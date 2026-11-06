import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows" / "helper"))

import threading

from pnp_source import (
    _kind_for_action,
    device_from_instance,
    parse_usb_vid_pid,
    public_record,
    stable_key,
    subscribe_described,
)


class PnpSourceTests(unittest.TestCase):
    def test_parse_known_ids_and_ignore_other_text(self):
        self.assertEqual(parse_usb_vid_pid(r"USB\VID_18D1&PID_2D00\tail"), (0x18D1, 0x2D00))
        self.assertEqual(parse_usb_vid_pid(r"USB\VID_12d1&PID_5000\tail"), (0x12D1, 0x5000))
        self.assertEqual(parse_usb_vid_pid(r"USB\VID_1234&PID_5678\tail"), (0x1234, 0x5678))
        self.assertIsNone(parse_usb_vid_pid("not-usb"))

    def test_key_hides_instance_tail_and_differs_per_device(self):
        first = r"USB\VID_18D1&PID_2D00\serial-a"
        second = r"USB\VID_18D1&PID_2D00\serial-b"
        self.assertNotIn("serial-a", stable_key(first))
        self.assertNotEqual(stable_key(first), stable_key(second))
        self.assertEqual(stable_key(first), stable_key(first))

    def test_record_keeps_problem_and_interface_without_the_instance(self):
        device = device_from_instance(r"USB\VID_18D1&PID_2D01\serial-a", 28, False)
        self.assertEqual((device.vendor_id, device.product_id), (0x18D1, 0x2D01))
        self.assertEqual(device.problem_code, 28)
        self.assertFalse(device.interface_present)
        self.assertNotIn("serial-a", device.key)
        self.assertEqual(public_record(device), {
            "vid": "18d1",
            "pid": "2d01",
            "problem_code": 28,
            "interface_present": False,
        })
        self.assertIsNone(device_from_instance(r"USB\VID_1234&PID_5678\serial-a", 0, True))

    def test_only_started_and_removed_instances_are_delivered(self):
        self.assertEqual(_kind_for_action(8), "arrive")
        self.assertEqual(_kind_for_action(9), "remove")
        self.assertIsNone(_kind_for_action(7))

    def test_arrival_is_described_outside_the_registration_callback(self):
        instance_id = r"USB\VID_18D1&PID_2D00\serial-a"
        inside = False
        described = []

        def register(callback):
            nonlocal inside
            inside = True
            callback("arrive", instance_id)
            inside = False
            return lambda: described.append("unsubscribed")

        def describe(value):
            self.assertFalse(inside)
            described.append(value)
            return device_from_instance(value, 0, True)

        seen = []
        done = threading.Event()

        def deliver(kind, device):
            seen.append((kind, device))
            done.set()

        unsubscribe = subscribe_described(register, describe, deliver)
        self.assertTrue(done.wait(1))
        unsubscribe()
        self.assertEqual(described[0], instance_id)
        self.assertEqual(described[-1], "unsubscribed")
        kind, device = seen[0]
        self.assertEqual(kind, "arrive")
        self.assertTrue(device.interface_present)
        self.assertEqual(device.problem_code, 0)


if __name__ == "__main__":
    unittest.main()
