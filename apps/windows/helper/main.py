"""Dependency-injected helper runtime.

This is the orchestration seam for the future native helper. It subscribes to
PnP before enumerating present devices, forwards presence into HostSession,
and keeps pairing persistence outside the device/transport implementations.
It opens the configured WinUSB interface for AOA control and SBC1 control
frames; it never installs drivers itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import os
import sys
import threading
from pathlib import Path

_HELPER_DIR = str(Path(__file__).resolve().parent)
if _HELPER_DIR not in sys.path:
    sys.path.insert(0, _HELPER_DIR)

from device_watch import DeviceWatch
from host_session import HostSession
from pairing import PairingStore
from pnp_source import list_targets, subscribe_targets
from session_machine import ACCESSORY_IDS, SessionMachine
from winusb_transport import WinUsbTransport, enumerate_interface_paths

_PROTOCOL_DIR = str(Path(__file__).resolve().parents[3] / "prototypes" / "usb" / "host")
if _PROTOCOL_DIR not in sys.path:
    sys.path.insert(0, _PROTOCOL_DIR)
from protocol import FrameReader


class HelperRuntime:
    def __init__(
        self,
        pairing_store: PairingStore,
        subscribe: Callable,
        enumerate_present: Callable[[], Iterable[object]],
        session,
        handshake: Callable[[object], None] | None = None,
        control_opener: Callable[[], object] | None = None,
    ) -> None:
        self.pairing_store = pairing_store
        self.session = session
        self._handshake = handshake
        self._control_opener = control_opener
        self._control_lock = threading.Lock()
        self._control_transport = None
        self._control_thread = None
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
        self._started = False
        self._watch.stop()
        self._stop_control()
        self.session.stop("background")

    def pair(self, key: str) -> None:
        self.pairing_store.add(key)
        self.session.machine.paired_keys.add(key)

    def forget(self, key: str) -> None:
        self.pairing_store.forget(key)
        self.session.machine.paired_keys.discard(key)

    def _on_presence(self, kind: str, device: object) -> None:
        before = len(self.session.machine.actions)
        self.session.handle(kind, device)
        if kind == "remove":
            self._stop_control()
            return
        if kind == "arrive" and self._should_read_control(device):
            self._start_control()
        new_actions = self.session.machine.actions[before:]
        if kind == "arrive" and self._handshake is not None and "handshake" in new_actions:
            try:
                self._handshake(device)
            except Exception:
                self.session.machine.actions.append("handshake_error")
                self.session.stop("stop")

    def _should_read_control(self, device: object) -> bool:
        return (
            self._control_opener is not None
            and self._started
            and (getattr(device, "vendor_id", 0), getattr(device, "product_id", 0)) in ACCESSORY_IDS
            and bool(getattr(device, "interface_present", False))
            and self.session.machine.phase == "waiting_tablet"
        )

    def _start_control(self) -> None:
        with self._control_lock:
            thread = self._control_thread
            if thread is not None and thread.is_alive():
                return
            thread = threading.Thread(target=self._control_loop, name="screenbridge-control", daemon=True)
            self._control_thread = thread
            thread.start()

    def _control_loop(self) -> None:
        transport = None
        try:
            transport = self._control_opener()
            with self._control_lock:
                if not self._started:
                    transport.close()
                    return
                self._control_transport = transport
            reader = FrameReader(transport.read)
            while self._started and self.session.machine.phase == "waiting_tablet":
                _, payload = reader.read_frame(5000)
                try:
                    from control_message import decode_control
                    message = decode_control(payload)
                except Exception:
                    if hasattr(self.session, "rejected_frames"):
                        self.session.rejected_frames += 1
                    continue
                if message["kind"] in ("ready", "stop"):
                    self._detach_control(transport)
                    transport.close()
                    self.session.accept_frame(payload)
                    return
                self.session.accept_frame(payload)
        except Exception:
            if self._started:
                self.session.machine.actions.append("control_error")
        finally:
            if transport is not None:
                transport.close()
            self._detach_control(transport)

    def _detach_control(self, transport) -> None:
        with self._control_lock:
            if transport is None or self._control_transport is transport:
                self._control_transport = None
            if self._control_thread is threading.current_thread():
                self._control_thread = None

    def _stop_control(self) -> None:
        with self._control_lock:
            transport = self._control_transport
            thread = self._control_thread
            self._control_transport = None
            self._control_thread = None
        if transport is not None:
            transport.close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(1)


def create_aoa_handshake(libusb_path: str | None = None) -> Callable[[object], int]:
    """Build the development AOA callback used before the native C++ port."""
    from aoa_handshake import choose_one, start_accessory

    def handshake(target):
        # Normal-mode devices are bound to the ScreenBridge WinUSB interface.
        # Use WinUsb_ControlTransfer for AOA so the helper does not depend on
        # a libusb filter or on a debug/HDC driver binding.
        if (getattr(target, "vendor_id", 0), getattr(target, "product_id", 0)) == (0x12D1, 0x107E):
            paths = enumerate_interface_paths()
            transport = WinUsbTransport.open_first(paths)

            class WinUsbControlDevice:
                def ctrl_transfer(self, direction, request, value, index, data, timeout):
                    return transport.control_transfer(direction, request, value, index, data, timeout)

            try:
                return start_accessory(WinUsbControlDevice(), 5000)
            finally:
                transport.close()

        import usb.backend.libusb1
        import usb.core

        backend = usb.backend.libusb1.get_backend(
            find_library=(lambda _name: libusb_path) if libusb_path else None,
        )
        if backend is None:
            raise RuntimeError("libusb backend unavailable")
        vendor_id = getattr(target, "vendor_id", 0x12D1)
        product_id = getattr(target, "product_id", 0x5000)
        candidates = usb.core.find(
            find_all=True,
            backend=backend,
            idVendor=vendor_id,
            idProduct=product_id,
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
    return HelperRuntime(
        store, subscribe_targets, list_targets, session, handshake, control_opener=opener
    )
