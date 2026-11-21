"""Versioned stdlib scrypt; bounded CPU/RAM work, no password logging."""

import hashlib
import hmac
import secrets
from threading import BoundedSemaphore

_WORK = BoundedSemaphore(2)
PREFIX = "scrypt$131072$8$1$"


class HashBusy(RuntimeError):
    pass


def derive(password, salt):
    if not _WORK.acquire(blocking=False):
        raise HashBusy("password_work_busy")
    try:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=131072,
            r=8,
            p=1,
            maxmem=256 * 1024 * 1024,
            dklen=32,
        )
    finally:
        _WORK.release()


def encode_password(password):
    salt = secrets.token_bytes(16)
    return PREFIX + salt.hex() + "$" + derive(password, salt).hex()


def verify_password(password, encoded):
    valid = False
    salt, expected = bytes(16), bytes(32)
    if encoded.startswith(PREFIX):
        try:
            salt_hex, digest_hex = encoded[len(PREFIX) :].split("$")
            salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
            valid = len(salt) == 16 and len(expected) == 32
        except ValueError:
            pass
    if not valid:
        salt, expected = bytes(16), bytes(32)
    actual = derive(password, salt)
    return hmac.compare_digest(actual, expected) and valid
