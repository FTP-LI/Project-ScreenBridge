import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows" / "helper"))

from pairing import PairingError, PairingStore


class PairingStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "pairing.json"

    def test_missing_file_returns_empty(self):
        store = PairingStore(self.path)
        self.assertEqual(store.load(), set())
        self.assertFalse(store.contains("a" * 16))

    def test_add_contains_forget_and_persist(self):
        store = PairingStore(self.path)
        store.add("a" * 16)
        self.assertTrue(store.contains("a" * 16))
        self.assertEqual(store.keys(), frozenset({"a" * 16}))
        reloaded = PairingStore(self.path)
        self.assertEqual(reloaded.load(), {"a" * 16})
        reloaded.forget("a" * 16)
        self.assertFalse(reloaded.contains("a" * 16))
        self.assertEqual(PairingStore(self.path).load(), set())

    def test_corrupt_or_wrong_version_file_degrades_to_empty(self):
        for content in ("{not json", '{"version": 99, "paired_keys": ["a"]}',
                        '{"version": 1, "paired_keys": "a"}', '[]'):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                store = PairingStore(self.path)
                self.assertEqual(store.load(), set())

    def test_atomic_write_leaves_no_temp_file(self):
        store = PairingStore(self.path)
        store.add("b" * 16)
        self.assertFalse((self.path.parent / "pairing.json.tmp").exists())
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data, {"version": 1, "paired_keys": ["b" * 16]})

    def test_rejects_device_path_like_keys(self):
        store = PairingStore(self.path)
        for bad in ("USB\\VID_12D1&PID_5000\\serial", "C:/device/serial", "", "x" * 65, 42, None):
            with self.subTest(bad=bad):
                with self.assertRaises(PairingError):
                    store.add(bad)

    def test_concurrent_adds_are_all_persisted(self):
        store = PairingStore(self.path)
        keys = [f"{i:016x}" for i in range(16)]

        def worker(key):
            store.add(key)

        threads = [threading.Thread(target=worker, args=(key,)) for key in keys]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(PairingStore(self.path).load(), set(keys))


if __name__ == "__main__":
    unittest.main()
