import contextlib
import io
import unittest

from protocol import encode_frame

from accessory_transport import (
    AccessorySelector,
    open_matching,
    run_echo,
)


class RecordingDevice:
    def __init__(self, vendor, product):
        self.idVendor = vendor
        self.idProduct = product
        self.writes = 0


class ByteTransport:
    """Accepts and returns one byte at a time, echoing written bytes."""

    def __init__(self):
        self.pending = bytearray()
        self.release_count = 0
        self._closed = False

    def write(self, data, timeout_ms):
        if self._closed:
            raise RuntimeError("closed")
        if not data:
            return 0
        self.pending.append(data[0])
        return 1

    def read(self, size, timeout_ms):
        if self._closed:
            raise RuntimeError("closed")
        if not self.pending:
            return b""
        value = bytes(self.pending[:1])
        del self.pending[:1]
        return value

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.release_count += 1


class LoopbackTransport(ByteTransport):
    def write(self, data, timeout_ms):
        if self._closed:
            raise RuntimeError("closed")
        self.pending.extend(data)
        return len(data)

    def read(self, size, timeout_ms):
        if self._closed:
            raise RuntimeError("closed")
        if not self.pending:
            return b""
        count = min(size, len(self.pending))
        value = bytes(self.pending[:count])
        del self.pending[:count]
        return value


class ScriptedReadTransport:
    def __init__(self, frame):
        self.frame = frame
        self.offset = 0
        self.release_count = 0
        self._closed = False
        self.write_count = 0

    def write(self, data, timeout_ms):
        if self._closed:
            raise RuntimeError("closed")
        self.write_count += 1
        return len(data)

    def read(self, size, timeout_ms):
        if self._closed:
            raise RuntimeError("closed")
        if self.offset >= len(self.frame):
            return b""
        end = min(len(self.frame), self.offset + size)
        value = self.frame[self.offset:end]
        self.offset = end
        return value

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.release_count += 1


class DisconnectTransport:
    def __init__(self):
        self.release_count = 0
        self._closed = False
        self.write_count = 0

    def write(self, data, timeout_ms):
        self.write_count += 1
        raise ConnectionError("disconnected")

    def read(self, size, timeout_ms):
        raise ConnectionError("disconnected")

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.release_count += 1


class AccessoryTransportTests(unittest.TestCase):
    def make_loopback_transport(self):
        return LoopbackTransport()

    def test_ambiguous_device_never_writes(self):
        devices = [RecordingDevice(0x18D1, 0x2D00), RecordingDevice(0x18D1, 0x2D00)]
        claimed = []

        def claim(device, interface_number):
            claimed.append((device, interface_number))
            device.writes += 1

        selector = AccessorySelector(((0x18D1, 0x2D00), (0x18D1, 0x2D01)))
        with self.assertRaises(RuntimeError):
            open_matching(devices, selector, claim)
        self.assertEqual(claimed, [])
        self.assertEqual(sum(device.writes for device in devices), 0)
        with self.assertRaises(ValueError):
            AccessorySelector(())
        with self.assertRaises(ValueError):
            open_matching([], None, claim)

    def test_crc_error_is_not_counted_as_verified(self):
        frame = bytearray(encode_frame(0, b"x" * 48))
        frame[-1] ^= 0xFF
        transport = ScriptedReadTransport(bytes(frame))
        result = run_echo(transport, sizes=(48,), count=1, timeout_ms=500)
        self.assertFalse(result.ok)
        self.assertEqual(result.verified_frames, 0)
        self.assertEqual(result.verified_payload_bytes, 0)
        self.assertEqual(result.error_type, "ProtocolError")
        self.assertEqual(transport.release_count, 1)
        transport.close()
        self.assertEqual(transport.release_count, 1)

    def test_partial_io_reconstructs_frame(self):
        transport = ByteTransport()
        result = run_echo(transport, sizes=(48,), count=1, timeout_ms=500)
        self.assertTrue(result.ok)
        self.assertEqual(result.verified_frames, 1)
        self.assertEqual(result.verified_payload_bytes, 48)
        self.assertIsNone(result.error_type)
        self.assertEqual(transport.release_count, 1)
        transport.close()
        self.assertEqual(transport.release_count, 1)

    def test_disconnect_closes_once_and_fails(self):
        transport = DisconnectTransport()
        result = run_echo(transport, sizes=(48,), count=1, timeout_ms=500)
        self.assertFalse(result.ok)
        self.assertEqual(result.verified_frames, 0)
        self.assertEqual(result.error_type, "ConnectionError")
        self.assertEqual(transport.release_count, 1)
        transport.close()
        self.assertEqual(transport.release_count, 1)

    def test_multi_size_count_and_bytes(self):
        transport = self.make_loopback_transport()
        result = run_echo(transport, sizes=(48, 496), count=2, timeout_ms=500)
        self.assertTrue(result.ok)
        self.assertEqual(result.verified_frames, 4)
        self.assertEqual(result.verified_payload_bytes, (48 + 496) * 2)
        transport.close()
        self.assertEqual(transport.release_count, 1)

    def test_duration_rejects_multiple_sizes(self):
        transport = self.make_loopback_transport()
        result = run_echo(transport, sizes=(48, 496), count=1, timeout_ms=500, duration_s=1)
        self.assertFalse(result.ok)
        self.assertEqual(result.verified_frames, 0)
        self.assertEqual(result.verified_payload_bytes, 0)
        self.assertEqual(transport.release_count, 1)

    def test_invalid_sizes_close_safely(self):
        for sizes in ((), (0,), (65537,)):
            transport = self.make_loopback_transport()
            result = run_echo(transport, sizes=sizes, count=1, timeout_ms=500)
            self.assertFalse(result.ok)
            self.assertEqual(result.verified_frames, 0)
            self.assertEqual(transport.release_count, 1)
            transport.close()
            self.assertEqual(transport.release_count, 1)

    def test_exact_packet_frame_ends_with_short_write(self):
        class RecordingTransport:
            def __init__(self):
                self.pending = bytearray()
                self.writes = []
                self.max_packet = 512
                self.release_count = 0
                self._closed = False

            def write(self, data, timeout_ms):
                self.writes.append(bytes(data))
                self.pending.extend(data)
                return len(data)

            def read(self, size, timeout_ms):
                count = min(size, len(self.pending))
                value = bytes(self.pending[:count])
                del self.pending[:count]
                return value

            def close(self):
                if not self._closed:
                    self._closed = True
                    self.release_count += 1

        transport = RecordingTransport()
        result = run_echo(transport, sizes=(496,), count=1, timeout_ms=500)
        self.assertTrue(result.ok)
        self.assertEqual(len(transport.writes[-1]), 1)
        self.assertEqual(sum(len(item) for item in transport.writes), 512)
        self.assertNotIn(b"", transport.writes)

    def test_sizes_reject_explicit_size_or_duration(self):
        from usb_probe import parse_args

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["echo", "--sizes", "48,496", "--size", "64"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["echo", "--sizes", "48,496", "--duration", "2"])

    def test_sizes_do_not_conflict_with_default_size(self):
        from usb_probe import parse_args

        args = parse_args(["echo", "--sizes", "48,496"])
        self.assertIsNone(args.size)
        self.assertEqual(args.sizes, (48, 496))
        self.assertIsNone(args.duration)


if __name__ == "__main__":
    unittest.main()
