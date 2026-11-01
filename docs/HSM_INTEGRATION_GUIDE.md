# PRAMANA — Hardware Security Module (HSM) Integration Guide

## 1. Abstract Base Architecture
PRAMANA decouples its business and validation logic from physical cryptography hardware via the `BaseHSMProvider` abstract base class (`backend/pramana/trust/hsm.py`). This guarantees plug-and-play interoperability across development environments, on-premise hardware appliances, and national cloud HSMs.

```python
class BaseHSMProvider(ABC):
    @abstractmethod
    def generate_key(self, key_id: str, algorithm: str, key_purpose: str) -> dict[str, Any]: ...
    
    @abstractmethod
    def sign(self, key_id: str, data: bytes) -> bytes: ...
    
    @abstractmethod
    def verify(self, key_id: str, data: bytes, signature: bytes, public_key_b64: str) -> bool: ...
    
    @abstractmethod
    def encrypt(self, key_id: str, plaintext: bytes) -> dict[str, Any]: ...
    
    @abstractmethod
    def decrypt(self, key_id: str, ciphertext: bytes, iv: bytes, tag: bytes) -> bytes: ...
    
    @abstractmethod
    def health_check(self) -> HSMHealthStatus: ...
```

---

## 2. Implemented Providers

### 2.1 `LocalDevelopmentCryptoProvider`
- **Purpose**: Local workstation execution and automated CI/CD testing without physical hardware dependencies.
- **Implementation**: Utilizes OpenSSL-backed primitives from Python's official `cryptography` package.
- **Honest Diagnostics**:
  - `is_hardware_backed`: `False`
  - `provider_type`: `"DEVELOPMENT_PROVIDER"`
  - `status`: `"HEALTHY"`
  - `status_message`: `"Local software crypto provider operational (OpenSSL primitives). Hardware security module NOT attached."`

### 2.2 `PKCS11HSMAdapter`
- **Purpose**: Production interface conforming to PKCS#11 standard v2.40 (OASIS) for physical appliances (Nitrokey HSM, YubiHSM 2, Thales Luna, AWS CloudHSM, Google Cloud HSM).
- **Diagnostics When Hardware Absent**:
  - `is_hardware_backed`: `True`
  - `status`: `"DEGRADED"`
  - `status_message`: `"HARDWARE_NOT_CONNECTED: PKCS#11 module not detected on bus or socket."`

---

## 3. Production Deployment Guide (PKCS#11 Setup)
When deploying PRAMANA in an AICTE data center or secure cloud enclave:
1. **Install Hardware Drivers & PKCS#11 Library**:
   ```bash
   sudo apt-get install opensc libpcsclite-dev pcscd
   ```
2. **Configure Environment Variables**:
   ```env
   PRAMANA_HSM_PROVIDER=PKCS11
   PRAMANA_PKCS11_LIB=/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so
   PRAMANA_HSM_SLOT=0
   PRAMANA_HSM_PIN=secret_officer_so_pin
   ```
3. **Initialize Provider Registry**:
   PRAMANA's `HSMProviderRegistry` will automatically detect the configuration and bind the primary signing and envelope keys to HSM hardware slots.

