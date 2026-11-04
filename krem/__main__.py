
"""KREM — F1 25 Telemetry Dashboard entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

import uvicorn

from krem.core import DEFAULT_UDP_PORT
from krem.ingest import decode_packet
from krem.ingest.protocol import F1UDPProtocol
from krem.ingest.recorder import Recorder, ReplayReader
from krem.pipeline import LiveState
from krem.server import create_app
from krem.storage import LapDatabase, LapRepository
from krem.storage.lap_writer import LapStorageWriter


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------

def create_lap_storage(database_path: Path):
    """Create database, repository and background writer."""

    database_path.parent.mkdir(parents=True, exist_ok=True)

    database = LapDatabase(str(database_path))
    repository = LapRepository(database)
    writer = LapStorageWriter(repository)

    return database, repository, writer


def attach_lap_storage(
    live_state: LiveState,
    writer: LapStorageWriter,
) -> None:
    live_state.lap_recorder.storage_writer = writer


def flush_lap_storage(
    live_state: LiveState,
    writer: LapStorageWriter,
) -> None:
    """Finalize pending recorder data and wait for database writes."""

    with live_state._lock:
        live_state.lap_recorder.flush(force=True)

    writer.flush()


def close_lap_storage(
    database: LapDatabase,
    writer: LapStorageWriter,
) -> None:
    try:
        writer.close()
    finally:
        database.close()


# ---------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------

async def run_live(
    port: int,
    host: str,
    web_port: int,
    captures_dir: Path,
    no_record: bool,
) -> None:

    live_state = LiveState()
    recorder = None if no_record else Recorder(captures_dir)

    database_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "krem-live.duckdb"
    )

    database, lap_repository, storage_writer = create_lap_storage(
        database_path
    )

    attach_lap_storage(live_state, storage_writer)

    transport = None
    server = None
    server_task = None

    loop = asyncio.get_running_loop()

    try:
        protocol = F1UDPProtocol(
            on_packet=live_state.update,
            recorder=recorder,
        )

        transport, _ = await loop.create_datagram_endpoint(
            lambda: protocol,
            local_addr=(host, port),
        )

        logging.getLogger("krem").info(
            "KREM listening on UDP %s:%d — Web server on http://localhost:%d",
            host,
            port,
            web_port,
        )

        if recorder:
            recorder.start(session_uid=0)
            logging.getLogger("krem").info(
                "Recording to %s",
                recorder.filepath,
            )

        app = create_app(
            live_state,
            protocol,
            lap_repository=lap_repository,
        )

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=web_port,
            log_level="warning",
            access_log=False,
        )

        server = uvicorn.Server(config)
        shutdown_event = asyncio.Event()

        def handle_signal():
            logging.getLogger("krem").info("Shutting down...")
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, handle_signal)
            except (NotImplementedError, RuntimeError):
                pass

        server_task = asyncio.create_task(server.serve())

        await shutdown_event.wait()

    finally:
        if transport is not None:
            transport.close()

        if recorder:
            recorder.stop()
            logging.getLogger("krem").info(
                "Recorded %d packets (%s bytes) to %s",
                recorder.packet_count,
                f"{recorder.bytes_written:,}",
                recorder.filepath,
            )

        if server is not None:
            server.should_exit = True

        if server_task is not None:
            try:
                await server_task
            except asyncio.CancelledError:
                pass

        try:
            flush_lap_storage(live_state, storage_writer)
        finally:
            close_lap_storage(database, storage_writer)

        logging.getLogger("krem").info(
            "Live telemetry storage closed: %s",
            database_path,
        )


# ---------------------------------------------------------------------
# Replay mode
# ---------------------------------------------------------------------

async def run_replay(
    filepath: Path,
    speed: float,
    web_port: int,
) -> None:

    if not filepath.exists():
        raise FileNotFoundError(f"Capture file not found: {filepath}")

    if speed < 0:
        raise ValueError("Replay speed cannot be negative")

    live_state = LiveState()
    protocol = F1UDPProtocol()

    database_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "replays"
        / f"{filepath.stem}.duckdb"
    )

    database, lap_repository, storage_writer = create_lap_storage(
        database_path
    )

    attach_lap_storage(live_state, storage_writer)

    logger = logging.getLogger("krem.replay")

    server = None
    server_task = None

    try:
        logger.info("Replaying %s at %.1fx speed", filepath, speed)

        reader = ReplayReader(filepath)
        packets = reader.packets()

        logger.info("Loaded %d packets from capture", len(packets))

        app = create_app(
            live_state,
            protocol,
            lap_repository=lap_repository,
        )

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=web_port,
            log_level="warning",
        )

        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())

        await asyncio.sleep(0.5)

        previous_timestamp = 0.0

        for i, (timestamp, datagram) in enumerate(packets):
            if i > 0 and speed > 0:
                delay = (timestamp - previous_timestamp) / speed

                if delay > 0:
                    await asyncio.sleep(delay)

            previous_timestamp = timestamp

            packet = decode_packet(datagram)

            if packet is not None:
                live_state.update(packet)
                protocol.stats.record_accepted(
                    packet.header.packet_id
                )

            if (i + 1) % 1000 == 0:
                logger.info(
                    "Replayed %d / %d packets",
                    i + 1,
                    len(packets),
                )

        flush_lap_storage(live_state, storage_writer)

        logger.info("Replay complete. Server remains available.")
        logger.info("Replay database: %s", database_path)

        await server_task

    finally:
        if server is not None:
            server.should_exit = True

        if server_task is not None and not server_task.done():
            server_task.cancel()

            try:
                await server_task
            except asyncio.CancelledError:
                pass

        close_lap_storage(database, storage_writer)

        logger.info("Replay storage closed.")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser(
        prog="krem",
        description="KREM — F1 25 Telemetry Dashboard",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=DEFAULT_UDP_PORT,
        help=f"UDP port (default: {DEFAULT_UDP_PORT})",
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="UDP host to bind to",
    )

    parser.add_argument(
        "--web-port",
        "-w",
        type=int,
        default=8765,
        help="Web server port",
    )

    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path(__file__).parent.parent / "captures",
        help="Directory for raw captures",
    )

    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Disable raw capture recording",
    )

    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="Replay a .f1udp capture file",
    )

    parser.add_argument(
        "--replay-speed",
        type=float,
        default=1.0,
        help="Replay speed multiplier (0 = maximum speed)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    logger = logging.getLogger("krem")

    logger.info("KREM — F1 25 Telemetry Dashboard")

    if args.replay:
        asyncio.run(
            run_replay(
                filepath=args.replay,
                speed=args.replay_speed,
                web_port=args.web_port,
            )
        )
    else:
        asyncio.run(
            run_live(
                port=args.port,
                host=args.host,
                web_port=args.web_port,
                captures_dir=args.captures_dir,
                no_record=args.no_record,
            )
        )


if __name__ == "__main__":
    main()
