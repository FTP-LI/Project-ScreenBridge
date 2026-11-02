"""Developer-only native USB probe. Never installs drivers or uses HDC forwarding."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from protocol import FrameReader, encode_frame, verify_echo, write_all

AOA_IDS = (0x2D00, 0x2D01)
IDENTITY = ("ScreenBridge", "USBProbe", "ScreenBridge M0 echo", "0.1",
            "https://github.com/FTP-LI/Project-ScreenBridge", "m0-prototype")


def choose(devices):
    devices = list(devices)
    if len(devices) != 1:
        raise RuntimeError(f"expected exactly one matching USB device, found {len(devices)}")
    return devices[0]


def protocol_version(device, timeout):
    data = bytes(device.ctrl_transfer(0xC0, 51, 0, 0, 2, timeout=timeout))
    if len(data) != 2:
        raise RuntimeError("GET_PROTOCOL returned an invalid length")
    return int.from_bytes(data, "little")


def start_accessory(device, timeout):
    version = protocol_version(device, timeout)
    if version not in (1, 2):
        raise RuntimeError(f"unsupported accessory protocol: {version}")
    for index, value in enumerate(IDENTITY):
        data = value.encode("utf-8") + b"\0"
        sent = device.ctrl_transfer(0x40, 52, 0, index, data, timeout=timeout)
        if sent != len(data):
            raise RuntimeError("incomplete accessory identity transfer")
    device.ctrl_transfer(0x40, 53, 0, 0, b"", timeout=timeout)
    return version


def positive(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "probe", "start", "echo"))
    parser.add_argument("--vid", type=lambda x: int(x, 0), default=0x12D1)
    parser.add_argument("--pid", type=lambda x: int(x, 0), default=0x5000)
    parser.add_argument("--libusb", default=os.environ.get("SCREENBRIDGE_LIBUSB"))
    parser.add_argument("--timeout-ms", type=positive, default=5000)
    parser.add_argument("--count", type=positive, default=100)
    parser.add_argument("--size", type=positive, default=4096)
    parser.add_argument("--duration", type=positive, help="echo duration in seconds; overrides count")
    parser.add_argument("--report", type=Path, help="write a redacted JSON report")
    args = parser.parse_args()
    if args.size > 65536:
        parser.error("--size must be <= 65536")
    result = {"command": args.command, "ok": False, "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    device = None
    util = None
    claimed = False
    start = time.monotonic()
    frames = 0
    try:
        import usb.core
        import usb.util
        import usb.backend.libusb1
        util = usb.util
        backend = usb.backend.libusb1.get_backend(find_library=(lambda _: args.libusb) if args.libusb else None)
        if backend is None:
            raise RuntimeError("libusb backend unavailable; specify --libusb with a compatible DLL")
        if args.command == "list":
            result["devices"] = [{"vid": f"{d.idVendor:04x}", "pid": f"{d.idProduct:04x}"}
                                 for d in usb.core.find(find_all=True, backend=backend)
                                 if d.idVendor == args.vid or (d.idVendor == 0x18D1 and d.idProduct in AOA_IDS)]
        else:
            if args.command == "echo":
                device = choose(usb.core.find(find_all=True, backend=backend,
                                custom_match=lambda d: d.idVendor == 0x18D1 and d.idProduct in AOA_IDS))
            else:
                device = choose(usb.core.find(find_all=True, backend=backend, idVendor=args.vid, idProduct=args.pid))
            result.update(vid=f"{device.idVendor:04x}", pid=f"{device.idProduct:04x}")
            if args.command == "probe":
                result["protocol_version"] = protocol_version(device, args.timeout_ms)
                if result["protocol_version"] not in (1, 2):
                    raise RuntimeError("device did not report supported accessory protocol")
            elif args.command == "start":
                result["protocol_version"] = start_accessory(device, args.timeout_ms)
                result["note"] = "START request completed; re-enumeration and application access still require verification"
            else:
                # AOA interface zero is the accessory channel; never claim the debugging interface.
                interface = device.get_active_configuration()[(0, 0)]
                util.claim_interface(device, 0)
                claimed = True
                endpoints = [ep for ep in interface if util.endpoint_type(ep.bmAttributes) == util.ENDPOINT_TYPE_BULK]
                ep_in = choose(ep for ep in endpoints if util.endpoint_direction(ep.bEndpointAddress) == util.ENDPOINT_IN)
                ep_out = choose(ep for ep in endpoints if util.endpoint_direction(ep.bEndpointAddress) == util.ENDPOINT_OUT)
                reader = FrameReader(lambda size, timeout: bytes(ep_in.read(size, timeout=timeout)))
                start = time.monotonic()
                while (time.monotonic() - start < args.duration) if args.duration else (frames < args.count):
                    sequence = frames & 0xFFFFFFFF
                    payload = os.urandom(args.size)
                    write_all(lambda data, timeout: ep_out.write(data, timeout=timeout),
                              encode_frame(sequence, payload), args.timeout_ms)
                    verify_echo(sequence, payload, reader.read_frame(args.timeout_ms))
                    frames += 1
                elapsed = time.monotonic() - start
                result.update(frames=frames, payload_bytes_each=args.size, elapsed_seconds=round(elapsed, 4),
                              roundtrip_payload_mib_per_second=round(2 * frames * args.size / elapsed / 1048576, 4))
        result["ok"] = True
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error), verified_frames=frames)
        result["hint"] = "If access is denied, release HDC and check this USB identity's driver. No driver was installed by this tool."
    finally:
        if device is not None and util is not None:
            try:
                if claimed:
                    util.release_interface(device, 0)
                util.dispose_resources(device)
            except Exception as error:
                result.update(ok=False, cleanup_error=str(error))
    output = json.dumps(result, indent=2, ensure_ascii=False)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
