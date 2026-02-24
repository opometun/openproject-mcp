from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _derive_key(raw: str) -> bytes:
    """
    Derive an AES key from the env value.
    Accepted formats:
      - "hex:<hexstring>" -> decode hexstring
      - "utf8:<string>"   -> UTF-8 encode string
    """
    if raw.startswith("hex:"):
        key_bytes = bytes.fromhex(raw[len("hex:") :])
    elif raw.startswith("utf8:"):
        key_bytes = raw[len("utf8:") :].encode("utf-8")
    else:
        # default to utf8 for backward compatibility
        key_bytes = raw.encode("utf-8")
    if len(key_bytes) not in (16, 24, 32):
        raise ValueError("token_encryption_key must be 16/24/32 bytes (or hex)")
    return key_bytes


def encrypt_token(token: str, key: str) -> str:
    k = _derive_key(key)
    aes = AESGCM(k)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, token.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("utf-8")


def decrypt_token(ciphertext: str, key: str) -> str:
    raw = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
    nonce, ct = raw[:12], raw[12:]
    k = _derive_key(key)
    aes = AESGCM(k)
    pt = aes.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


__all__ = ["encrypt_token", "decrypt_token"]
