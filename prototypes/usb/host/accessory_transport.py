"""USB accessory selection and checked echo transport.

Enumeration refuses an empty or ambiguous match before any bulk write.
This is a device-count guard for the experiment, not product pairing.
"""
import os
import time

from protocol import FrameReader, encode_frame, verify_echo, write_all

AOA_IDS = ((0x18D1, 0x2D00), (0x18D1, 0x2D01))


def choose(devices):
    devices = list(devices)
    if len(devices) != 1:
        raise RuntimeError(f"expected exactly one matching USB device, found {len(devices)}")
    return devices[0]


class AccessorySelector:
    def __init__(self, allowed_ids, interface_number=0):
        allowed_ids = tuple(allowed_ids)
        if not allowed_ids:
            raise ValueError("allowed_ids must not be empty")
        for item in allowed_ids:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("allowed_ids must contain vendor/product pairs")
        if isinstance(interface_number, bool) or not isinstance(interface_number, int) or interface_number < 0:
            raise ValueError("interface_number must be a non-negative integer")
        self.allowed_ids = allowed_ids
        self.interface_number = interface_number


class EchoResult:
    def __init__(self, ok, verified_frames, verified_payload_bytes, elapsed_seconds, error_type):
        self.ok = bool(ok)
        self.verified_frames = verified_frames
        self.verified_payload_bytes = verified_payload_bytes
        self.elapsed_seconds = elapsed_seconds
        self.error_type = error_type


class AccessoryTransport:
    def __init__(self, reader, writer, releaser, vendor=None, product=None, max_packet=0):
        self._reader = reader
        self._writer = writer
        self._releaser = releaser
        self._closed = False
        self.vendor = vendor
        self.product = product
        self.max_packet = max_packet

    def read(self, size, timeout_ms):
        if self._closed:
            raise RuntimeError("transport is closed")
        return bytes(self._reader(size, timeout_ms))

    def write(self, data, timeout_ms):
        if self._closed:
            raise RuntimeError("transport is closed")
        return int(self._writer(data, timeout_ms))

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._releaser()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False


def open_matching(devices, selector, claim):
    if not isinstance(selector, AccessorySelector):
        raise ValueError("selector is required")
    allowed = set(selector.allowed_ids)
    matched = [device for device in devices if (device.idVendor, device.idProduct) in allowed]
    device = choose(matched)
    return claim(device, selector.interface_number)


def claim_bulk(device, interface_number):
    import usb.util

    interface = device.get_active_configuration()[(interface_number, 0)]
    usb.util.claim_interface(device, interface_number)
    try:
        endpoints = [
            endpoint for endpoint in interface
            if usb.util.endpoint_type(endpoint.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
        ]
        endpoint_in = choose(
            endpoint for endpoint in endpoints
            if usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_IN
        )
        endpoint_out = choose(
            endpoint for endpoint in endpoints
            if usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
    except Exception:
        usb.util.release_interface(device, interface_number)
        usb.util.dispose_resources(device)
        raise

    def release():
        usb.util.release_interface(device, interface_number)
        usb.util.dispose_resources(device)

    return AccessoryTransport(
        lambda size, timeout: endpoint_in.read(size, timeout=timeout),
        lambda data, timeout: endpoint_out.write(data, timeout=timeout),
        release,
        device.idVendor,
        device.idProduct,
        endpoint_out.wMaxPacketSize,
    )


def open_accessory(backend, selector):
    import usb.core

    if not isinstance(selector, AccessorySelector):
        raise ValueError("selector is required")
    allowed = set(selector.allowed_ids)
    found = usb.core.find(
        find_all=True,
        backend=backend,
        custom_match=lambda device: (device.idVendor, device.idProduct) in allowed,
    )
    return open_matching(list(found), selector, claim_bulk)


def _validate_echo(sizes, count, timeout_ms, duration_s):
    sizes = tuple(sizes)
    if not sizes or any(_invalid_size(size) for size in sizes):
        raise ValueError("sizes must each be from 1 to 65536")
    if _invalid_positive(count):
        raise ValueError("count must be positive")
    if _invalid_positive(timeout_ms):
        raise ValueError("timeout_ms must be positive")
    if duration_s is not None and (len(sizes) != 1 or isinstance(duration_s, bool) or duration_s <= 0):
        raise ValueError("duration_s requires exactly one size")
    return sizes


def _invalid_size(size):
    return isinstance(size, bool) or not isinstance(size, int) or size < 1 or size > 65536


def _invalid_positive(value):
    return isinstance(value, bool) or not isinstance(value, int) or value <= 0


def _exchange(transport, sequence, payload, timeout_ms):
    reader = FrameReader(transport.read)
    frame = encode_frame(sequence, payload)
    packet = getattr(transport, "max_packet", 0) or 0
    if packet and len(frame) > 1 and len(frame) % packet == 0:
        write_all(transport.write, frame[:-1], timeout_ms)
        write_all(transport.write, frame[-1:], timeout_ms)
    else:
        write_all(transport.write, frame, timeout_ms)
    verify_echo(sequence, payload, reader.read_frame(timeout_ms))


def run_echo(transport, *, sizes, count, timeout_ms, duration_s=None):
    verified_frames = 0
    verified_payload_bytes = 0
    error_type = None
    ok = False
    started = time.monotonic()
    try:
        sizes = _validate_echo(sizes, count, timeout_ms, duration_s)
        sequence = 0
        if duration_s is not None:
            deadline = time.monotonic() + float(duration_s)
            size = sizes[0]
            while time.monotonic() < deadline:
                payload = os.urandom(size)
                _exchange(transport, sequence, payload, timeout_ms)
                verified_frames += 1
                verified_payload_bytes += size
                sequence = (sequence + 1) & 0xFFFFFFFF
        else:
            for size in sizes:
                for _ in range(count):
                    payload = os.urandom(size)
                    _exchange(transport, sequence, payload, timeout_ms)
                    verified_frames += 1
                    verified_payload_bytes += size
                    sequence = (sequence + 1) & 0xFFFFFFFF
        ok = True
    except Exception as error:
        ok = False
        error_type = type(error).__name__
    finally:
        try:
            transport.close()
        except Exception as error:
            ok = False
            if error_type is None:
                error_type = type(error).__name__
    return EchoResult(ok, verified_frames, verified_payload_bytes, time.monotonic() - started, error_type)
