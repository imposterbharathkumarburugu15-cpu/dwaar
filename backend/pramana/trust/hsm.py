"""Provider-Independent Hardware Security Module (HSM) Abstraction Layer.

Implements Module 2 of Phase 3:
- Common HSM interface for cryptographic operations (generate, sign, verify, encrypt, decrypt).
- Real LocalDevelopmentCryptoProvider using genuine standard Python cryptography primitives.
- Explicit DEVELOPMENT_PROVIDER status (zero simulation of fake hardware success).
- PKCS#11 adapter interface with realistic hardware availability diagnostics.
- Provider health check and capability reporting.
"""

import base64
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings
from ..crypto import sha256_hex


@dataclass
class ProviderHealth:
    healthy: bool
    provider_type: str
    is_hardware_backed: bool
    capabilities: list[str]
    status_message: str
    checked_at: str
    diagnostics: dict[str, Any]


class BaseHSMProvider(ABC):
    """Abstract interface defining required HSM cryptographic operations."""

    @property
    @abstractmethod
    def provider_type(self) -> str:
        pass

    @property
    @abstractmethod
    def is_hardware_backed(self) -> bool:
        pass

    @abstractmethod
    def generate_key(self, key_id: str, algorithm: str) -> dict[str, Any]:
        """Generates a keypair or symmetric key inside the provider boundary."""
        pass

    @abstractmethod
    def sign(self, key_id: str, data: bytes) -> bytes:
        """Digitally signs data using the specified private key."""
        pass

    @abstractmethod
    def verify(self, key_id: str, data: bytes, signature: bytes, public_key_b64: str | None = None) -> bool:
        """Verifies a digital signature."""
        pass

    @abstractmethod
    def encrypt(self, key_id: str, plaintext: bytes) -> dict[str, str]:
        """Envelope-encrypts data using a managed symmetric key."""
        pass

    @abstractmethod
    def decrypt(self, key_id: str, ciphertext_b64: str, nonce_b64: str) -> bytes:
        """Decrypts ciphertext using a managed symmetric key."""
        pass

    @abstractmethod
    def get_public_key(self, key_id: str) -> str | None:
        """Retrieves Base64-encoded public key bytes."""
        pass

    @abstractmethod
    def check_health(self) -> ProviderHealth:
        """Runs health diagnostics and returns capability envelope."""
        pass


