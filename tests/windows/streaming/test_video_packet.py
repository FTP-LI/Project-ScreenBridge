import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "shared" / "protocol"))
sys.path.insert(0, str(ROOT / "prototypes" / "usb" / "host"))

from protocol import FrameReader, encode_frame
from video_packet import (
    HEADER,
    MAX_SBP1_PAYLOAD,
    AccessAssembler,
    VideoPacketError,
    encode_capability,
    encode_stop,
    split_access_unit,
)


class VideoPacketTests(unittest.TestCase):
    def test_large_frame_splits_inside_sbp1_and_reassembles(self):
        payload = bytes(range(256)) * 300
        self.assertGreater(len(payload), MAX_SBP1_PAYLOAD)
        packets = split_access_unit(7, 123456, True, payload)
        self.assertGreater(len(packets), 1)
        self.assertTrue(all(len(packet) <= MAX_SBP1_PAYLOAD for packet in packets))
        assembler = AccessAssembler(max_bytes=len(payload))
        message = None
        for packet in packets:
            message = assembler.push(packet)
        self.assertEqual(message.kind, "frame")
        self.assertEqual(message.access_unit, 7)
        self.assertEqual(message.timestamp_us, 123456)
        self.assertTrue(message.keyframe)
        self.assertEqual(message.payload, payload)
        self.assertEqual(assembler.retained(), 0)
        self.assertEqual(HEADER.size, 22)

    def test_new_frame_drops_the_incomplete_one(self):
        first = split_access_unit(1, 10, False, b"abcdef", fragment_payload=4)
        second = split_access_unit(2, 20, True, b"xyz", fragment_payload=4)
        assembler = AccessAssembler(max_bytes=64)
        self.assertIsNone(assembler.push(first[0]))
        message = assembler.push(second[0])
        self.assertEqual(assembler.dropped, 1)
        self.assertEqual(message.payload, b"xyz")
        self.assertTrue(message.keyframe)
        self.assertEqual(assembler.retained(), 0)

    def test_control_and_invalid_packets_do_not_build_a_frame(self):
        assembler = AccessAssembler(max_bytes=32)
        capability = assembler.push(encode_capability(1, 1920, 1080, 60))
        self.assertEqual(capability.kind, "capability")
        self.assertEqual(capability.payload, b"\x80\x07\x38\x04\x3c")
        stop = assembler.push(encode_stop(1))
        self.assertEqual(stop.kind, "stop")
        self.assertEqual(assembler.retained(), 0)
        bad_index = HEADER.pack(b"SBV1", 2, 0, 1, 1, 1, 1) + b"z"
        for packet in (b"SBV1", b"xxxx" + b"\x00" * 30, bad_index):
            with self.subTest(packet=packet[:4]), self.assertRaises(VideoPacketError):
                assembler.push(packet)
        self.assertEqual(assembler.dropped, 0)

    def test_oversize_assembly_is_rejected(self):
        packets = split_access_unit(4, 1, False, b"0123456789", fragment_payload=4)
        assembler = AccessAssembler(max_bytes=6)
        self.assertIsNone(assembler.push(packets[0]))
        with self.assertRaises(VideoPacketError):
            assembler.push(packets[1])
        self.assertEqual(assembler.retained(), 0)
        self.assertIsNone(assembler.push(packets[2]))

    def test_loss_discards_deltas_until_the_next_keyframe(self):
        assembler = AccessAssembler(max_bytes=64)
        early = split_access_unit(1, 1, False, b"delta", fragment_payload=8)
        self.assertIsNone(assembler.push(early[0]))
        self.assertEqual(assembler.discarded, 1)
        key = split_access_unit(2, 2, True, b"key", fragment_payload=8)
        self.assertEqual(assembler.push(key[0]).payload, b"key")
        lost = split_access_unit(3, 3, False, b"abcdef", fragment_payload=4)
        self.assertIsNone(assembler.push(lost[0]))
        delta = split_access_unit(4, 4, False, b"next", fragment_payload=8)
        self.assertIsNone(assembler.push(delta[0]))
        self.assertEqual(assembler.dropped, 1)
        self.assertEqual(assembler.discarded, 2)
        recovered = split_access_unit(5, 5, True, b"new", fragment_payload=8)
        message = assembler.push(recovered[0])
        self.assertEqual(message.payload, b"new")
        self.assertTrue(message.keyframe)

    def test_video_packets_roundtrip_through_sbp1_frames(self):
        payload = bytes(range(256)) * 300
        packets = split_access_unit(9, 99, True, payload)
        wire = b"".join(encode_frame(index, packet) for index, packet in enumerate(packets))
        chunks = [wire]

        def read(size, timeout):
            if not chunks:
                return b""
            return chunks.pop(0)

        reader = FrameReader(read)
        assembler = AccessAssembler(max_bytes=len(payload))
        message = None
        for _ in packets:
            sequence, body = reader.read_frame(1000)
            message = assembler.push(body)
        self.assertEqual(message.payload, payload)
        self.assertEqual(sequence, len(packets) - 1)

    def test_host_bytes_match_the_tablet_vector(self):
        key = split_access_unit(2, 6, True, b"key", fragment_payload=8)[0]
        capability = encode_capability(6, 1920, 1080, 60)
        self.assertEqual(key.hex(), "534256310201020000000600000000000000000001006b6579")
        self.assertEqual(capability.hex(), "53425631010006000000000000000000000000000100800738043c")


if __name__ == "__main__":
    unittest.main()
