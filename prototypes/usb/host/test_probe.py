import unittest
from usb_probe import IDENTITY, choose, protocol_version, start_accessory


class FakeDevice:
    def __init__(self, version=b"\x02\x00"):
        self.version = version
        self.calls = []

    def ctrl_transfer(self, direction, request, value, index, data, timeout):
        self.calls.append((direction, request, value, index, data))
        return self.version if request == 51 else len(data)


class ProbeTests(unittest.TestCase):
    def test_probe_is_read_only(self):
        device = FakeDevice()
        self.assertEqual(protocol_version(device, 100), 2)
        self.assertEqual(device.calls, [(0xC0, 51, 0, 0, 2)])

    def test_start_sends_identity_before_mode_change(self):
        device = FakeDevice()
        self.assertEqual(start_accessory(device, 100), 2)
        self.assertEqual(len(device.calls), 8)
        for index, value in enumerate(IDENTITY):
            self.assertEqual(device.calls[index + 1], (0x40, 52, 0, index, value.encode() + b"\0"))
        self.assertEqual(device.calls[-1], (0x40, 53, 0, 0, b""))

    def test_unsupported_or_invalid_version_cannot_switch_mode(self):
        for version in (b"\0\0", b"\x02", b"\x03\0"):
            device = FakeDevice(version)
            with self.assertRaises(RuntimeError):
                start_accessory(device, 100)
            self.assertEqual(len(device.calls), 1)

    def test_absent_or_ambiguous_device_rejected(self):
        for devices in ([], [object(), object()]):
            with self.assertRaises(RuntimeError):
                choose(devices)


if __name__ == '__main__':
    unittest.main()
