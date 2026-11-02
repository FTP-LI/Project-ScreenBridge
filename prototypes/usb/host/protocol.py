"""Bounded SBP1 echo framing, independent of the USB backend."""
import struct
import time
import zlib

MAX_PAYLOAD = 65536
HEADER = struct.Struct("<4sIII")
CHUNK = 16384


class ProtocolError(Exception):
    pass


def encode_frame(sequence, payload):
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload exceeds 65536 bytes")
    return HEADER.pack(b"SBP1", sequence, len(payload), zlib.crc32(payload)) + payload


def remaining_ms(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("frame deadline expired")
    return max(1, int(remaining * 1000))


class FrameReader:
    def __init__(self, read):
        self.read = read
        self.buffer = bytearray()

    def read_frame(self, timeout_ms):
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            timeout = remaining_ms(deadline)
            if len(self.buffer) >= HEADER.size:
                magic, sequence, length, checksum = HEADER.unpack_from(self.buffer)
                if magic != b"SBP1" or length > MAX_PAYLOAD:
                    raise ProtocolError("invalid magic or payload length")
                end = HEADER.size + length
                if len(self.buffer) >= end:
                    payload = bytes(self.buffer[HEADER.size:end])
                    del self.buffer[:end]
                    if zlib.crc32(payload) != checksum:
                        raise ProtocolError("CRC32 mismatch")
                    return sequence, payload
            chunk = self.read(CHUNK, timeout)
            if not chunk:
                raise ProtocolError("stream closed or zero-length read")
            self.buffer.extend(chunk)
            if len(self.buffer) > HEADER.size + MAX_PAYLOAD + CHUNK:
                raise ProtocolError("receive buffer limit exceeded")


def verify_echo(sequence, payload, received):
    if received != (sequence, payload):
        raise ProtocolError("echo sequence or payload mismatch")


def write_all(write, data, timeout_ms):
    deadline = time.monotonic() + timeout_ms / 1000
    offset = 0
    while offset < len(data):
        chunk = data[offset:offset + CHUNK]
        count = write(chunk, remaining_ms(deadline))
        if count <= 0 or count > len(chunk):
            raise ProtocolError("invalid write progress")
        offset += count
