"""Local pairing store for the Windows helper prototype.

Only opaque ``stable_key`` values (``sha256(instance_id)[:16]``) belong here.
Instance IDs, serial numbers, VID/PID pairs and computer names are never
written to disk; the store lives under the git-ignored ``work/`` directory.

This module does not decide whether a device is paired. ``SessionMachine``
does that during ``attach`` using ``device.key``; ``control()`` does not
consult the pairing store at all.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "work" / "pairing.json"
_MAX_KEY_LENGTH = 64


class PairingError(ValueError):
    """Raised when a caller tries to store something that is not an opaque key."""


def _check_key(key: object) -> str:
    if not isinstance(key, str) or not key or len(key) > _MAX_KEY_LENGTH:
        raise PairingError("pairing key must be a non-empty bounded string")
    if any(ch in key for ch in ("\\", "/", "\x00", "\n", "\r")):
        raise PairingError("pairing key must be an opaque stable_key, not a device path")
    return key


class PairingStore:
    """Thread-safe, atomically persisted set of paired stable keys."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else DEFAULT_PATH
        self._lock = threading.Lock()
        self._keys: set[str] = set()
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        with self._lock:
            self._keys = self._read(self._path)

    @staticmethod
    def _read(path: Path) -> set[str]:
        """Missing or damaged files degrade to an empty set, never a crash."""
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError, UnicodeError):
            return set()
        if not isinstance(data, dict) or data.get("version") != VERSION:
            return set()
        keys = data.get("paired_keys")
        if not isinstance(keys, list):
            return set()
        result: set[str] = set()
        for key in keys:
            try:
                result.add(_check_key(key))
            except PairingError:
                continue
        return result

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": VERSION, "paired_keys": sorted(self._keys)},
            sort_keys=True,
            indent=2,
        ) + "\n"
        tmp = self._path.with_name(self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self._path)

    def load(self) -> set[str]:
        """Re-read from disk and return a copy of the paired keys."""
        self._load()
        with self._lock:
            return set(self._keys)

    def keys(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._keys)

    def contains(self, key: str) -> bool:
        _check_key(key)
        with self._lock:
            return key in self._keys

    def add(self, key: str) -> None:
        _check_key(key)
        with self._lock:
            if key in self._keys:
                return
            self._keys.add(key)
            self._write()

    def forget(self, key: str) -> None:
        _check_key(key)
        with self._lock:
            if key not in self._keys:
                return
            self._keys.discard(key)
            self._write()

    def clear(self) -> None:
        with self._lock:
            if not self._keys:
                return
            self._keys.clear()
            self._write()
