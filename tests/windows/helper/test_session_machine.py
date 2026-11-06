import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows" / "helper"))

from session_machine import DeviceSeen, SessionMachine
from host_step import classify_present


def debug_device(key="tablet-a"):
    return DeviceSeen(key, 0x12D1, 0x5000, 0, True)


def accessory(key="tablet-a", problem_code=0, interface_present=True):
    return DeviceSeen(key, 0x18D1, 0x2D00, problem_code, interface_present)


def ready(machine):
    machine.control(kind="ready", version=1, paired=True, accept=True)


class SessionMachineTests(unittest.TestCase):
    def test_duplicate_attach_opens_one_session(self):
        machine = SessionMachine(("tablet-a",))
        machine.attach(debug_device())
        machine.attach(debug_device())
        self.assertEqual(machine.actions.count("handshake"), 1)
        self.assertFalse(machine.display_connected)
        self.assertEqual(machine.phase, "waiting_reenumeration")

    def test_reenumeration_waits_for_tablet_without_another_handshake(self):
        machine = SessionMachine(("tablet-a",))
        machine.attach(debug_device())
        machine.attach(accessory())
        self.assertEqual(machine.actions.count("handshake"), 1)
        self.assertEqual(machine.phase, "waiting_tablet")
        self.assertFalse(machine.display_connected)

    def test_present_accessory_does_not_request_handshake(self):
        self.assertEqual(classify_present([(0x18D1, 0x2D00)]), "wait_tablet")
        self.assertEqual(classify_present([(0x12D1, 0x5000)]), "handshake")
        self.assertEqual(classify_present([]), "idle")
        self.assertEqual(classify_present([(0x12D1, 0x5000), (0x18D1, 0x2D00)]), "ambiguous")

    def test_unpaired_or_foreign_accessory_does_not_show_display(self):
        machine = SessionMachine(("tablet-a",))
        machine.attach(accessory("other-tablet"))
        machine.attach(debug_device())
        machine.attach(accessory("foreign", problem_code=0, interface_present=True))
        ready(machine)
        self.assertIn("reject_unpaired", machine.actions)
        self.assertIn("reject_ambiguous", machine.actions)
        self.assertNotIn("show_display", machine.actions)
        self.assertFalse(machine.display_connected)

    def test_removal_stop_and_background_clean_up_once(self):
        for reason in ("unplug", "stop", "background", "read_hang"):
            machine = SessionMachine(("tablet-a",))
            machine.attach(accessory())
            ready(machine)
            self.assertFalse(machine.display_connected)
            machine.note_keyframe()
            self.assertTrue(machine.display_connected)
            machine.stop(reason)
            machine.stop(reason)
            self.assertEqual(machine.phase, "disconnected")
            self.assertFalse(machine.display_connected)
            self.assertEqual(machine.actions.count("cleanup"), 1)
            self.assertEqual(machine.actions.count("hide_display"), 1)
            self.assertIn("cleaning", machine.phases)

    def test_tablet_not_ready_does_not_send_display(self):
        cases = (
            {"kind": "ready", "version": 1, "paired": True, "accept": False},
            {"kind": "ready", "version": 99, "paired": True, "accept": True},
            {"kind": "ready", "version": 1, "paired": False, "accept": True},
            {"kind": "capability", "version": 1, "paired": True, "accept": True},
        )
        for message in cases:
            machine = SessionMachine(("tablet-a",))
            machine.attach(accessory())
            machine.control(**message)
            self.assertNotIn("show_display", machine.actions)
            self.assertFalse(machine.display_connected)
            self.assertEqual(machine.phase, "waiting_tablet")

    def test_problem_code_requests_setup_without_retry_loop(self):
        machine = SessionMachine(("tablet-a",))
        broken = accessory(problem_code=28, interface_present=False)
        machine.attach(broken)
        machine.attach(broken)
        self.assertEqual(machine.actions.count("needs_setup"), 1)
        self.assertNotIn("handshake", machine.actions)
        self.assertNotIn("show_display", machine.actions)
        self.assertEqual(machine.phase, "needs_setup")

    def test_required_phases_allow_only_one_session(self):
        machine = SessionMachine(("tablet-a",))
        machine.attach(debug_device())
        self.assertEqual(machine.phase, "waiting_reenumeration")
        machine.attach(accessory())
        self.assertEqual(machine.phase, "waiting_tablet")
        ready(machine)
        self.assertEqual(machine.phase, "running")
        self.assertLess(machine.phases.index("establishing"), machine.phases.index("running"))
        self.assertFalse(machine.display_connected)
        machine.note_keyframe()
        self.assertTrue(machine.display_connected)
        machine.attach(accessory("other-tablet"))
        self.assertIn("reject_ambiguous", machine.actions)
        self.assertTrue(machine.display_connected)
        machine.stop("unplug")
        self.assertIn("cleaning", machine.phases)
        self.assertEqual(machine.phase, "disconnected")
        self.assertFalse(machine.display_connected)
        blocked = SessionMachine(("tablet-a",))
        blocked.attach(accessory(problem_code=28, interface_present=False))
        self.assertEqual(blocked.phase, "needs_setup")
        self.assertNotIn("show_display", blocked.actions)

    def test_can_reconnect_after_cleanup(self):
        machine = SessionMachine(("tablet-a",))
        machine.attach(accessory())
        ready(machine)
        machine.stop("unplug")
        machine.attach(debug_device())
        self.assertEqual(machine.actions.count("handshake"), 1)
        self.assertEqual(machine.phase, "waiting_reenumeration")
        self.assertFalse(machine.display_connected)


if __name__ == "__main__":
    unittest.main()
