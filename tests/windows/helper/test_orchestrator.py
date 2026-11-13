import tempfile
import unittest
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows" / "helper"))

from pairing import PairingStore
from session_machine import DeviceSeen
from main import HelperRuntime


class FakeBus:
    def __init__(self, present=()):
        self.present = list(present)
        self.callback = None
        self.unsubscribed = 0

    def subscribe(self, callback):
        self.callback = callback
        return self.unsubscribe

    def enumerate_present(self):
        return list(self.present)

    def unsubscribe(self):
        self.unsubscribed += 1


class FakeSession:
    def __init__(self):
        self.events = []
        self.machine = type("Machine", (), {"paired_keys": set(), "actions": []})()
        self.emit_handshake = False

    def handle(self, kind, device):
        self.events.append((kind, device))
        if self.emit_handshake:
            self.machine.actions.append("handshake")

    def stop(self, reason):
        self.events.append(("stop", reason))


class HelperRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = PairingStore(Path(self.tmp.name) / "pairing.json")
        self.device = DeviceSeen("tablet-a", 0x18D1, 0x2D00, 0, True)

    def test_start_subscribes_before_snapshot_and_forwards_events(self):
        bus = FakeBus([self.device])
        session = FakeSession()
        runtime = HelperRuntime(self.store, bus.subscribe, bus.enumerate_present, session)
        runtime.start()
        self.assertEqual(session.events, [("arrive", self.device)])
        self.assertIsNotNone(bus.callback)
        runtime.stop()
        self.assertEqual(bus.unsubscribed, 1)
        self.assertEqual(session.events[-1], ("stop", "background"))

    def test_pair_and_forget_updates_store_and_session_machine(self):
        runtime = HelperRuntime(self.store, lambda callback: lambda: None, lambda: (), FakeSession())
        runtime.pair("tablet-a")
        self.assertTrue(self.store.contains("tablet-a"))
        self.assertIn("tablet-a", runtime.session.machine.paired_keys)
        runtime.forget("tablet-a")
        self.assertFalse(self.store.contains("tablet-a"))
        self.assertNotIn("tablet-a", runtime.session.machine.paired_keys)

    def test_handshake_callback_only_runs_for_handshake_action(self):
        bus = FakeBus()
        session = FakeSession()
        session.machine.actions = ["handshake"]
        session.emit_handshake = True
        called = []
        runtime = HelperRuntime(self.store, bus.subscribe, bus.enumerate_present, session,
                                handshake=lambda device: called.append(device))
        runtime.start()
        bus.callback("arrive", self.device)
        self.assertEqual(called, [self.device])
        session.machine.actions = ["wait_tablet"]
        session.emit_handshake = False
        bus.callback("arrive", DeviceSeen("tablet-b", 0x18D1, 0x2D00, 0, True))
        self.assertEqual(called, [self.device])

    def test_handshake_failure_stops_session_without_killing_event_path(self):
        bus = FakeBus()
        session = FakeSession()
        session.emit_handshake = True
        runtime = HelperRuntime(
            self.store,
            bus.subscribe,
            bus.enumerate_present,
            session,
            handshake=lambda device: (_ for _ in ()).throw(RuntimeError("handshake failed")),
        )
        runtime.start()
        bus.callback("arrive", self.device)
        self.assertIn(("stop", "stop"), session.events)

    def test_runtime_module_imports_from_repository_package(self):
        result = subprocess.run(
            [sys.executable, "-c", "import apps.windows.helper.main"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
