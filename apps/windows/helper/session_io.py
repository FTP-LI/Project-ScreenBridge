"""Stop a blocked helper transfer without counting it as a good frame.

The fake transport used in tests unblocks when the gate is stopped.
A real WinUSB read still has to use a cancelable request before this can be
treated as proven on a device.
"""
import threading

from device_watch import apply_presence
from session_machine import STOP_REASONS


class TransferStopped(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class TransferGate:
    def __init__(self):
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self.reason = None

    def stop(self, reason):
        if reason not in STOP_REASONS:
            raise ValueError("unknown stop reason")
        with self._lock:
            if self.reason is None:
                self.reason = reason
        self._stopped.set()

    def raise_if_stopped(self):
        if self._stopped.is_set():
            raise TransferStopped(self.reason)

    def wait(self, timeout_ms):
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer")
        return self._stopped.wait(timeout_ms / 1000)


def wait_for_frame(gate, timeout_ms):
    gate.raise_if_stopped()
    if gate.wait(timeout_ms):
        gate.raise_if_stopped()
    raise TimeoutError("frame deadline expired")


def run_cancellable(transport, exchange, gate):
    verified = 0
    error_type = None
    try:
        while True:
            gate.raise_if_stopped()
            exchange(verified)
            verified += 1
    except Exception as error:
        error_type = type(error).__name__
    finally:
        transport.close()
    return verified, error_type


def interrupt_for_removal(machine, transport, gate, kind, device):
    closing = kind == "remove" and machine.device_key == device.key and machine.phase != "disconnected"
    apply_presence(machine, kind, device)
    if closing:
        gate.stop("unplug")
        transport.close()