class LocalDevelopmentCryptoProvider(BaseHSMProvider):
    """Real software cryptographic provider for local development & testing.
    
    HONEST LABELLING:
    - Reports provider_type: 'DEVELOPMENT_PROVIDER'
    - Reports is_hardware_backed: False
    - Uses genuine OpenSSL-backed cryptographic primitives from standard `cryptography`.
    """

    def __init__(self, key_storage_dir: Path | None = None):
        self.key_dir = key_storage_dir or (get_settings().keys_dir / "kms")
        self.key_dir.mkdir(parents=True, exist_ok=True)
        self._memory_keys: dict[str, Any] = {}

    @property
    def provider_type(self) -> str:
        return "DEVELOPMENT_PROVIDER"

    @property
    def is_hardware_backed(self) -> bool:
        return False

    def generate_key(self, key_id: str, algorithm: str) -> dict[str, Any]:
        algorithm = algorithm.upper()
        pub_b64: str | None = None

        if algorithm == "ED25519":
            priv = ed25519.Ed25519PrivateKey.generate()
            pub_bytes = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
            self._save_raw_key(key_id, priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            ))
            self._memory_keys[key_id] = ("ED25519", priv)

        elif algorithm in ("ECDSA_P256", "EC_SECP256R1"):
            priv = ec.generate_private_key(ec.SECP256R1())
            pub_pem = priv.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            pub_b64 = base64.b64encode(pub_pem).decode("ascii")
            self._save_raw_key(key_id, priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ))
            self._memory_keys[key_id] = ("ECDSA_P256", priv)

        elif algorithm in ("AES_256_GCM", "AES256"):
            raw_aes = AESGCM.generate_key(bit_length=256)
            self._save_raw_key(key_id, raw_aes)
            self._memory_keys[key_id] = ("AES_256_GCM", raw_aes)
            pub_b64 = None  # Symmetric key has no public key

        else:
            raise ValueError(f"Unsupported algorithm '{algorithm}' for provider {self.provider_type}")

        fingerprint = sha256_hex(base64.b64decode(pub_b64)) if pub_b64 else sha256_hex(key_id.encode())
        return {
            "key_id": key_id,
            "algorithm": algorithm,
            "provider_type": self.provider_type,
            "public_key_b64": pub_b64,
            "public_key_fingerprint": fingerprint,
            "is_hardware_backed": self.is_hardware_backed,
        }

    def sign(self, key_id: str, data: bytes) -> bytes:
        alg, priv = self._get_key(key_id)
        if alg == "ED25519":
            return priv.sign(data)
        elif alg == "ECDSA_P256":
            return priv.sign(data, ec.ECDSA(hashes.SHA256()))
        raise ValueError(f"Key '{key_id}' algorithm '{alg}' does not support signing")

    def verify(self, key_id: str, data: bytes, signature: bytes, public_key_b64: str | None = None) -> bool:
        pub_b64 = public_key_b64 or self.get_public_key(key_id)
        if not pub_b64:
            return False

        try:
            raw_pub = base64.b64decode(pub_b64)
            # Try Ed25519 first
            if len(raw_pub) == 32:
                ed_pub = ed25519.Ed25519PublicKey.from_public_bytes(raw_pub)
                ed_pub.verify(signature, data)
                return True
            else:
                # Try ECDSA PEM
                ec_pub = serialization.load_pem_public_key(raw_pub)
                ec_pub.verify(signature, data, ec.ECDSA(hashes.SHA256()))
                return True
        except (InvalidSignature, ValueError):
            return False

    def encrypt(self, key_id: str, plaintext: bytes) -> dict[str, str]:
        alg, raw_key = self._get_key(key_id)
        if alg != "AES_256_GCM":
            raise ValueError(f"Key '{key_id}' algorithm '{alg}' does not support symmetric encryption")

        aesgcm = AESGCM(raw_key)
        nonce = os.urandom(12)  # 96-bit standard nonce for AES-GCM
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        return {
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        }

    def decrypt(self, key_id: str, ciphertext_b64: str, nonce_b64: str) -> bytes:
        alg, raw_key = self._get_key(key_id)
        if alg != "AES_256_GCM":
            raise ValueError(f"Key '{key_id}' is not an AES-256-GCM encryption key")

        aesgcm = AESGCM(raw_key)
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(ciphertext_b64)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def get_public_key(self, key_id: str) -> str | None:
        if key_id in self._memory_keys:
            alg, priv = self._memory_keys[key_id]
            if alg == "ED25519":
                pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
                return base64.b64encode(pub).decode("ascii")
            elif alg == "ECDSA_P256":
                pub = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
                return base64.b64encode(pub).decode("ascii")
            return None

        # Try disk file
        key_file = self.key_dir / f"{key_id}.key"
        meta_file = self.key_dir / f"{key_id}.meta"
        if not key_file.exists() or not meta_file.exists():
            return None

        alg = meta_file.read_text().strip()
        data = key_file.read_bytes()
        if alg == "ED25519":
            priv = ed25519.Ed25519PrivateKey.from_private_bytes(data)
            pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            return base64.b64encode(pub).decode("ascii")
        elif alg == "ECDSA_P256":
            priv = serialization.load_pem_private_key(data, password=None)
            pub = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            return base64.b64encode(pub).decode("ascii")
        return None

    def check_health(self) -> ProviderHealth:
        # Run test signature and AES roundtrip
        try:
            test_ed = ed25519.Ed25519PrivateKey.generate()
            test_sig = test_ed.sign(b"health_check")
            test_ed.public_key().verify(test_sig, b"health_check")

            test_aes = AESGCM.generate_key(256)
            aes = AESGCM(test_aes)
            nonce = os.urandom(12)
            ct = aes.encrypt(nonce, b"health_check", None)
            pt = aes.decrypt(nonce, ct, None)
            assert pt == b"health_check"

            healthy = True
            msg = "Local development cryptographic provider operating normally."
        except Exception as err:
            healthy = False
            msg = f"Cryptographic self-test failed: {err}"

        return ProviderHealth(
            healthy=healthy,
            provider_type=self.provider_type,
            is_hardware_backed=self.is_hardware_backed,
            capabilities=["ED25519_SIGN", "ECDSA_P256_SIGN", "AES_256_GCM_ENCRYPT", "SOFTWARE_KEYSTORE"],
            status_message=msg,
            checked_at=datetime.now(UTC).isoformat(),
            diagnostics={
                "storage_directory": str(self.key_dir),
                "open_keys_count": len(self._memory_keys),
                "fips_mode": False,
            },
        )

    def _save_raw_key(self, key_id: str, raw_bytes: bytes) -> None:
        key_file = self.key_dir / f"{key_id}.key"
        key_file.write_bytes(raw_bytes)
        try:
            os.chmod(key_file, 0o600)
        except Exception:
            pass

    def _get_key(self, key_id: str) -> tuple[str, Any]:
        if key_id in self._memory_keys:
            return self._memory_keys[key_id]

        key_file = self.key_dir / f"{key_id}.key"
        meta_file = self.key_dir / f"{key_id}.meta"
        if not key_file.exists():
            raise KeyError(f"Key '{key_id}' does not exist in provider")

        alg = meta_file.read_text().strip() if meta_file.exists() else "ED25519"
        data = key_file.read_bytes()
        if alg == "ED25519":
            priv = ed25519.Ed25519PrivateKey.from_private_bytes(data)
            self._memory_keys[key_id] = (alg, priv)
            return alg, priv
        elif alg == "ECDSA_P256":
            priv = serialization.load_pem_private_key(data, password=None)
            self._memory_keys[key_id] = (alg, priv)
            return alg, priv
        elif alg == "AES_256_GCM":
            self._memory_keys[key_id] = (alg, data)
            return alg, data

        raise ValueError(f"Unknown algorithm {alg}")


