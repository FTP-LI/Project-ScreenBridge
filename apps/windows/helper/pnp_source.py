"""Read-only Windows USB presence for the helper.

Enumeration and notification registration do not open the USB interface.
Instance ids stay in this process; published records use a hash as the key.
"""
import ctypes
import hashlib
import re
import threading
from ctypes import wintypes

from session_machine import ACCESSORY_IDS, DEBUG_IDS, DeviceSeen

_USB_IDENTITY = re.compile(r"VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})")
INTERESTED_IDS = DEBUG_IDS | ACCESSORY_IDS
INTERFACE_GUID = (0x331C44BE, 0x387B, 0x4621, (0x84, 0xA7, 0xF5, 0x54, 0x22, 0xE4, 0x1C, 0xFC))
_PRESENT_USB = 0x00000001 | 0x00000100
_DN_HAS_PROBLEM = 0x00000400
_CR_NO_SUCH_DEVICE_INTERFACE = 0x00000037
_INSTANCE_STARTED = 8
_INSTANCE_REMOVED = 9
_INSTANCE_ENUMERATED = 7


def parse_usb_vid_pid(instance_id):
    match = _USB_IDENTITY.search(instance_id or "")
    if match is None:
        return None
    return int(match.group(1), 16), int(match.group(2), 16)


def stable_key(instance_id):
    return hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:16]


def device_from_instance(instance_id, problem_code, interface_present):
    identity = parse_usb_vid_pid(instance_id)
    if identity is None or identity not in INTERESTED_IDS:
        return None
    vendor_id, product_id = identity
    return DeviceSeen(stable_key(instance_id), vendor_id, product_id, problem_code, interface_present)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _FilterInterface(ctypes.Structure):
    _fields_ = [("ClassGuid", _GUID)]


class _FilterHandle(ctypes.Structure):
    _fields_ = [("hTarget", wintypes.HANDLE)]


class _FilterInstance(ctypes.Structure):
    _fields_ = [("InstanceId", wintypes.WCHAR * 200)]


class _FilterUnion(ctypes.Union):
    _fields_ = [
        ("DeviceInterface", _FilterInterface),
        ("DeviceHandle", _FilterHandle),
        ("DeviceInstance", _FilterInstance),
    ]


class _NotifyFilter(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("Flags", wintypes.DWORD),
        ("FilterType", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
        ("u", _FilterUnion),
    ]


_CALLBACK = ctypes.WINFUNCTYPE(
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
)


def _cfg():
    library = ctypes.windll.cfgmgr32
    library.CM_Get_Device_ID_List_SizeW.argtypes = [
        ctypes.POINTER(wintypes.ULONG), wintypes.LPCWSTR, wintypes.ULONG,
    ]
    library.CM_Get_Device_ID_List_SizeW.restype = wintypes.DWORD
    library.CM_Get_Device_ID_ListW.argtypes = [
        wintypes.LPCWSTR, ctypes.c_wchar_p, wintypes.ULONG, wintypes.ULONG,
    ]
    library.CM_Get_Device_ID_ListW.restype = wintypes.DWORD
    library.CM_Locate_DevNodeW.argtypes = [
        ctypes.POINTER(wintypes.DWORD), wintypes.LPCWSTR, wintypes.ULONG,
    ]
    library.CM_Locate_DevNodeW.restype = wintypes.DWORD
    library.CM_Get_DevNode_Status.argtypes = [
        ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG),
        wintypes.DWORD, wintypes.ULONG,
    ]
    library.CM_Get_DevNode_Status.restype = wintypes.DWORD
    library.CM_Get_Device_Interface_List_SizeW.argtypes = [
        ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(_GUID),
        wintypes.LPCWSTR, wintypes.ULONG,
    ]
    library.CM_Get_Device_Interface_List_SizeW.restype = wintypes.DWORD
    library.CM_Register_Notification.argtypes = [
        ctypes.POINTER(_NotifyFilter), ctypes.c_void_p, _CALLBACK,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.CM_Register_Notification.restype = wintypes.DWORD
    library.CM_Unregister_Notification.argtypes = [ctypes.c_void_p]
    library.CM_Unregister_Notification.restype = wintypes.DWORD
    return library


def _check(status, name):
    if status != 0:
        raise OSError(f"{name} failed with CONFIGRET {status}")


def _interface_guid():
    data1, data2, data3, data4 = INTERFACE_GUID
    return _GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4))


