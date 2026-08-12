from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .types import PkceMaterial

_PREFIX = b"MI1"
_NONCE_BYTES = 12


def state_digest(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def generate_pkce() -> PkceMaterial:
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return PkceMaterial(
        state=state,
        state_hash=state_digest(state),
        verifier=verifier,
        challenge=challenge,
    )


class EnvelopeCrypto:
    def __init__(self, key: bytes, *, key_version: str = "v1") -> None:
        if len(key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        if not key_version:
            raise ValueError("key_version is required")
        self._aead = AESGCM(key)
        self.key_version = key_version

    def seal(self, plaintext: str, *, context: str) -> bytes:
        if not context:
            raise ValueError("context is required")
        nonce = secrets.token_bytes(_NONCE_BYTES)
        ciphertext = self._aead.encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))
        return _PREFIX + nonce + ciphertext

    def open(self, envelope: bytes, *, context: str) -> str:
        if not context:
            raise ValueError("context is required")
        if len(envelope) <= len(_PREFIX) + _NONCE_BYTES or not envelope.startswith(_PREFIX):
            raise ValueError("invalid encrypted envelope")
        nonce_start = len(_PREFIX)
        nonce = envelope[nonce_start:nonce_start + _NONCE_BYTES]
        ciphertext = envelope[nonce_start + _NONCE_BYTES:]
        plaintext = self._aead.decrypt(nonce, ciphertext, context.encode("utf-8"))
        return plaintext.decode("utf-8")
