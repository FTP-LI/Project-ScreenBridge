"""Developer-only native USB probe. Never installs drivers or uses HDC forwarding."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from accessory_transport import AccessorySelector, choose, open_accessory, run_echo

AOA_IDS = (0x2D00, 0x2D01)
IDENTITY = ("ScreenBridge", "USBProbe", "ScreenBridge M0 echo", "0.1",
            "https://github.com/FTP-LI/Project-ScreenBridge", "m0-prototype")


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


def payload_sizes(value):
    try:
        sizes = tuple(int(part, 10) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("sizes must be comma-separated integers") from error
    if not sizes or any(size < 1 or size > 65536 for size in sizes):
        raise argparse.ArgumentTypeError("each size must be 1..65536")
    return sizes


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "probe", "start", "echo"))
    parser.add_argument("--vid", type=lambda x: int(x, 0), default=0x12D1)
    parser.add_argument("--pid", type=lambda x: int(x, 0), default=0x5000)
    parser.add_argument("--libusb", default=os.environ.get("SCREENBRIDGE_LIBUSB"))
    parser.add_argument("--timeout-ms", type=positive, default=5000)
    parser.add_argument("--count", type=positive, default=100)
    parser.add_argument("--size", type=positive, default=None)
    parser.add_argument("--sizes", type=payload_sizes)
    parser.add_argument("--duration", type=positive, help="echo duration in seconds; overrides count")
    parser.add_argument("--report", type=Path, help="write a redacted JSON report")
    return parser


def parse_args(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.size is not None and args.size > 65536:
        parser.error("--size must be <= 65536")
    if args.command == "echo":
        if args.sizes is not None and args.size is not None:
            parser.error("--sizes cannot be combined with --size")
        if args.sizes is not None and args.duration is not None:
            parser.error("--sizes cannot be combined with --duration")
        if args.sizes is None and args.size is None:
            args.size = 4096
    elif args.sizes is not None:
        parser.error("--sizes is only valid for echo")
    return args


def main(argv=None):
    args = parse_args(argv)
    result = {"command": args.command, "ok": False, "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    device = None
    util = None
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
            result["ok"] = True
        elif args.command == "echo":
            selector = AccessorySelector(tuple((0x18D1, product) for product in AOA_IDS))
            transport = open_accessory(backend, selector)
            result.update(vid=f"{transport.vendor:04x}", pid=f"{transport.product:04x}")
            sizes = args.sizes if args.sizes is not None else (args.size,)
            echo = run_echo(
                transport,
                sizes=sizes,
                count=args.count,
                timeout_ms=args.timeout_ms,
                duration_s=args.duration,
            )
            result.update(
                frames=echo.verified_frames,
                verified_frames=echo.verified_frames,
                verified_payload_bytes=echo.verified_payload_bytes,
                elapsed_seconds=round(echo.elapsed_seconds, 4),
            )
            if len(sizes) == 1:
                result["payload_bytes_each"] = sizes[0]
                if echo.elapsed_seconds > 0:
                    result["roundtrip_payload_mib_per_second"] = round(
                        2 * echo.verified_payload_bytes / echo.elapsed_seconds / 1048576, 4)
            else:
                result["payload_sizes"] = list(sizes)
                result["count_per_size"] = args.count
            if echo.error_type:
                result["error_type"] = echo.error_type
            result["ok"] = echo.ok
        else:
            device = choose(usb.core.find(find_all=True, backend=backend, idVendor=args.vid, idProduct=args.pid))
            result.update(vid=f"{device.idVendor:04x}", pid=f"{device.idProduct:04x}")
            if args.command == "probe":
                result["protocol_version"] = protocol_version(device, args.timeout_ms)
                if result["protocol_version"] not in (1, 2):
                    raise RuntimeError("device did not report supported accessory protocol")
            else:
                result["protocol_version"] = start_accessory(device, args.timeout_ms)
                result["note"] = "START request completed; re-enumeration and application access still require verification"
            result["ok"] = True
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error))
        result["hint"] = "If access is denied, release HDC and check this USB identity's driver. No driver was installed by this tool."
    finally:
        if device is not None and util is not None:
            try:
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
