import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows" / "streaming"))
sys.path.insert(0, str(ROOT / "prototypes" / "usb" / "host"))
sys.path.insert(0, str(ROOT / "shared" / "protocol"))

from video_sender import VideoSender
from protocol import FrameReader
from video_packet import AccessAssembler


class FakeTransport:
    def __init__(self):
        self.writes = []

    def write(self, data, timeout_ms):
        self.writes.append((bytes(data), timeout_ms))
        return len(data)


class VideoSenderTests(unittest.TestCase):
    def test_capability_keyframe_and_stop_use_bounded_sbp1_frames(self):
        transport = FakeTransport()
        sender = VideoSender(transport, timeout_ms=500)
        sender.send_capability(1920, 1080, 30)
        sender.send_access_unit(100, 1234, True, b"keyframe")
        sender.send_access_unit(101, 2234, False, b"delta")
        sender.send_stop(102)

        reader = FrameReader(lambda size, timeout: transport.writes.pop(0)[0])
        frames = [reader.read_frame(500) for _ in range(4)]
        assembler = AccessAssembler(1024)
        messages = [assembler.push(payload) for _, payload in frames]
        self.assertEqual(messages[0].kind, "capability")
        self.assertEqual(messages[1].payload, b"keyframe")
        self.assertEqual(messages[2].payload, b"delta")
        self.assertEqual(messages[3].kind, "stop")
        self.assertEqual([sequence for sequence, _ in frames], [0, 1, 2, 3])

    def test_large_access_unit_is_split_without_unbounded_payload(self):
        transport = FakeTransport()
        sender = VideoSender(transport, timeout_ms=100)
        sender.send_access_unit(1, 1, True, b"x" * 120000)
        self.assertGreater(len(transport.writes), 1)
        self.assertTrue(all(len(data) <= 16 + 65536 for data, _ in transport.writes))


if __name__ == "__main__":
    unittest.main()
