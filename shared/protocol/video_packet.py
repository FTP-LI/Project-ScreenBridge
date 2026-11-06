"""Video messages carried inside one SBP1 payload.

Each packet is at most 65536 bytes. A larger access unit is split, and the
assembler keeps only the newest incomplete unit.
"""
import struct

MAGIC = b"SBV1"
HEADER = struct.Struct("<4sBBIQHH")
MAX_SBP1_PAYLOAD = 65536
MAX_FRAGMENT_PAYLOAD = MAX_SBP1_PAYLOAD - HEADER.size
CAPABILITY = 1
FRAGMENT = 2
STOP = 3
FLAG_KEYFRAME = 0x01
_MAX_FRAGMENTS = 256


class VideoPacketError(Exception):
    pass


class VideoMessage:
    def __init__(self, kind, access_unit, timestamp_us, keyframe, payload):
        self.kind = kind
        self.access_unit = access_unit
        self.timestamp_us = timestamp_us
        self.keyframe = keyframe
        self.payload = payload


def _encode(kind, flags, access_unit, timestamp_us, index, count, payload):
    if kind not in (CAPABILITY, FRAGMENT, STOP):
        raise VideoPacketError("unknown video message")
    if isinstance(access_unit, bool) or not isinstance(access_unit, int) or access_unit < 0 or access_unit > 0xFFFFFFFF:
        raise VideoPacketError("invalid access unit")
    if isinstance(timestamp_us, bool) or not isinstance(timestamp_us, int) or timestamp_us < 0 or timestamp_us > 0xFFFFFFFFFFFFFFFF:
        raise VideoPacketError("invalid timestamp")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > _MAX_FRAGMENTS or index >= count:
        raise VideoPacketError("invalid fragment position")
    payload = bytes(payload)
    if len(payload) > MAX_FRAGMENT_PAYLOAD:
        raise VideoPacketError("fragment exceeds SBP1 payload")
    return HEADER.pack(MAGIC, kind, flags, access_unit, timestamp_us, index, count) + payload


def encode_capability(access_unit, max_width, max_height, max_fps):
    payload = struct.pack("<HHB", max_width, max_height, max_fps)
    return _encode(CAPABILITY, 0, access_unit, 0, 0, 1, payload)


def encode_stop(access_unit):
    return _encode(STOP, 0, access_unit, 0, 0, 1, b"")


def split_access_unit(access_unit, timestamp_us, keyframe, payload, fragment_payload=MAX_FRAGMENT_PAYLOAD):
    payload = bytes(payload)
    if fragment_payload < 1 or fragment_payload > MAX_FRAGMENT_PAYLOAD:
        raise VideoPacketError("invalid fragment size")
    if not payload:
        raise VideoPacketError("empty video frame")
    flags = FLAG_KEYFRAME if keyframe else 0
    count = (len(payload) + fragment_payload - 1) // fragment_payload
    if count > _MAX_FRAGMENTS:
        raise VideoPacketError("frame needs too many fragments")
    packets = []
    for index in range(count):
        start = index * fragment_payload
        packets.append(_encode(
            FRAGMENT, flags, access_unit, timestamp_us, index, count, payload[start:start + fragment_payload]
        ))
    return tuple(packets)


def decode_packet(packet):
    if not isinstance(packet, (bytes, bytearray)) or len(packet) < HEADER.size:
        raise VideoPacketError("short video packet")
    magic, kind, flags, access_unit, timestamp_us, index, count = HEADER.unpack_from(packet)
    if magic != MAGIC or kind not in (CAPABILITY, FRAGMENT, STOP) or flags > 0x01:
        raise VideoPacketError("invalid video packet")
    if count < 1 or count > _MAX_FRAGMENTS or index >= count:
        raise VideoPacketError("invalid fragment position")
    return kind, flags, access_unit, timestamp_us, index, count, bytes(packet[HEADER.size:])


class AccessAssembler:
    def __init__(self, max_bytes):
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise VideoPacketError("invalid assembly limit")
        self.max_bytes = max_bytes
        self.dropped = 0
        self.discarded = 0
        self._synced = False
        self._unit = None
        self._count = 0
        self._flags = 0
        self._timestamp = 0
        self._parts = {}

    def retained(self):
        return sum(len(item) for item in self._parts.values())

    def push(self, packet):
        kind, flags, access_unit, timestamp_us, index, count, payload = decode_packet(packet)
        if kind != FRAGMENT:
            return VideoMessage(
                "capability" if kind == CAPABILITY else "stop",
                access_unit,
                timestamp_us,
                False,
                payload,
            )
        if self._unit != access_unit:
            if self._unit is not None:
                self.dropped += 1
                self._synced = False
            self._unit = access_unit
            self._count = count
            self._flags = flags
            self._timestamp = timestamp_us
            self._parts = {}
        if count != self._count or flags != self._flags or timestamp_us != self._timestamp:
            self._lose()
            raise VideoPacketError("fragment metadata mismatch")
        if index in self._parts and self._parts[index] != payload:
            self._lose()
            raise VideoPacketError("conflicting fragment")
        if index not in self._parts and self.retained() + len(payload) > self.max_bytes:
            self._lose()
            raise VideoPacketError("access unit exceeds assembly limit")
        self._parts[index] = payload
        if len(self._parts) != self._count:
            return None
        assembled = b"".join(self._parts[item] for item in range(self._count))
        keyframe = bool(flags & FLAG_KEYFRAME)
        message = VideoMessage("frame", access_unit, timestamp_us, keyframe, assembled)
        self._clear()
        if not keyframe and not self._synced:
            self.discarded += 1
            return None
        if keyframe:
            self._synced = True
        return message

    def _lose(self):
        self._synced = False
        self._clear()

    def _clear(self):
        self._unit = None
        self._count = 0
        self._flags = 0
        self._timestamp = 0
        self._parts = {}
