import pytest
from openproject_mcp.transports.http.errors import TokenNotLinkedError
from openproject_mcp.transports.http.op_token_provider import OpenProjectTokenProvider
from openproject_mcp.transports.http.token_crypto import decrypt_token, encrypt_token
from openproject_mcp.transports.http.token_store import (
    MemoryTokenStore,
    principal_from_api_key,
)

cryptography = pytest.importorskip("cryptography")


def test_encrypt_decrypt_utf8_key():
    key = "utf8:0123456789abcdef0123456789abcdef"  # 32 bytes
    ct = encrypt_token("hello", key)
    assert decrypt_token(ct, key) == "hello"


def test_encrypt_decrypt_hex_key():
    key = "hex:" + "00" * 16  # 16 bytes
    ct = encrypt_token("world", key)
    assert decrypt_token(ct, key) == "world"


def test_principal_hash_stable():
    p1 = principal_from_api_key("abc")
    p2 = principal_from_api_key("abc")
    assert p1 == p2
    assert p1[0] == "api-key"
    # Different keys produce different principals
    p3 = principal_from_api_key("xyz")
    assert p3 != p1
    # Digest is a hex string of expected length (SHA-256 = 64 hex chars)
    assert len(p1[1]) == 64


def test_memory_store_with_encryption():
    store = MemoryTokenStore(enc_key="utf8:0123456789abcdef0123456789abcdef")
    princ = ("iss", "sub")
    store.set(princ, "tok123", "http://x")
    record = store.get(princ)
    assert record.api_token == "tok123"
    assert record.base_url == "http://x"


def test_op_token_provider_precedence_and_error():
    store = MemoryTokenStore()
    provider = OpenProjectTokenProvider(store, env_api_key=None, env_base_url=None)
    princ = ("iss", "sub")
    with pytest.raises(TokenNotLinkedError):
        provider.resolve(princ, None)
    # fallback works
    api, base = provider.resolve(princ, "fallback")
    assert api == "fallback"
    assert base is None
    # stored token wins over fallback
    store.set(princ, "stored", "http://y")
    api2, base2 = provider.resolve(princ, "fallback")
    assert api2 == "stored"
    assert base2 == "http://y"
