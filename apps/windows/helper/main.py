"""Dependency-injected helper runtime.

This is the orchestration seam for the future native helper. It subscribes to
PnP before enumerating present devices, forwards presence into HostSession,
and keeps pairing persistence outside the device/transport implementations.
It deliberately does not open USB or install drivers itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from device_watch import DeviceWatch
from pairing import PairingStore


class HelperRuntime:
    def __init__(
        self,
        pairing_store: PairingStore,
        subscribe: Callable,
        enumerate_present: Callable[[], Iterable[object]],
        session,
        handshake: Callable[[object], None] | None = None,
    ) -> None:
        self.pairing_store = pairing_store
        self.session = session
        self._handshake = handshake
        self._started = False
        self._watch = DeviceWatch(
            subscribe,
            enumerate_present,
            on_event=self._on_presence,
        )
        self.session.machine.paired_keys = set(pairing_store.keys())

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._watch.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._watch.stop()
        self.session.stop("background")
        self._started = False

    def pair(self, key: str) -> None:
        self.pairing_store.add(key)
        self.session.machine.paired_keys.add(key)

    def forget(self, key: str) -> None:
        self.pairing_store.forget(key)
        self.session.machine.paired_keys.discard(key)

    def _on_presence(self, kind: str, device: object) -> None:
        before = len(self.session.machine.actions)
        self.session.handle(kind, device)
        new_actions = self.session.machine.actions[before:]
        if kind == "arrive" and self._handshake is not None and "handshake" in new_actions:
            self._handshake(device)
