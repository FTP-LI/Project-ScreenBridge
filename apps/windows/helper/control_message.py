"""Explicit helper control messages.

A malformed frame is rejected before a session can open a transport.
"""
import struct

MAGIC = b"SBC1"
_PACK = struct.Struct("<4sBHB")
_KINDS = {"capability": 1, "ready": 2, "stop": 3}
_NAMES = {value: name for name, value in _KINDS.items()}


class ControlError(Exception):
    pass


def encode_control(kind, version, paired, accept):
    if kind not in _KINDS:
        raise ControlError("unknown control kind")
    if isinstance(version, bool) or not isinstance(version, int) or version < 0 or version > 0xFFFF:
        raise ControlError("invalid control version")
    flags = (1 if paired else 0) | (2 if accept else 0)
    return _PACK.pack(MAGIC, _KINDS[kind], version, flags)


def decode_control(payload):
    if not isinstance(payload, (bytes, bytearray)) or len(payload) != _PACK.size:
        raise ControlError("invalid control length")
    magic, kind, version, flags = _PACK.unpack(payload)
    if magic != MAGIC or kind not in _NAMES or flags > 0x03:
        raise ControlError("invalid control message")
    return {
        "kind": _NAMES[kind],
        "version": version,
        "paired": bool(flags & 0x01),
        "accept": bool(flags & 0x02),
    }
