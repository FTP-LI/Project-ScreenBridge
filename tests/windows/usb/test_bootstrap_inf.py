import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INF = ROOT / "drivers" / "windows" / "usb" / "ScreenBridgeBootstrap.inf"


class BootstrapInfTests(unittest.TestCase):
    def test_normal_mode_package_is_explicit_and_does_not_match_accessory_or_hdc(self):
        text = INF.read_text(encoding="utf-8")
        self.assertIn("USB\\VID_12D1&PID_107E", text)
        self.assertNotIn("USB\\VID_12D1&PID_5000", text)
        self.assertNotIn("USB\\VID_18D1&PID_2D00", text)
        self.assertNotIn("USB\\VID_18D1&PID_2D01", text)
        self.assertNotRegex(text, r"USB\\VID_12D1&PID_107E&MI_")
        hardware_lines = [
            line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith(";")
            and "USB\\VID_" in line
        ]
        self.assertEqual(hardware_lines, ["%DeviceName% = USB_Install, USB\\VID_12D1&PID_107E"])

    def test_package_uses_the_screenbridge_interface_guid(self):
        text = INF.read_text(encoding="utf-8")
        self.assertIn("{331c44be-387b-4621-84a7-f55422e41cfc}", text.lower())
        self.assertIn("DeviceInterfaceGUIDs", text)
        self.assertIn("A;;GRGW;;;IU", text)
        self.assertNotIn("A;;GA;;;AU", text)


if __name__ == "__main__":
    unittest.main()
