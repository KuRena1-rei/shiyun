# tests/test_crypto.py
"""Tests for password encryption (DPAPI)."""


def test_encrypt_decrypt_roundtrip():
    """Encrypted password should decrypt back to original."""
    from core.crypto import encrypt_password, decrypt_password
    pwd = "MyS3cretP@ssw0rd!你好"
    encrypted = encrypt_password(pwd)
    assert encrypted != pwd
    assert encrypted.startswith("DPAPI:")
    assert decrypt_password(encrypted) == pwd


def test_empty_password():
    """Empty password should pass through unchanged."""
    from core.crypto import encrypt_password, decrypt_password
    assert encrypt_password("") == ""
    assert decrypt_password("") == ""


def test_is_encrypted():
    """Should correctly identify DPAPI-encrypted strings."""
    from core.crypto import encrypt_password, is_encrypted
    assert is_encrypted("DPAPI:somedata") is True
    assert is_encrypted("plaintext") is False
    assert is_encrypted("") is False
    assert is_encrypted(encrypt_password("test")) is True


def test_legacy_plaintext_passthrough():
    """Legacy plaintext passwords should pass through decrypt unchanged."""
    from core.crypto import decrypt_password
    assert decrypt_password("legacy_password") == "legacy_password"