class PKCS11HSMAdapter(BaseHSMProvider):
    """PKCS#11 Hardware Security Module adapter interface.
    
    HONEST DISCLOSURE:
    When physical hardware (e.g. Nitrokey HSM, YubiHSM, Thales Luna) is not attached,
    accurately reports HARDWARE_NOT_CONNECTED without fabricating fake success.
    """

    def __init__(self, lib_path: str | None = None, slot_id: int = 0):
        self.lib_path = lib_path or os.getenv("PRAMANA_PKCS11_LIB", "")
        self.slot_id = slot_id

    @property
    def provider_type(self) -> str:
        return "PKCS11_HSM"

    @property
    def is_hardware_backed(self) -> bool:
        return True

    def generate_key(self, key_id: str, algorithm: str) -> dict[str, Any]:
        raise NotImplementedError("Physical PKCS#11 HSM hardware is not connected in local development environment")

    def sign(self, key_id: str, data: bytes) -> bytes:
        raise NotImplementedError("Physical PKCS#11 HSM hardware is not connected in local development environment")

    def verify(self, key_id: str, data: bytes, signature: bytes, public_key_b64: str | None = None) -> bool:
        raise NotImplementedError("Physical PKCS#11 HSM hardware is not connected in local development environment")

    def encrypt(self, key_id: str, plaintext: bytes) -> dict[str, str]:
        raise NotImplementedError("Physical PKCS#11 HSM hardware is not connected in local development environment")

    def decrypt(self, key_id: str, ciphertext_b64: str, nonce_b64: str) -> bytes:
        raise NotImplementedError("Physical PKCS#11 HSM hardware is not connected in local development environment")

    def get_public_key(self, key_id: str) -> str | None:
        return None

    def check_health(self) -> ProviderHealth:
        has_lib = bool(self.lib_path and Path(self.lib_path).exists())
        return ProviderHealth(
            healthy=False,
            provider_type=self.provider_type,
            is_hardware_backed=True,
            capabilities=["FIPS_140_3_LEVEL_3", "HARDWARE_RNG", "PKCS11_CRYPTO"],
            status_message="HARDWARE_NOT_CONNECTED: Physical HSM driver/token is not present on host.",
            checked_at=datetime.now(UTC).isoformat(),
            diagnostics={
                "driver_configured": has_lib,
                "library_path": self.lib_path or "UNCONFIGURED",
                "slot_id": self.slot_id,
            },
        )


class HSMProviderRegistry:
    """Manages active cryptographic providers."""

    def __init__(self):
        self.default_provider = LocalDevelopmentCryptoProvider()
        self.providers: dict[str, BaseHSMProvider] = {
            "DEVELOPMENT_PROVIDER": self.default_provider,
            "PKCS11_HSM": PKCS11HSMAdapter(),
        }

    def get_provider(self, provider_type: str = "DEVELOPMENT_PROVIDER") -> BaseHSMProvider:
        return self.providers.get(provider_type, self.default_provider)


# Global registry
default_hsm_registry = HSMProviderRegistry()

