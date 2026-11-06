import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows" / "helper"))
sys.path.insert(0, str(ROOT / "shared" / "protocol"))

from control_message import decode_control, encode_control
from video_packet import split_access_unit
from host_session import HostSession
from session_io import wait_for_frame
from session_machine import DeviceSeen, SessionMachine


def accessory(key="tablet-a"):
    return DeviceSeen(key, 0x18D1, 0x2D00, 0, True)


class CloseOnce:
    def __init__(self):
        self.release_count = 0
        self._closed = False
        self._lock = threading.Lock()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.release_count += 1


class HostSessionTests(unittest.TestCase):
    def session(self, opener, exchange=None):
        machine = SessionMachine(("tablet-a",))
        return HostSession(machine, opener, exchange), machine

    def test_tablet_not_ready_does_not_open(self):
        opened = []
        session, machine = self.session(lambda: opened.append(1))
        session.handle("arrive", accessory())
        for message in (
            {"kind": "ready", "version": 1, "paired": True, "accept": False},
            {"kind": "ready", "version": 99, "paired": True, "accept": True},
            {"kind": "capability", "version": 1, "paired": True, "accept": True},
        ):
            session.accept_ready(**message)
        session.handle("arrive", accessory("other-tablet"))
        self.assertEqual(opened, [])
        self.assertEqual(machine.phase, "waiting_tablet")
        self.assertNotIn("show_display", machine.actions)

    def test_ready_opens_once_and_removal_closes_once(self):
        transport = CloseOnce()
        opened = []
        started = threading.Event()

        def exchange(sequence):
            started.set()
            wait_for_frame(session.gate, 5000)

        session, machine = self.session(lambda: opened.append(transport) or transport, exchange)
        session.handle("arrive", accessory())
        session.accept_ready(kind="ready", version=1, paired=True, accept=True)
        session.accept_ready(kind="ready", version=1, paired=True, accept=True)
        self.assertTrue(started.wait(1))
        self.assertEqual(opened, [transport])
        self.assertEqual(machine.phase, "running")
        self.assertFalse(machine.display_connected)
        session.deliver(split_access_unit(1, 1, False, b"delta")[0])
        self.assertFalse(machine.display_connected)
        session.deliver(split_access_unit(2, 2, True, b"key")[0])
        self.assertTrue(machine.display_connected)
        self.assertEqual(machine.actions.count("show_display"), 1)
        session.handle("remove", accessory("other-tablet"))
        self.assertEqual(transport.release_count, 0)
        session.handle("remove", accessory())
        self.assertTrue(session.finish(1))
        self.assertEqual(transport.release_count, 1)
        self.assertEqual(machine.phase, "disconnected")
        self.assertEqual(machine.actions.count("hide_display"), 1)
        self.assertFalse(machine.display_connected)

    def test_failed_open_rolls_back_without_a_second_attempt(self):
        opened = []

        def opener():
            opened.append(1)
            raise RuntimeError("open failed")

        session, machine = self.session(opener)
        session.handle("arrive", accessory())
        with self.assertRaises(RuntimeError):
            session.accept_ready(kind="ready", version=1, paired=True, accept=True)
        self.assertEqual(opened, [1])
        self.assertEqual(machine.phase, "disconnected")
        self.assertNotIn("show_display", machine.actions)
        self.assertNotIn("hide_display", machine.actions)
        self.assertFalse(machine.display_connected)
        self.assertIsNone(session.transport)

    def test_bad_or_rejected_control_does_not_open_and_stop_closes(self):
        transport = CloseOnce()
        opened = []
        started = threading.Event()

        def exchange(sequence):
            started.set()
            wait_for_frame(session.gate, 5000)

        session, machine = self.session(lambda: opened.append(transport) or transport, exchange)
        session.handle("arrive", accessory())
        session.accept_frame(b"nope")
        session.accept_frame(encode_control("ready", 99, True, True))
        session.accept_frame(encode_control("capability", 1, True, True))
        session.accept_frame(encode_control("ready", 1, False, True))
        self.assertEqual(opened, [])
        self.assertEqual(session.rejected_frames, 1)
        self.assertEqual(machine.phase, "waiting_tablet")
        ready = encode_control("ready", 1, True, True)
        self.assertEqual(decode_control(ready)["kind"], "ready")
        session.accept_frame(ready)
        self.assertTrue(started.wait(1))
        self.assertEqual(opened, [transport])
        session.accept_frame(encode_control("stop", 1, True, True))
        self.assertTrue(session.finish(1))
        self.assertEqual(transport.release_count, 1)
        self.assertEqual(machine.phase, "disconnected")
        self.assertFalse(machine.display_connected)


if __name__ == "__main__":
    unittest.main()
