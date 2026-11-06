import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows" / "helper"))

from device_watch import DeviceWatch, apply_presence
from session_machine import DeviceSeen, SessionMachine


def accessory(key="tablet-a"):
    return DeviceSeen(key, 0x18D1, 0x2D00, 0, True)


class Bus:
    def __init__(self, present, early=()):
        self.present = list(present)
        self.early = list(early)
        self.order = []
        self.callback = None
        self.stopped = 0

    def subscribe(self, callback):
        self.order.append("subscribe")
        self.callback = callback
        for kind, device in self.early:
            callback(kind, device)
        return self.stop

    def enumerate_present(self):
        self.order.append("enumerate")
        return list(self.present)

    def stop(self):
        self.stopped += 1


class DeviceWatchTests(unittest.TestCase):
    def test_late_start_subscribes_before_enumerate_and_reports_existing(self):
        device = accessory()
        bus = Bus([device])
        watch = DeviceWatch(bus.subscribe, bus.enumerate_present)
        watch.start()
        self.assertEqual(bus.order, ["subscribe", "enumerate"])
        self.assertEqual([kind for kind, _ in watch.events], ["arrive"])
        self.assertIs(watch.events[0][1], device)

    def test_arrival_during_subscribe_is_not_repeated_by_snapshot(self):
        device = accessory()
        bus = Bus([device], early=(("arrive", device),))
        watch = DeviceWatch(bus.subscribe, bus.enumerate_present)
        watch.start()
        self.assertEqual(watch.events, [("arrive", device)])

    def test_duplicate_notification_and_replug_after_removal(self):
        device = accessory()
        bus = Bus([])
        watch = DeviceWatch(bus.subscribe, bus.enumerate_present)
        watch.start()
        bus.callback("arrive", device)
        bus.callback("arrive", device)
        bus.callback("remove", device)
        bus.callback("remove", device)
        bus.callback("arrive", device)
        self.assertEqual(
            [kind for kind, item in watch.events],
            ["arrive", "remove", "arrive"],
        )
        self.assertTrue(all(item is device for _, item in watch.events))

    def test_stop_unsubscribes_once(self):
        bus = Bus([])
        watch = DeviceWatch(bus.subscribe, bus.enumerate_present)
        watch.start()
        watch.stop()
        watch.stop()
        self.assertEqual(bus.stopped, 1)

    def test_presence_feeds_one_session_and_unplug_cleans_it(self):
        device = accessory()
        other = accessory("other-tablet")
        machine = SessionMachine(("tablet-a",))
        bus = Bus([device])
        watch = DeviceWatch(bus.subscribe, bus.enumerate_present)
        watch.start()
        for kind, item in watch.events:
            apply_presence(machine, kind, item)
        apply_presence(machine, "arrive", device)
        apply_presence(machine, "remove", other)
        self.assertEqual(machine.phase, "waiting_tablet")
        self.assertEqual(machine.actions.count("handshake"), 0)
        apply_presence(machine, "remove", device)
        apply_presence(machine, "remove", device)
        self.assertEqual(machine.phase, "disconnected")
        self.assertEqual(machine.actions.count("cleanup"), 1)
        self.assertFalse(machine.display_connected)


if __name__ == "__main__":
    unittest.main()
