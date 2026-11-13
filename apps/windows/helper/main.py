"""Dependency-injected helper runtime.

This is the orchestration seam for the future native helper. It subscribes to
PnP before enumerating present devices, forwards presence into HostSession,
and keeps pairing persistence outside the device/transport implementations.
It deliberately does not open USB or install drivers itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import os
import sys
from pathlib import Path

_HELPER_DIR = str(Path(__file__).resolve().parent)
if _HELPER_DIR not in sys.path:
    sys.path.insert(0, _HELPER_DIR)

from device_watch import DeviceWatch
from host_session import HostSession
from pairing import PairingStore
from pnp_source import list_targets, subscribe_targets
from session_machine import SessionMachine
from winusb_transport import WinUsbTransport, enumerate_interface_paths


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
            try:
                self._handshake(device)
            except Exception:
                self.session.machine.actions.append("handshake_error")
                self.session.stop("stop")


def create_aoa_handshake(libusb_path: str | None = None) -> Callable[[object], int]:
    """Build the development AOA callback used before the native C++ port."""
    from aoa_handshake import choose_one, start_accessory

    def handshake(_device):
        import usb.backend.libusb1
        import usb.core

        backend = usb.backend.libusb1.get_backend(
            find_library=(lambda _name: libusb_path) if libusb_path else None,
        )
        if backend is None:
            raise RuntimeError("libusb backend unavailable")
        candidates = usb.core.find(
            find_all=True,
            backend=backend,
            idVendor=0x12D1,
            idProduct=0x5000,
        )
        device = choose_one(candidates)
        return start_accessory(device, 5000)

    return handshake


def create_runtime(*, pairing_store=None, handshake=None, transport_opener=None):
    """Create the default Python helper runtime for local U4 validation."""
    store = pairing_store or PairingStore()
    machine = SessionMachine(store.keys())
    opener = transport_opener or (
        lambda: WinUsbTransport.open_first(enumerate_interface_paths())
    )
    session = HostSession(machine, opener)
    if handshake is None:
        handshake = create_aoa_handshake(os.environ.get("SCREENBRIDGE_LIBUSB"))
    return HelperRuntime(store, subscribe_targets, list_targets, session, handshake)
