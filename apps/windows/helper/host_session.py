"""Open one injected transport after the tablet is ready.

The opener is not WinUSB. A failed open rolls the session back, and removal
closes that transport once. The display flag waits for a video keyframe.
This does not claim the live accessory.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "protocol"))

from control_message import ControlError, decode_control
from device_watch import apply_presence
from session_io import TransferGate, interrupt_for_removal, run_cancellable, wait_for_frame
from video_packet import AccessAssembler, VideoPacketError


class HostSession:
    def __init__(self, machine, open_transport, exchange=None):
        self.machine = machine
        self._open = open_transport
        self._exchange = exchange
        self.transport = None
        self.gate = None
        self.verified = 0
        self.error_type = None
        self.rejected_frames = 0
        self.video_errors = 0
        self._video = AccessAssembler(2 * 1024 * 1024)
        self._thread = None

    def deliver(self, packet):
        if self.machine.phase != "running":
            return None
        try:
            message = self._video.push(packet)
        except VideoPacketError:
            self.video_errors += 1
            return None
        if message is not None and message.kind == "frame" and message.keyframe:
            self.machine.note_keyframe()
        return message

    def handle(self, kind, device):
        if kind == "remove" and self.transport is not None and self.gate is not None:
            interrupt_for_removal(self.machine, self.transport, self.gate, kind, device)
            return
        apply_presence(self.machine, kind, device)

    def accept_frame(self, payload):
        try:
            message = decode_control(payload)
        except ControlError:
            self.rejected_frames += 1
            return
        self.accept_ready(**message)

    def _release(self, reason):
        gate = self.gate
        transport = self.transport
        if gate is not None:
            gate.stop(reason)
        if transport is not None:
            transport.close()

    def accept_ready(self, *, kind, version, paired, accept):
        self.machine.control(kind=kind, version=version, paired=paired, accept=accept)
        if kind == "stop":
            self._release("stop")
            return
        if self.machine.phase != "running" or self.transport is not None:
            return
        try:
            transport = self._open()
        except Exception:
            if self.machine.phase != "disconnected":
                self.machine.stop("stop")
            raise
        self.transport = transport
        self.gate = TransferGate()
        exchange = self._exchange or (lambda sequence: wait_for_frame(self.gate, 5000))
        self._thread = threading.Thread(
            target=self._pump,
            args=(transport, exchange, self.gate),
            daemon=True,
        )
        self._thread.start()

    def _pump(self, transport, exchange, gate):
        self.verified, self.error_type = run_cancellable(transport, exchange, gate)

    def finish(self, timeout):
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True
