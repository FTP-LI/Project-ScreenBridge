import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows" / "helper"))

from winusb_transport import TransportClosed, WinUsbTransport


class FakeBackend:
    def __init__(self):
        self.sessions = []
        self.reads = []
        self.writes = []
        self.closes = 0

    def open(self, path):
        session = object()
        self.sessions.append((path, session))
        return session, 0x81, 0x02

    def read(self, session, pipe_id, size, timeout_ms):
        self.reads.append((session, pipe_id, size, timeout_ms))
        return b"frame"

    def write(self, session, pipe_id, data, timeout_ms):
        self.writes.append((session, pipe_id, bytes(data), timeout_ms))
        return len(data)

    def close(self, session):
        self.closes += 1


class WinUsbTransportTests(unittest.TestCase):
    def test_open_read_write_and_idempotent_close(self):
        backend = FakeBackend()
        transport = WinUsbTransport.open("\\\\?\\usb#screenbridge", backend=backend)
        self.assertEqual(transport.read(64, 500), b"frame")
        self.assertEqual(transport.write(b"hello", 500), 5)
        transport.close()
        transport.close()
        self.assertEqual(backend.closes, 1)
        with self.assertRaises(TransportClosed):
            transport.read(64, 500)
        with self.assertRaises(TransportClosed):
            transport.write(b"x", 500)

    def test_open_rejects_empty_interface_path(self):
        with self.assertRaises(ValueError):
            WinUsbTransport.open("", backend=FakeBackend())

    def test_open_first_rejects_zero_or_ambiguous_paths(self):
        backend = FakeBackend()
        with self.assertRaises(RuntimeError):
            WinUsbTransport.open_first([], backend=backend)
        with self.assertRaises(RuntimeError):
            WinUsbTransport.open_first(["a", "b"], backend=backend)
        transport = WinUsbTransport.open_first(["a"], backend=backend)
        transport.close()


if __name__ == "__main__":
    unittest.main()
