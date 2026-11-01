"""Tests for Provider-Independent HSM Abstraction Layer (Module 2).

Verifies:
1. Real software cryptographic operations in LocalDevelopmentCryptoProvider (Ed25519, ECDSA, AES-GCM).
2. Honest reporting of DEVELOPMENT_PROVIDER status (zero simulation of fake hardware).
3. Encryption & decryption roundtrips with authenticated tags.
4. PKCS#11 HSM adapter health checks and honest HARDWARE_NOT_CONNECTED reporting when unattached.
5. Unsupported operations / algorithms trigger clean exceptions.
"""

import pytest
from pramana.trust.hsm import (
    HSMProviderRegistry,
    LocalDevelopmentCryptoProvider,
    PKCS11HSMAdapter,
    default_hsm_registry,
)


@pytest.fixture
def dev_provider(tmp_path):
    return LocalDevelopmentCryptoProvider(key_storage_dir=tmp_path / "hsm_keys")


def test_dev_provider_ed25519_sign_and_verify(dev_provider):
    """Test 1: Generates Ed25519 key, signs data, and verifies mathematically."""
    key_info = dev_provider.generate_key("test-hsm-ed", "ED25519")
    assert key_info["is_hardware_backed"] is False
    assert key_info["provider_type"] == "DEVELOPMENT_PROVIDER"

    data = b"AICTE Document Verification Hash"
    sig = dev_provider.sign("test-hsm-ed", data)
    assert len(sig) == 64

    # Verification passes with valid signature
    assert dev_provider.verify("test-hsm-ed", data, sig) is True

    # Verification fails on modified data
    assert dev_provider.verify("test-hsm-ed", b"Tampered data", sig) is False


def test_dev_provider_ecdsa_sign_and_verify(dev_provider):
    """Test 2: Generates ECDSA P-256 key, signs data, and verifies with SHA-256."""
    key_info = dev_provider.generate_key("test-hsm-ec", "ECDSA_P256")
    assert key_info["public_key_b64"] is not None

    data = b"Officer Field Inspection Observation"
    sig = dev_provider.sign("test-hsm-ec", data)
    assert len(sig) > 40  # DER-encoded ECDSA signature

    assert dev_provider.verify("test-hsm-ec", data, sig) is True
    assert dev_provider.verify("test-hsm-ec", b"Modified data", sig) is False


def test_dev_provider_aes_gcm_envelope_encryption(dev_provider):
    """Test 3: Generates AES-256-GCM symmetric key and roundtrips encryption and decryption."""
    dev_provider.generate_key("test-hsm-aes", "AES_256_GCM")

    secret_doc = b"%PDF-1.4 Secret Faculty Salary Statement 2026"
    encrypted = dev_provider.encrypt("test-hsm-aes", secret_doc)
    
    assert "ciphertext_b64" in encrypted
    assert "nonce_b64" in encrypted

    # Decrypt and verify
    plaintext = dev_provider.decrypt("test-hsm-aes", encrypted["ciphertext_b64"], encrypted["nonce_b64"])
    assert plaintext == secret_doc


def test_dev_provider_health_check_reporting(dev_provider):
    """Test 4: Reports honest DEVELOPMENT_PROVIDER diagnostics and capability envelope."""
    health = dev_provider.check_health()
    assert health.healthy is True
    assert health.provider_type == "DEVELOPMENT_PROVIDER"
    assert health.is_hardware_backed is False
    assert "ED25519_SIGN" in health.capabilities
    assert "AES_256_GCM_ENCRYPT" in health.capabilities
    assert "operating normally" in health.status_message.lower()


def test_pkcs11_adapter_honest_hardware_diagnostics():
    """Test 5: PKCS#11 adapter reports HARDWARE_NOT_CONNECTED when physical token is not attached."""
    pkcs11_adapter = PKCS11HSMAdapter(lib_path="")
    health = pkcs11_adapter.check_health()
    
    assert health.healthy is False
    assert health.is_hardware_backed is True
    assert health.provider_type == "PKCS11_HSM"
    assert "HARDWARE_NOT_CONNECTED" in health.status_message

    # Calling operations on disconnected hardware raises clean NotImplementedError
    with pytest.raises(NotImplementedError, match="Physical PKCS#11 HSM hardware is not connected"):
        pkcs11_adapter.generate_key("key-fail", "ED25519")

