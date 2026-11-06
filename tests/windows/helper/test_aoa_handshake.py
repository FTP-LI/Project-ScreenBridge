import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows" / "helper"))

from aoa_handshake import (
    IDENTITY,
    HandshakeError,
    choose_one,
    protocol_version,
    should_handshake,
    start_accessory,
)

DEBUG = (0x12D1, 0x5000)
ACCESSORY = (0x18D1, 0x2D00)


class FakeDevice:
    def __init__(self, version=b"\x02\x00"):
        self.version = version
        self.calls = []

    def ctrl_transfer(self, direction, request, value, index, data, timeout):
        self.calls.append((direction, request, value, index, data))
        return self.version if request == 51 else len(data)


class AoaHandshakeTests(unittest.TestCase):
    def test_probe_is_read_only(self):
        device = FakeDevice()
        self.assertEqual(protocol_version(device, 100), 2)
        self.assertEqual(device.calls, [(0xC0, 51, 0, 0, 2)])

    def test_start_sends_identity_before_mode_change(self):
        device = FakeDevice()
        self.assertEqual(start_accessory(device, 100), 2)
        self.assertEqual(len(device.calls), 8)
        for index, value in enumerate(IDENTITY):
            self.assertEqual(
                device.calls[index + 1],
                (0x40, 52, 0, index, value.encode("utf-8") + b"\0"),
            )
        self.assertEqual(device.calls[-1], (0x40, 53, 0, 0, b""))

    def test_unsupported_or_invalid_version_cannot_switch_mode(self):
        for version in (b"\x00\x00", b"\x02", b"\x03\x00"):
            with self.subTest(version=version):
                device = FakeDevice(version)
                with self.assertRaises(HandshakeError):
                    start_accessory(device, 100)
                self.assertEqual(len(device.calls), 1)

    def test_choose_one_rejects_absent_or_ambiguous_devices(self):
        with self.assertRaises(HandshakeError):
            choose_one([])
        with self.assertRaises(HandshakeError):
            choose_one([object(), object()])
        target = object()
        self.assertIs(choose_one([target]), target)

    def test_should_handshake_only_for_debug_identity(self):
        self.assertTrue(should_handshake([DEBUG], "waiting_reenumeration", ["handshake"]))
        self.assertTrue(should_handshake([DEBUG], "discovered", []))
        self.assertFalse(should_handshake([], "disconnected", ["handshake"]))
        self.assertFalse(should_handshake([ACCESSORY], "waiting_tablet", ["handshake"]))
        self.assertFalse(should_handshake([DEBUG, ACCESSORY], "waiting_reenumeration", ["handshake"]))

    def test_should_handshake_rejects_active_session_and_repeats(self):
        for phase in ("waiting_tablet", "establishing", "running", "cleaning", "needs_setup"):
            with self.subTest(phase=phase):
                self.assertFalse(should_handshake([DEBUG], phase, ["handshake"]))
        self.assertFalse(
            should_handshake([DEBUG], "waiting_reenumeration", ["handshake"], already_attempted=True)
        )


if __name__ == "__main__":
    unittest.main()
