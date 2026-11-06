"""Injectable USB session model for the future Windows helper.

This decides when one paired tablet may move toward a display session.
It does not open USB devices, install drivers, or create a Windows monitor.
"""

DEBUG_IDS = {(0x12D1, 0x5000)}
ACCESSORY_IDS = {(0x18D1, 0x2D00), (0x18D1, 0x2D01)}
SUPPORTED_CONTROL_VERSION = 1
STOP_REASONS = ("unplug", "stop", "background", "read_hang")


class DeviceSeen:
    def __init__(self, key, vendor_id, product_id, problem_code, interface_present):
        self.key = key
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.problem_code = problem_code
        self.interface_present = interface_present


class SessionMachine:
    def __init__(self, paired_keys):
        self.paired_keys = set(paired_keys)
        self.phase = "disconnected"
        self.phases = ["disconnected"]
        self.device_key = None
        self.display_connected = False
        self.actions = []

    def attach(self, device):
        identity = (device.vendor_id, device.product_id)
        if identity not in DEBUG_IDS and identity not in ACCESSORY_IDS:
            self.actions.append("ignore")
            return
        session_active = self.phase not in ("disconnected", "needs_setup")
        if self.device_key is not None and device.key != self.device_key and session_active:
            self.actions.append("reject_ambiguous")
            return
        if self.device_key == device.key and self.phase != "disconnected":
            if self.phase == "waiting_reenumeration" and identity in ACCESSORY_IDS:
                if device.problem_code != 0 or not device.interface_present:
                    self._enter("needs_setup")
                    self.actions.append("needs_setup")
                    return
                if device.key in self.paired_keys:
                    self._enter("waiting_tablet")
            return
        if identity in ACCESSORY_IDS and (device.problem_code != 0 or not device.interface_present):
            self.device_key = device.key
            self._enter("needs_setup")
            self.actions.append("needs_setup")
            return
        if identity in ACCESSORY_IDS and device.key not in self.paired_keys:
            self.actions.append("reject_unpaired")
            return
        if identity in DEBUG_IDS:
            self.device_key = device.key
            self._enter("discovered")
            self._enter("waiting_reenumeration")
            self.actions.append("handshake")
            return
        self.device_key = device.key
        self._enter("waiting_tablet")

    def control(self, *, kind, version, paired, accept):
        if kind == "stop":
            self.stop("stop")
            return
        if self.phase != "waiting_tablet":
            self.actions.append("reject_control")
            return
        if kind != "ready" or version != SUPPORTED_CONTROL_VERSION or not paired or not accept:
            self.actions.append("reject_tablet")
            return
        self._enter("establishing")
        self.actions.append("open_session")
        self._enter("running")

    def note_keyframe(self):
        if self.phase != "running" or self.display_connected:
            return
        self.display_connected = True
        self.actions.append("show_display")

    def stop(self, reason):
        if reason not in STOP_REASONS:
            raise ValueError("unknown stop reason")
        if self.phase == "disconnected":
            return
        showed = self.display_connected
        self._enter("cleaning")
        self.actions.append("cleanup")
        if showed:
            self.display_connected = False
            self.actions.append("hide_display")
        self.device_key = None
        self._enter("disconnected")

    def _enter(self, phase):
        self.phase = phase
        self.phases.append(phase)
