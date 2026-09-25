"""At-rest encryption for anything that contains un-redacted client text.

Rule of thumb for the data directory: plaintext files may only ever hold *redacted*
text; original uploads, original parsed documents, redaction reviews and mappings are
written through this module.

Key resolution:
* ``REDACTION_KEY`` (a Fernet key, ``Fernet.generate_key()``) from the environment.
* In development, when it is missing, a key is generated once and kept at
  ``DATA_DIR/.redaction_key`` (mode 0600). Production and staging refuse to start
  without an explicit key so a redeploy cannot silently lose access to stored files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from configs.settings import DATA_DIR, REDACTION_KEY

_DEV_KEY_FILE = DATA_DIR / ".redaction_key"
_FERNET: Optional[Fernet] = None


class EncryptionUnavailable(RuntimeError):
    pass


def _production_like() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in {"production", "staging", "prod"}


def _load_key() -> bytes:
    if REDACTION_KEY:
        return REDACTION_KEY.encode("utf-8")
    if _production_like():
        raise EncryptionUnavailable("REDACTION_KEY must be set when APP_ENV=production/staging.")
    if _DEV_KEY_FILE.exists():
        return _DEV_KEY_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
    key = Fernet.generate_key()
    _DEV_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DEV_KEY_FILE.write_text(key.decode("utf-8"), encoding="utf-8")
    try:
        os.chmod(_DEV_KEY_FILE, 0o600)
    except OSError:
        pass
    return key


def get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        _FERNET = Fernet(_load_key())
    return _FERNET


def reset_for_tests() -> None:
    """Forget the cached key (tests that monkeypatch DATA_DIR / REDACTION_KEY call this)."""
    global _FERNET
    _FERNET = None


def encrypt_bytes(data: bytes) -> bytes:
    return get_fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return get_fernet().decrypt(token)
    except InvalidToken as exc:
        raise EncryptionUnavailable("stored file cannot be decrypted with the configured REDACTION_KEY") from exc


def encrypt_json(payload: Any) -> bytes:
    return encrypt_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def decrypt_json(token: bytes) -> Any:
    return json.loads(decrypt_bytes(token).decode("utf-8"))


def write_encrypted(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(encrypt_bytes(data))
    os.replace(tmp, path)


def read_encrypted(path: Path) -> bytes:
    return decrypt_bytes(Path(path).read_bytes())


def write_encrypted_json(path: Path, payload: Any) -> None:
    write_encrypted(path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def read_encrypted_json(path: Path) -> Any:
    return json.loads(read_encrypted(path).decode("utf-8"))


__all__ = [
    "EncryptionUnavailable",
    "decrypt_bytes",
    "decrypt_json",
    "encrypt_bytes",
    "encrypt_json",
    "get_fernet",
    "read_encrypted",
    "read_encrypted_json",
    "reset_for_tests",
    "write_encrypted",
    "write_encrypted_json",
]
