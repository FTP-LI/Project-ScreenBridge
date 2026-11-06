import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows" / "helper"))

from session_io import TransferGate, interrupt_for_removal, run_cancellable, wait_for_frame
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


class SessionIoTests(unittest.TestCase):
    def test_stop_unblocks_a_waiting_read_before_the_deadline(self):
        gate = TransferGate()
        transport = CloseOnce()
        started = threading.Event()

        def exchange(sequence):
            started.set()
            wait_for_frame(gate, 5000)

        result = {}

        def worker():
            result["value"] = run_cancellable(transport, exchange, gate)

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(started.wait(1))
        gate.stop("unplug")
        thread.join(1)
        self.assertFalse(thread.is_alive())
        verified, error_type = result["value"]
        self.assertEqual(verified, 0)
        self.assertEqual(error_type, "TransferStopped")
        self.assertEqual(transport.release_count, 1)

    def test_completed_frame_is_kept_when_the_next_read_is_stopped(self):
        gate = TransferGate()
        transport = CloseOnce()
        first_done = threading.Event()

        def exchange(sequence):
            if sequence == 0:
                first_done.set()
                return
            wait_for_frame(gate, 5000)

        result = {}

        def worker():
            result["value"] = run_cancellable(transport, exchange, gate)

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(first_done.wait(1))
        gate.stop("stop")
        thread.join(1)
        self.assertFalse(thread.is_alive())
        verified, error_type = result["value"]
        self.assertEqual(verified, 1)
        self.assertEqual(error_type, "TransferStopped")
        self.assertEqual(transport.release_count, 1)

    def test_removal_of_the_open_device_stops_the_transfer_once(self):
        device = accessory()
        other = accessory("other-tablet")
        machine = SessionMachine(("tablet-a",))
        machine.attach(device)
        machine.control(kind="ready", version=1, paired=True, accept=True)
        self.assertFalse(machine.display_connected)
        machine.note_keyframe()
        gate = TransferGate()
        transport = CloseOnce()
        started = threading.Event()

        def exchange(sequence):
            started.set()
            wait_for_frame(gate, 5000)

        result = {}
        thread = threading.Thread(target=lambda: result.update(value=run_cancellable(transport, exchange, gate)))
        thread.start()
        self.assertTrue(started.wait(1))
        interrupt_for_removal(machine, transport, gate, "remove", other)
        self.assertEqual(machine.phase, "running")
        self.assertEqual(transport.release_count, 0)
        interrupt_for_removal(machine, transport, gate, "remove", device)
        interrupt_for_removal(machine, transport, gate, "remove", device)
        thread.join(1)
        self.assertFalse(thread.is_alive())
        verified, error_type = result["value"]
        self.assertEqual(verified, 0)
        self.assertEqual(error_type, "TransferStopped")
        self.assertEqual(machine.phase, "disconnected")
        self.assertEqual(machine.actions.count("cleanup"), 1)
        self.assertEqual(machine.actions.count("hide_display"), 1)
        self.assertEqual(transport.release_count, 1)

    def test_unknown_stop_reason_does_not_close(self):
        gate = TransferGate()
        transport = CloseOnce()
        with self.assertRaises(ValueError):
            gate.stop("sleep")
        self.assertEqual(transport.release_count, 0)
        gate.raise_if_stopped()


if __name__ == "__main__":
    unittest.main()
