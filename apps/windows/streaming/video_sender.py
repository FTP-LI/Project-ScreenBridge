"""Bounded SBV1-over-SBP1 video sender.

The sender accepts already encoded access units. Encoder selection and the
IDD frame source stay outside this module so protocol behavior can be tested
without a GPU or a tablet.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_HOST_PROTOCOL = str(_ROOT / "prototypes" / "usb" / "host")
_VIDEO_PROTOCOL = str(_ROOT / "shared" / "protocol")
for _path in (_HOST_PROTOCOL, _VIDEO_PROTOCOL):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from protocol import encode_frame, write_all
from video_packet import encode_capability, encode_stop, split_access_unit


class VideoSender:
    def __init__(self, transport, *, timeout_ms=5000, sequence=0):
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0 or sequence > 0xFFFFFFFF:
            raise ValueError("sequence must be a uint32")
        self.transport = transport
        self.timeout_ms = timeout_ms
        self.sequence = sequence

    def send_capability(self, max_width, max_height, max_fps):
        self._send(encode_capability(0, max_width, max_height, max_fps))

    def send_access_unit(self, access_unit, timestamp_us, keyframe, payload):
        for packet in split_access_unit(access_unit, timestamp_us, keyframe, payload):
            self._send(packet)

    def send_stop(self, access_unit):
        self._send(encode_stop(access_unit))

    def _send(self, payload):
        frame = encode_frame(self.sequence, payload)
        write_all(self.transport.write, frame, self.timeout_ms)
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
