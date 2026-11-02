"""KREM — F1 25 Telemetry Dashboard entry point.

Starts the UDP listener, recorder, live state, and web server.

Usage:
    python -m krem                    # listen on default port 20777
    python -m krem --port 20778       # custom port
    python -m krem --replay capture.f1udp   # replay a capture file
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

import uvicorn

from krem.core import DEFAULT_UDP_PORT
from krem.ingest.protocol import F1UDPProtocol
from krem.ingest.recorder import Recorder, ReplayReader
from krem.pipeline import LiveState
from krem.ingest import decode_packet
from krem.server import create_app


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run_live(
    port: int,
    host: str,
    web_port: int,
    captures_dir: Path,
    no_record: bool,
) -> None:
    """Run the live UDP listener + web server."""
    live_state = LiveState()
    recorder = None if no_record else Recorder(captures_dir)

    protocol = F1UDPProtocol(
        on_packet=live_state.update,
        recorder=recorder,
    )

    loop = asyncio.get_event_loop()

    # Start UDP listener
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol,
        local_addr=(host, port),
    )

    logging.getLogger("krem").info(
        "KREM listening on UDP %s:%d · Web server on http://localhost:%d",
        host, port, web_port,
    )

    if recorder and not no_record:
        recorder.start(session_uid=0)
        logging.getLogger("krem").info("Recording to %s", recorder.filepath)

    # Create FastAPI app
    app = create_app(live_state, protocol)

    # Run uvicorn in-process
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=web_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Handle shutdown
    shutdown_event = asyncio.Event()

    def handle_signal():
        logging.getLogger("krem").info("Shutting down...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass  # Windows

    # Run server in background
    server_task = asyncio.create_task(server.serve())

    # Wait for shutdown
    await shutdown_event.wait()

    # Cleanup
    transport.close()
    if recorder:
        recorder.stop()
        logging.getLogger("krem").info(
            "Recorded %d packets (%s bytes) to %s",
            recorder.packet_count,
            f"{recorder.bytes_written:,}",
            recorder.filepath,
        )

    server.should_exit = True
    await server_task


async def run_replay(
    filepath: Path,
    speed: float,
    web_port: int,
) -> None:
    """Replay a .f1udp capture file through the pipeline."""
    live_state = LiveState()
    protocol_stats_holder = F1UDPProtocol()  # just for stats display

    logger = logging.getLogger("krem.replay")
    logger.info("Replaying %s at %.1fx speed", filepath, speed)

    reader = ReplayReader(filepath)
    packets = reader.packets()
    logger.info("Loaded %d packets from capture", len(packets))

    # Create and start server
    app = create_app(live_state, protocol_stats_holder)
    config = uvicorn.Config(app, host="0.0.0.0", port=web_port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait a moment for server to start
    await asyncio.sleep(0.5)

    # Replay packets with timing
    prev_ts = 0.0
    for i, (ts, datagram) in enumerate(packets):
        if i > 0 and speed > 0:
            delay = (ts - prev_ts) / speed
            if delay > 0:
                await asyncio.sleep(delay)
        prev_ts = ts

        packet = decode_packet(datagram)
        if packet is not None:
            live_state.update(packet)
            protocol_stats_holder.stats.record_accepted(packet.header.packet_id)

        if (i + 1) % 1000 == 0:
            logger.info("Replayed %d / %d packets", i + 1, len(packets))

    logger.info("Replay complete. Server still running — press Ctrl+C to stop.")

    # Keep server running
    try:
        await server_task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="krem",
        description="KREM — F1 25 Telemetry Dashboard",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_UDP_PORT,
        help=f"UDP port to listen on (default: {DEFAULT_UDP_PORT})",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="UDP host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--web-port", "-w",
        type=int,
        default=8765,
        help="Web server port (default: 8765)",
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
        help="Replay a .f1udp capture file instead of live UDP",
    )
    parser.add_argument(
        "--replay-speed",
        type=float,
        default=1.0,
        help="Replay speed multiplier (default: 1.0, 0 = as fast as possible)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    logger = logging.getLogger("krem")
    logger.info("╔═══════════════════════════════════════╗")
    logger.info("║   KREM — F1 25 Telemetry Dashboard    ║")
    logger.info("╚═══════════════════════════════════════╝")

    if args.replay:
        asyncio.run(run_replay(
            filepath=args.replay,
            speed=args.replay_speed,
            web_port=args.web_port,
        ))
    else:
        asyncio.run(run_live(
            port=args.port,
            host=args.host,
            web_port=args.web_port,
            captures_dir=args.captures_dir,
            no_record=args.no_record,
        ))


if __name__ == "__main__":
    main()
