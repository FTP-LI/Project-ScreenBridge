"""Presence watch that subscribes before it enumerates.

Duplicate arrival notifications for a device that is already present are ignored.
Removal of that device allows a later arrival to be delivered again.
Notifications may arrive on another thread; the watch does not open USB itself.
"""
import threading


class DeviceWatch:
    def __init__(self, subscribe, enumerate_present):
        self._subscribe = subscribe
        self._enumerate_present = enumerate_present
        self._unsubscribe = None
        self._queue = None
        self._present = set()
        self._lock = threading.RLock()
        self.events = []

    def start(self):
        with self._lock:
            if self._unsubscribe is not None or self._queue is not None:
                return
            self._present.clear()
            self._queue = []
        self._unsubscribe = self._subscribe(self._on_notification)
        snapshot = tuple(self._enumerate_present())
        with self._lock:
            queued = tuple(self._queue)
            self._queue = None
        for device in snapshot:
            self._arrive(device)
        for kind, device in queued:
            self._apply(kind, device)

    def stop(self):
        with self._lock:
            unsubscribe = self._unsubscribe
            self._unsubscribe = None
            self._queue = None
        if unsubscribe is not None:
            unsubscribe()

    def _on_notification(self, kind, device):
        with self._lock:
            if self._queue is not None:
                self._queue.append((kind, device))
                return
        self._apply(kind, device)

    def _apply(self, kind, device):
        if kind == "arrive":
            self._arrive(device)
            return
        if kind == "remove":
            self._remove(device)
            return
        raise ValueError("unknown presence kind")

    def _arrive(self, device):
        with self._lock:
            if device.key in self._present:
                return
            self._present.add(device.key)
            self.events.append(("arrive", device))

    def _remove(self, device):
        with self._lock:
            if device.key not in self._present:
                return
            self._present.remove(device.key)
            self.events.append(("remove", device))


def apply_presence(machine, kind, device):
    if kind == "arrive":
        machine.attach(device)
        return
    if kind == "remove":
        if machine.device_key == device.key and machine.phase != "disconnected":
            machine.stop("unplug")
        return
    raise ValueError("unknown presence kind")