def _present_instance_ids():
    library = _cfg()
    length = wintypes.ULONG(0)
    _check(library.CM_Get_Device_ID_List_SizeW(ctypes.byref(length), "USB", _PRESENT_USB),
           "CM_Get_Device_ID_List_SizeW")
    buffer = ctypes.create_unicode_buffer(length.value)
    _check(library.CM_Get_Device_ID_ListW("USB", buffer, length.value, _PRESENT_USB),
           "CM_Get_Device_ID_ListW")
    text = ctypes.wstring_at(ctypes.addressof(buffer), length.value)
    return [item for item in text.split("\0") if item]


def _problem_code(library, instance_id):
    devinst = wintypes.DWORD()
    _check(library.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, 0), "CM_Locate_DevNodeW")
    status = wintypes.ULONG()
    problem = wintypes.ULONG()
    _check(library.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), devinst, 0),
           "CM_Get_DevNode_Status")
    if status.value & _DN_HAS_PROBLEM:
        return int(problem.value)
    return 0


def _interface_present(library, instance_id):
    guid = _interface_guid()
    length = wintypes.ULONG(0)
    status = library.CM_Get_Device_Interface_List_SizeW(ctypes.byref(length), ctypes.byref(guid), instance_id, 0)
    if status == _CR_NO_SUCH_DEVICE_INTERFACE:
        return False
    _check(status, "CM_Get_Device_Interface_List_SizeW")
    return length.value > 1


def list_targets():
    library = _cfg()
    devices = []
    for instance_id in _present_instance_ids():
        if parse_usb_vid_pid(instance_id) not in INTERESTED_IDS:
            continue
        devices.append(device_from_instance(
            instance_id,
            _problem_code(library, instance_id),
            _interface_present(library, instance_id),
        ))
    return devices


def _kind_for_action(action):
    if action == _INSTANCE_ENUMERATED:
        return None
    if action == _INSTANCE_STARTED:
        return "arrive"
    if action == _INSTANCE_REMOVED:
        return "remove"
    return None


def _instance_from_event(event_data, event_size):
    if not event_data or event_size < 10:
        return None
    filter_type = ctypes.c_uint.from_address(event_data).value
    if filter_type != 2:
        return None
    address = event_data + 8
    remaining = max(0, (event_size - 8) // 2)
    if remaining <= 0:
        return None
    return ctypes.wstring_at(address, remaining).split("\0", 1)[0]


def register_instance_notifications(callback):
    """Register before the caller enumerates. The callback is (kind, instance_id)."""
    library = _cfg()
    filt = _NotifyFilter()
    filt.cbSize = ctypes.sizeof(_NotifyFilter)
    filt.Flags = 0x00000002
    filt.FilterType = 2

    def native(notify, context, action, event_data, event_size):
        kind = _kind_for_action(action)
        if kind is None:
            return 0
        instance_id = _instance_from_event(event_data, event_size)
        if instance_id:
            callback(kind, instance_id)
        return 0

    holder = _CALLBACK(native)
    token = ctypes.c_void_p()
    _check(library.CM_Register_Notification(ctypes.byref(filt), None, holder, ctypes.byref(token)),
           "CM_Register_Notification")

    def unsubscribe():
        _check(library.CM_Unregister_Notification(token), "CM_Unregister_Notification")

    unsubscribe._callback = holder
    return unsubscribe


def describe_target(instance_id):
    identity = parse_usb_vid_pid(instance_id)
    if identity not in INTERESTED_IDS:
        return None
    library = _cfg()
    return device_from_instance(
        instance_id,
        _problem_code(library, instance_id),
        _interface_present(library, instance_id),
    )


def subscribe_described(register, describe, callback):
    """Queue raw notifications, then read device status outside that callback."""
    pending = []
    lock = threading.Lock()
    ready = threading.Event()
    stopped = threading.Event()

    def on_instance(kind, instance_id):
        with lock:
            pending.append((kind, instance_id))
        ready.set()

    unsubscribe_native = register(on_instance)

    def loop():
        while True:
            ready.wait(0.05)
            while True:
                with lock:
                    if not pending:
                        ready.clear()
                        if pending:
                            continue
                        break
                    kind, instance_id = pending.pop(0)
                if kind == "remove":
                    device = device_from_instance(instance_id, 0, False)
                else:
                    device = describe(instance_id)
                if device is not None:
                    callback(kind, device)
            if stopped.is_set():
                return

    worker = threading.Thread(target=loop, name="screenbridge-pnp", daemon=True)
    worker.start()

    def unsubscribe():
        stopped.set()
        ready.set()
        worker.join(1)
        unsubscribe_native()

    return unsubscribe


def subscribe_targets(callback):
    return subscribe_described(register_instance_notifications, describe_target, callback)


def public_record(device):
    return {
        "vid": f"{device.vendor_id:04x}",
        "pid": f"{device.product_id:04x}",
        "problem_code": device.problem_code,
        "interface_present": bool(device.interface_present),
    }
