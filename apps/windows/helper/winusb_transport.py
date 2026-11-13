"""Small WinUSB transport seam for the helper prototype.

The real backend is intentionally isolated behind ``WinUsbBackend`` so the
session lifecycle can be tested without opening a device. The native backend
uses overlapped WinUSB I/O and cancels pending requests during ``close``.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

SCREENBRIDGE_INTERFACE_GUID = "{331c44be-387b-4621-84a7-f55422e41cfc}"
ERROR_IO_PENDING = 997
ERROR_OPERATION_ABORTED = 995
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
WAIT_FAILED = 0xFFFFFFFF
PIPE_BULK = 2
PIPE_IN = 0x80


class TransportClosed(RuntimeError):
    """Raised when a caller uses a transport after close."""


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _USB_INTERFACE_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_ubyte),
        ("bDescriptorType", ctypes.c_ubyte),
        ("bInterfaceNumber", ctypes.c_ubyte),
        ("bAlternateSetting", ctypes.c_ubyte),
        ("bNumEndpoints", ctypes.c_ubyte),
        ("bInterfaceClass", ctypes.c_ubyte),
        ("bInterfaceSubClass", ctypes.c_ubyte),
        ("bInterfaceProtocol", ctypes.c_ubyte),
        ("iInterface", ctypes.c_ubyte),
    ]


class _WINUSB_PIPE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PipeType", ctypes.c_ubyte),
        ("PipeId", ctypes.c_ubyte),
        ("MaximumPacketSize", wintypes.USHORT),
        ("Interval", ctypes.c_ubyte),
        ("MaximumBytesPerInterval", wintypes.ULONG),
    ]


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


def _guid_from_string() -> _GUID:
    # This is the fixed interface GUID from docs/CONTRACT.md; keeping the
    # fields explicit avoids a platform-specific UUID package dependency.
    return _GUID(
        0x331C44BE,
        0x387B,
        0x4621,
        (ctypes.c_ubyte * 8)(0x84, 0xA7, 0xF5, 0x54, 0x22, 0xE4, 0x1C, 0xFC),
    )


def enumerate_interface_paths() -> list[str]:
    """Return present ScreenBridge WinUSB interface paths.

    This read-only enumeration is deliberately separate from ``open`` so the
    caller can reject zero or ambiguous devices before any I/O is attempted.
    """
    if os.name != "nt":
        raise OSError("WinUSB transport requires Windows")
    cfgmgr = ctypes.WinDLL("cfgmgr32", use_last_error=True)
    cfgmgr.CM_Get_Device_Interface_List_SizeW.argtypes = [
        ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(_GUID),
        wintypes.LPCWSTR, wintypes.ULONG,
    ]
    cfgmgr.CM_Get_Device_Interface_List_SizeW.restype = wintypes.DWORD
    cfgmgr.CM_Get_Device_Interface_ListW.argtypes = [
        ctypes.POINTER(_GUID), wintypes.LPCWSTR, wintypes.LPWSTR,
        wintypes.ULONG, wintypes.ULONG,
    ]
    cfgmgr.CM_Get_Device_Interface_ListW.restype = wintypes.DWORD
    guid = _guid_from_string()
    length = wintypes.ULONG(0)
    status = cfgmgr.CM_Get_Device_Interface_List_SizeW(
        ctypes.byref(length), ctypes.byref(guid), None, 0,
    )
    if status != 0:
        raise OSError(f"CM_Get_Device_Interface_List_SizeW failed: {status}")
    if length.value <= 1:
        return []
    buffer = ctypes.create_unicode_buffer(length.value)
    status = cfgmgr.CM_Get_Device_Interface_ListW(
        ctypes.byref(guid), None, buffer, length.value, 0,
    )
    if status != 0:
        raise OSError(f"CM_Get_Device_Interface_ListW failed: {status}")
    return [item for item in buffer[:length.value].split("\0") if item]


class _CtypesWinUsbBackend:
    def __init__(self):
        if os.name != "nt":
            raise OSError("WinUSB transport requires Windows")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._winusb = ctypes.WinDLL("winusb", use_last_error=True)
        self._configure_api()

    def _configure_api(self):
        k = self._kernel32
        w = self._winusb
        k.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        k.CreateFileW.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateEventW.restype = wintypes.HANDLE
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED), ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
        k.GetOverlappedResult.restype = wintypes.BOOL
        k.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED)]
        k.CancelIoEx.restype = wintypes.BOOL
        w.WinUsb_Initialize.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE)]
        w.WinUsb_Initialize.restype = wintypes.BOOL
        w.WinUsb_Free.argtypes = [wintypes.HANDLE]
        w.WinUsb_Free.restype = wintypes.BOOL
        w.WinUsb_QueryInterfaceSettings.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, ctypes.POINTER(_USB_INTERFACE_DESCRIPTOR)]
        w.WinUsb_QueryInterfaceSettings.restype = wintypes.BOOL
        w.WinUsb_QueryPipe.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, ctypes.c_ubyte, ctypes.POINTER(_WINUSB_PIPE_INFORMATION)]
        w.WinUsb_QueryPipe.restype = wintypes.BOOL
        w.WinUsb_ReadPipe.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(_OVERLAPPED)]
        w.WinUsb_ReadPipe.restype = wintypes.BOOL
        w.WinUsb_WritePipe.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(_OVERLAPPED)]
        w.WinUsb_WritePipe.restype = wintypes.BOOL
        w.WinUsb_AbortPipe.argtypes = [wintypes.HANDLE, ctypes.c_ubyte]
        w.WinUsb_AbortPipe.restype = wintypes.BOOL

    def _last_error(self, operation: str) -> OSError:
        return OSError(ctypes.get_last_error(), operation)

    def open(self, path):
        k, w = self._kernel32, self._winusb
        handle = k.CreateFileW(path, 0xC0000000, 0x00000003, None, 3, 0x40000000, None)
        if handle in (None, wintypes.HANDLE(-1).value):
            raise self._last_error("CreateFileW")
        interface = wintypes.HANDLE()
        try:
            if not w.WinUsb_Initialize(handle, ctypes.byref(interface)):
                raise self._last_error("WinUsb_Initialize")
            descriptor = _USB_INTERFACE_DESCRIPTOR()
            if not w.WinUsb_QueryInterfaceSettings(interface, 0, ctypes.byref(descriptor)):
                raise self._last_error("WinUsb_QueryInterfaceSettings")
            in_pipe = out_pipe = None
            for index in range(descriptor.bNumEndpoints):
                pipe = _WINUSB_PIPE_INFORMATION()
                if not w.WinUsb_QueryPipe(interface, 0, index, ctypes.byref(pipe)):
                    raise self._last_error("WinUsb_QueryPipe")
                if pipe.PipeType != PIPE_BULK:
                    continue
                if pipe.PipeId & PIPE_IN:
                    in_pipe = pipe.PipeId
                else:
                    out_pipe = pipe.PipeId
            if in_pipe is None or out_pipe is None:
                raise OSError("ScreenBridge interface has no bulk IN/OUT pair")
            return {"file": handle, "interface": interface, "in_pipe": in_pipe, "out_pipe": out_pipe, "closed": False, "lock": threading.Lock()}
        except Exception:
            if interface:
                w.WinUsb_Free(interface)
            k.CloseHandle(handle)
            raise

    def _transfer(self, session, pipe_id, data, timeout_ms, write):
        with session["lock"]:
            if session["closed"]:
                raise TransportClosed("transport is closed")
        buffer = ctypes.create_string_buffer(data if write else int(data))
        length = len(data) if write else int(data)
        transferred = wintypes.ULONG(0)
        event = self._kernel32.CreateEventW(None, True, False, None)
        if not event:
            raise self._last_error("CreateEventW")
        overlapped = _OVERLAPPED(hEvent=event)
        try:
            call = self._winusb.WinUsb_WritePipe if write else self._winusb.WinUsb_ReadPipe
            pointer = ctypes.cast(buffer, ctypes.c_void_p)
            ok = call(session["interface"], pipe_id, pointer, length, ctypes.byref(transferred), ctypes.byref(overlapped))
            if not ok:
                error = ctypes.get_last_error()
                if error != ERROR_IO_PENDING:
                    raise OSError(error, "WinUsb transfer")
            wait_status = self._kernel32.WaitForSingleObject(event, timeout_ms)
            if wait_status == WAIT_TIMEOUT:
                self._kernel32.CancelIoEx(session["file"], ctypes.byref(overlapped))
                self._winusb.WinUsb_AbortPipe(session["interface"], pipe_id)
                self._kernel32.WaitForSingleObject(event, 1000)
                raise TimeoutError("WinUSB transfer timed out")
            if wait_status == WAIT_FAILED:
                raise self._last_error("WaitForSingleObject")
            if not self._kernel32.GetOverlappedResult(session["file"], ctypes.byref(overlapped), ctypes.byref(transferred), False):
                error = ctypes.get_last_error()
                if error == ERROR_OPERATION_ABORTED:
                    raise TimeoutError("WinUSB transfer cancelled")
                raise OSError(error, "GetOverlappedResult")
            if write:
                return int(transferred.value)
            return bytes(buffer.raw[:transferred.value])
        finally:
            self._kernel32.CloseHandle(event)

    def read(self, session, pipe_id, size, timeout_ms):
        return self._transfer(session, pipe_id, size, timeout_ms, False)

    def write(self, session, pipe_id, data, timeout_ms):
        return self._transfer(session, pipe_id, bytes(data), timeout_ms, True)

    def close(self, session):
        with session["lock"]:
            if session["closed"]:
                return
            session["closed"] = True
        self._kernel32.CancelIoEx(session["file"], None)
        self._winusb.WinUsb_AbortPipe(session["interface"], session["in_pipe"])
        self._winusb.WinUsb_AbortPipe(session["interface"], session["out_pipe"])
        self._winusb.WinUsb_Free(session["interface"])
        self._kernel32.CloseHandle(session["file"])


class WinUsbTransport:
    def __init__(self, backend, session, in_pipe, out_pipe):
        self._backend = backend
        self._session = session
        self._in_pipe = in_pipe
        self._out_pipe = out_pipe
        self._closed = False
        self._lock = threading.Lock()

    @classmethod
    def open(cls, interface_path: str, *, backend=None):
        if not isinstance(interface_path, str) or not interface_path:
            raise ValueError("interface_path must be non-empty")
        backend = backend or _CtypesWinUsbBackend()
        session, in_pipe, out_pipe = backend.open(interface_path)
        return cls(backend, session, in_pipe, out_pipe)

    @classmethod
    def open_first(cls, interface_paths, *, backend=None):
        paths = list(interface_paths)
        if len(paths) != 1:
            raise RuntimeError(f"expected exactly one ScreenBridge interface, found {len(paths)}")
        return cls.open(paths[0], backend=backend)

    def _ensure_open(self):
        with self._lock:
            if self._closed:
                raise TransportClosed("transport is closed")

    def read(self, size: int, timeout_ms: int) -> bytes:
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("size must be a positive integer")
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer")
        self._ensure_open()
        return self._backend.read(self._session, self._in_pipe, size, timeout_ms)

    def write(self, data: bytes, timeout_ms: int) -> int:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer")
        self._ensure_open()
        return self._backend.write(self._session, self._out_pipe, bytes(data), timeout_ms)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._backend.close(self._session)
