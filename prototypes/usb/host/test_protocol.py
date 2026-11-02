import struct
import unittest

from protocol import FrameReader, ProtocolError, encode_frame, verify_echo, write_all


class ProtocolTests(unittest.TestCase):
    def test_wire_vector(self):
        self.assertEqual(encode_frame(7, b"123456789"),
                         b"SBP1" + struct.pack("<III", 7, 9, 0xCBF43926) + b"123456789")

    def reader(self, chunks):
        iterator = iter(chunks)
        return FrameReader(lambda size, timeout: next(iterator, b""))

    def test_fragmented_and_coalesced_frames(self):
        first, second = encode_frame(1, b"abc"), encode_frame(2, b"def")
        reader = self.reader([first[:2], first[2:15], first[15:] + second])
        self.assertEqual(reader.read_frame(1000), (1, b"abc"))
        self.assertEqual(reader.read_frame(1000), (2, b"def"))

    def test_empty_and_maximum_payload(self):
        for payload in (b"", bytes(range(256)) * 256):
            wire = encode_frame(0xFFFFFFFF, payload)
            chunks = [wire[i:i+4096] for i in range(0, len(wire), 4096)]
            self.assertEqual(self.reader(chunks).read_frame(1000), (0xFFFFFFFF, payload))

    def test_bad_magic_length_checksum_and_truncation(self):
        valid = encode_frame(1, b"abc")
        cases = [b"xxxx" + valid[4:], b"SBP1" + struct.pack("<III", 1, 65537, 0),
                 valid[:-1] + b"x", valid[:-1]]
        for wire in cases:
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                self.reader([wire]).read_frame(1000)

    def test_wrong_sequence_or_payload_fails(self):
        for received in ((2, b"abc"), (1, b"xyz")):
            with self.assertRaises(ProtocolError):
                verify_echo(1, b"abc", received)

    def test_oversized_payload_rejected(self):
        with self.assertRaises(ValueError):
            encode_frame(1, bytes(65537))

    def test_partial_writes_and_zero_progress(self):
        sent = bytearray()
        def write(data, timeout):
            sent.extend(data[:3])
            return min(3, len(data))
        write_all(write, b"abcdefgh", 1000)
        self.assertEqual(sent, b"abcdefgh")
        with self.assertRaises(ProtocolError):
            write_all(lambda data, timeout: 0, b"x", 1000)

    def test_expired_deadline(self):
        with self.assertRaises(TimeoutError):
            self.reader([]).read_frame(0)
        with self.assertRaises(TimeoutError):
            write_all(lambda data, timeout: len(data), b"x", 0)


if __name__ == "__main__":
    unittest.main()
