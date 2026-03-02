"""Tests for envelope encryption service."""
from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("cryptography", reason="cryptography not installed; install with: pip install neuromem[encryption]")

from neuromem.services.encryption import EncryptionService


@pytest.fixture
def key_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def keypair(key_dir):
    priv = os.path.join(key_dir, "private.pem")
    pub = os.path.join(key_dir, "public.pem")
    EncryptionService.generate_keypair(priv, pub)
    return priv, pub


class TestKeyGeneration:
    def test_files_created(self, keypair):
        priv, pub = keypair
        assert os.path.exists(priv)
        assert os.path.exists(pub)

    @pytest.mark.skipif(os.name == "nt", reason="Unix file permissions not supported on Windows")
    def test_private_key_permissions(self, keypair):
        priv, _ = keypair
        mode = oct(os.stat(priv).st_mode)[-3:]
        assert mode == "600"

    def test_creates_parent_dirs(self, key_dir):
        priv = os.path.join(key_dir, "nested", "dir", "private.pem")
        pub = os.path.join(key_dir, "nested", "dir", "public.pem")
        EncryptionService.generate_keypair(priv, pub)
        assert os.path.exists(priv)
        assert os.path.exists(pub)

    def test_passphrase_protected(self, key_dir):
        priv = os.path.join(key_dir, "private_enc.pem")
        pub = os.path.join(key_dir, "public_enc.pem")
        EncryptionService.generate_keypair(priv, pub, passphrase=b"mysecret")
        svc = EncryptionService(pub, priv, passphrase=b"mysecret")
        envelope = svc.encrypt("test")
        assert svc.decrypt(envelope) == "test"


class TestEncryptDecrypt:
    def test_roundtrip_ascii(self, keypair):
        priv, pub = keypair
        svc = EncryptionService(pub, priv)
        plaintext = "Hello, World!"
        envelope = svc.encrypt(plaintext)
        assert svc.decrypt(envelope) == plaintext

    def test_roundtrip_unicode(self, keypair):
        priv, pub = keypair
        svc = EncryptionService(pub, priv)
        plaintext = "用户喜欢打篮球 🏀"
        envelope = svc.encrypt(plaintext)
        assert svc.decrypt(envelope) == plaintext

    def test_roundtrip_long_text(self, keypair):
        priv, pub = keypair
        svc = EncryptionService(pub, priv)
        plaintext = "x" * 10000
        envelope = svc.encrypt(plaintext)
        assert svc.decrypt(envelope) == plaintext

    def test_envelope_structure(self, keypair):
        _, pub = keypair
        svc = EncryptionService(pub)
        envelope = svc.encrypt("test")
        assert "encrypted_dek" in envelope
        assert "nonce" in envelope
        assert "ciphertext" in envelope
        # All values should be base64 strings
        for key in ("encrypted_dek", "nonce", "ciphertext"):
            assert isinstance(envelope[key], str)

    def test_different_ciphertext_each_time(self, keypair):
        _, pub = keypair
        svc = EncryptionService(pub)
        e1 = svc.encrypt("same text")
        e2 = svc.encrypt("same text")
        # Random nonce + DEK means different ciphertext
        assert e1["ciphertext"] != e2["ciphertext"]

    def test_wrong_key_fails(self, key_dir):
        priv1 = os.path.join(key_dir, "priv1.pem")
        pub1 = os.path.join(key_dir, "pub1.pem")
        priv2 = os.path.join(key_dir, "priv2.pem")
        pub2 = os.path.join(key_dir, "pub2.pem")
        EncryptionService.generate_keypair(priv1, pub1)
        EncryptionService.generate_keypair(priv2, pub2)

        svc_encrypt = EncryptionService(pub1)
        svc_decrypt = EncryptionService(private_key_path=priv2)
        envelope = svc_encrypt.encrypt("secret")
        with pytest.raises(Exception):
            svc_decrypt.decrypt(envelope)


class TestErrorHandling:
    def test_encrypt_without_public_key(self, keypair):
        priv, _ = keypair
        svc = EncryptionService(private_key_path=priv)
        with pytest.raises(ValueError, match="Public key"):
            svc.encrypt("test")

    def test_decrypt_without_private_key(self, keypair):
        _, pub = keypair
        svc = EncryptionService(public_key_path=pub)
        envelope = svc.encrypt("test")
        with pytest.raises(ValueError, match="Private key"):
            svc.decrypt(envelope)

    def test_tampered_ciphertext_fails(self, keypair):
        priv, pub = keypair
        svc = EncryptionService(pub, priv)
        envelope = svc.encrypt("test")
        # Tamper with ciphertext
        import base64
        ct = base64.b64decode(envelope["ciphertext"])
        tampered = bytes([ct[0] ^ 0xFF]) + ct[1:]
        envelope["ciphertext"] = base64.b64encode(tampered).decode()
        with pytest.raises(Exception):
            svc.decrypt(envelope)
