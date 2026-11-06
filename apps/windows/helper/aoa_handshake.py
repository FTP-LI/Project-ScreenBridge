"""AOA handshake logic for the future Windows helper prototype.

The control transfers mirror ``prototypes/usb/host/usb_probe.py`` byte for
byte so the diagnostic CLI and the helper stay interchangeable. This module
never enumerates devices, never installs drivers and never starts HDC: the
caller supplies one already-selected device-like object.

AOA ``START`` only completes the control request. Re-enumeration into the
accessory identity and application access still have to be observed by the
caller; a successful return here is not a live connection.
"""

from __future__ import annotations

from typing import Iterable

AOA_IDS = (0x2D00, 0x2D01)
DEBUG_IDS = frozenset({(0x12D1, 0x5000)})
ACCESSORY_IDS = frozenset({(0x18D1, product) for product in AOA_IDS})
SUPPORTED_VERSIONS = (1, 2)
IDENTITY = (
    "ScreenBridge",
    "USBProbe",
    "ScreenBridge M0 echo",
    "0.1",
    "https://github.com/FTP-LI/Project-ScreenBridge",
    "m0-prototype",
)


class HandshakeError(RuntimeError):
    """Raised for ambiguous devices or unsupported accessory protocols."""


def choose_one(devices: Iterable[object]) -> object:
    """Return the only target device; refuse empty or ambiguous selections."""
    items = list(devices)
    if len(items) != 1:
        raise HandshakeError("expected exactly one target USB device")
    return items[0]


def protocol_version(device: object, timeout_ms: int) -> int:
    """GET_PROTOCOL (0xC0 / 51), read-only."""
    data = bytes(device.ctrl_transfer(0xC0, 51, 0, 0, 2, timeout=timeout_ms))
    if len(data) != 2:
        raise HandshakeError("GET_PROTOCOL returned an invalid length")
    return int.from_bytes(data, "little")


def start_accessory(device: object, timeout_ms: int) -> int:
    """Send identity strings (0x40 / 52) then START (0x40 / 53).

    Returns the negotiated protocol version. Eight control transfers total:
    one GET_PROTOCOL, six identity strings, one START.
    """
    version = protocol_version(device, timeout_ms)
    if version not in SUPPORTED_VERSIONS:
        raise HandshakeError(f"unsupported accessory protocol: {version}")
    for index, value in enumerate(IDENTITY):
        data = value.encode("utf-8") + b"\0"
        sent = device.ctrl_transfer(0x40, 52, 0, index, data, timeout=timeout_ms)
        if sent != len(data):
            raise HandshakeError("incomplete accessory identity transfer")
    device.ctrl_transfer(0x40, 53, 0, 0, b"", timeout=timeout_ms)
    return version


def should_handshake(
    identities: Iterable[tuple[int, int]],
    phase: str,
    actions: Iterable[str],
    already_attempted: bool = False,
) -> bool:
    """Decide whether one AOA handshake may be sent right now.

    Only the debug identity triggers it, and only while the state machine is
    before or waiting for re-enumeration. An accessory identity, an active
    session, an ambiguous set, or a previous attempt all veto the request.
    """
    if already_attempted:
        return False
    ids = set(identities)
    if not ids & DEBUG_IDS:
        return False
    if ids & ACCESSORY_IDS:
        return False
    if phase in {"waiting_tablet", "establishing", "running", "cleaning", "needs_setup"}:
        return False
    return "handshake" in set(actions) or phase in {"discovered", "waiting_reenumeration"}
