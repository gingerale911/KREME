"""Received payload totals include every datagram, before guard validation."""

from krem.ingest.protocol import F1UDPProtocol, PacketStats
from test_guard import _make_header


def test_received_bytes_include_accepted_and_rejected_datagrams():
    protocol = F1UDPProtocol()
    valid = _make_header()
    invalid = b"invalid"
    for payload in (valid, invalid, b""):
        protocol.datagram_received(payload, ("127.0.0.1", 20777))
    snapshot = protocol.stats.snapshot()
    assert snapshot["packetsReceived"] == 3
    assert snapshot["packetsAccepted"] == 1
    assert snapshot["packetsRejected"] == 2
    assert snapshot["bytesReceived"] == len(valid) + len(invalid)
    # Reading stats (including a paused/stale feed) does not add or clear bytes.
    assert protocol.stats.snapshot()["bytesReceived"] == snapshot["bytesReceived"]


def test_byte_total_starts_at_zero_and_supports_multiple_gigabytes():
    stats = PacketStats()
    assert stats.snapshot()["bytesReceived"] == 0
    stats.record_received(5_000_000_000)
    stats.record_received(1352)
    assert stats.snapshot()["bytesReceived"] == 5_000_001_352
    assert PacketStats().snapshot()["bytesReceived"] == 0
