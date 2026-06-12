# core/crypto.py
"""
Password encryption using Windows DPAPI (Data Protection API).
Tied to the current Windows user account — same security level as browser password storage.
No extra dependencies required.
"""
import base64
import ctypes
import ctypes.wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt_protect(data: bytes) -> bytes | None:
    """Encrypt data using DPAPI. Returns encrypted bytes or None on failure."""
    blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = DATA_BLOB()
    if ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    return None


def _crypt_unprotect(data: bytes) -> bytes | None:
    """Decrypt DPAPI-encrypted data. Returns raw bytes or None on failure."""
    blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = DATA_BLOB()
    if ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    return None


def encrypt_password(plaintext: str) -> str:
    """Encrypt a plaintext password. Returns base64-encoded encrypted string."""
    if not plaintext:
        return ""
    encrypted = _crypt_protect(plaintext.encode("utf-8"))
    if encrypted is None:
        return plaintext  # fallback: store as-is if DPAPI fails
    return "DPAPI:" + base64.b64encode(encrypted).decode("ascii")


def decrypt_password(stored: str) -> str:
    """Decrypt a stored password. Handles both DPAPI-encrypted and legacy plaintext."""
    if not stored:
        return ""
    if stored.startswith("DPAPI:"):
        encrypted = base64.b64decode(stored[6:])
        decrypted = _crypt_unprotect(encrypted)
        if decrypted is not None:
            return decrypted.decode("utf-8")
        return ""  # DPAPI decrypt failed (e.g. different user account)
    return stored  # legacy plaintext — return as-is


def is_encrypted(stored: str) -> bool:
    """Check if a stored password is DPAPI-encrypted."""
    return stored.startswith("DPAPI:")


def migrate_password(plaintext: str) -> str:
    """Encrypt a legacy plaintext password for storage."""
    if not plaintext or is_encrypted(plaintext):
        return plaintext
    return encrypt_password(plaintext)
