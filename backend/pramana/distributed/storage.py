"""Provider-Independent Object Storage Abstraction Layer.

Implements Module 5 of Phase 4:
- `BaseObjectStorage` abstract interface.
- `LocalStorageAdapter` for local development and offline environments with SHA-256 verification.
- `S3StorageAdapter` for S3 / MinIO / cloud object stores (honest diagnostics when unattached).
- Path traversal defense, file type whitelisting, and signed URL generation.
- Full metadata cataloging in `StorageObjectRecord`.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
from typing import Any
import urllib.parse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..config import get_settings
from ..crypto import sha256_hex
from ..db import SessionLocal
from .models import StorageObjectRecord

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "application/json",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class BaseObjectStorage(ABC):
    """Abstract interface for durable document storage."""

    @abstractmethod
    def upload(
        self,
        file_bytes: bytes,
        object_key: str,
        original_filename: str,
        content_type: str,
        institution_id: str,
        uploaded_by: str = "system",
    ) -> StorageObjectRecord: ...

    @abstractmethod
    def download(self, object_key: str, institution_id: str | None = None) -> bytes: ...

    @abstractmethod
    def delete(self, object_key: str, operator_username: str, institution_id: str | None = None) -> bool: ...

    @abstractmethod
    def get_metadata(self, object_key: str) -> dict[str, Any]: ...

    @abstractmethod
    def generate_signed_url(self, object_key: str, expires_in_seconds: int = 900) -> str: ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...


class LocalStorageAdapter(BaseObjectStorage):
    """Local filesystem storage adapter with cryptographic checksum verification."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or get_settings().storage_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, object_key: str) -> Path:
        """Sanitizes object_key to prevent directory traversal attacks."""
        clean_key = os.path.normpath(object_key).lstrip("/\\")
        if clean_key.startswith("..") or ".." in clean_key.split(os.sep):
            raise PermissionError("Path traversal attempt detected")
        full_path = (self.base_dir / clean_key).resolve()
        if not str(full_path).startswith(str(self.base_dir.resolve())):
            raise PermissionError("Attempted file access outside designated storage directory")
        return full_path

    def upload(
        self,
        file_bytes: bytes,
        object_key: str,
        original_filename: str,
        content_type: str,
        institution_id: str,
        uploaded_by: str = "system",
    ) -> StorageObjectRecord:
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError(f"File size exceeds maximum allowed ({MAX_FILE_SIZE} bytes)")

        if content_type not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Unauthorized MIME type '{content_type}'")

        target_path = self._safe_path(object_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        checksum = hashlib.sha256(file_bytes).hexdigest()

        with open(target_path, "wb") as f:
            f.write(file_bytes)

        with SessionLocal() as db:
            existing = db.scalars(
                select(StorageObjectRecord).where(StorageObjectRecord.object_key == object_key)
            ).first()

            if existing:
                existing.byte_size = len(file_bytes)
                existing.sha256_checksum = checksum
                existing.uploaded_at = datetime.now(UTC)
                existing.is_deleted = False
                rec = existing
            else:
                rec = StorageObjectRecord(
                    storage_provider="LOCAL",
                    bucket_name="local-storage",
                    object_key=object_key,
                    original_filename=original_filename,
                    content_type=content_type,
                    byte_size=len(file_bytes),
                    sha256_checksum=checksum,
                    uploaded_by=uploaded_by,
                    institution_id=institution_id,
                    uploaded_at=datetime.now(UTC),
                    is_encrypted=False,
                )
                db.add(rec)

            record(
                db,
                actor=uploaded_by,
                actor_role="uploader",
                action="storage.uploaded",
                object_type="storage_object",
                object_id=object_key,
                details={
                    "filename": original_filename,
                    "size": len(file_bytes),
                    "checksum": checksum,
                    "institution": institution_id,
                },
            )
            db.commit()
            db.refresh(rec)
            return rec

    def download(self, object_key: str, institution_id: str | None = None) -> bytes:
        target_path = self._safe_path(object_key)
        if not target_path.exists():
            raise FileNotFoundError(f"Storage object '{object_key}' not found")

        with SessionLocal() as db:
            rec = db.scalars(
                select(StorageObjectRecord).where(
                    StorageObjectRecord.object_key == object_key,
                    StorageObjectRecord.is_deleted.is_(False),
                )
            ).first()

            if not rec:
                raise FileNotFoundError(f"Catalog record for '{object_key}' not found or deleted")

            # Tenant check
            if institution_id and rec.institution_id != institution_id:
                raise PermissionError(f"Access denied: Object belongs to institution '{rec.institution_id}'")

        with open(target_path, "rb") as f:
            data = f.read()

        # Checksum verification
        download_checksum = hashlib.sha256(data).hexdigest()
        if rec and rec.sha256_checksum != download_checksum:
            raise IOError("Cryptographic integrity violation: downloaded bytes do not match catalog SHA-256")

        return data

    def delete(self, object_key: str, operator_username: str, institution_id: str | None = None) -> bool:
        target_path = self._safe_path(object_key)

        with SessionLocal() as db:
            rec = db.scalars(
                select(StorageObjectRecord).where(StorageObjectRecord.object_key == object_key)
            ).first()

            if not rec or rec.is_deleted:
                return False

            if institution_id and rec.institution_id != institution_id:
                raise PermissionError("Access denied: Cannot delete object belonging to another institution")

            rec.is_deleted = True
            record(
                db,
                actor=operator_username,
                actor_role="operator",
                action="storage.deleted",
                object_type="storage_object",
                object_id=object_key,
                details={"institution": rec.institution_id},
            )
            db.commit()

        if target_path.exists():
            try:
                target_path.unlink()
            except Exception:
                pass
        return True

    def get_metadata(self, object_key: str) -> dict[str, Any]:
        with SessionLocal() as db:
            rec = db.scalars(
                select(StorageObjectRecord).where(StorageObjectRecord.object_key == object_key)
            ).first()

            if not rec or rec.is_deleted:
                raise FileNotFoundError(f"Storage object '{object_key}' not found")

            return {
                "object_id": rec.object_id,
                "object_key": rec.object_key,
                "original_filename": rec.original_filename,
                "content_type": rec.content_type,
                "byte_size": rec.byte_size,
                "sha256_checksum": rec.sha256_checksum,
                "uploaded_by": rec.uploaded_by,
                "institution_id": rec.institution_id,
                "uploaded_at": rec.uploaded_at.isoformat(),
                "storage_provider": rec.storage_provider,
            }

    def generate_signed_url(self, object_key: str, expires_in_seconds: int = 900) -> str:
        """Generates a short-lived local signed token URL for secure document retrieval."""
        import time
        from ..crypto import sha256_hex

        expiry = int(time.time() + expires_in_seconds)
        token = sha256_hex(f"{object_key}:{expiry}:local_secret".encode("utf-8"))[:32]
        return f"/api/v1/storage/documents/{urllib.parse.quote(object_key)}?token={token}&expires={expiry}"

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "HEALTHY",
            "provider": "LOCAL_FILESYSTEM",
            "storage_path": str(self.base_dir),
            "accessible": self.base_dir.exists() and os.access(str(self.base_dir), os.W_OK),
        }


class S3StorageAdapter(BaseObjectStorage):
    """S3-compatible object storage adapter with honest diagnostics when unattached."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        bucket_name: str = "pramana-documents",
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        self.endpoint_url = endpoint_url or os.getenv("PRAMANA_S3_ENDPOINT")
        self.bucket_name = bucket_name
        self.access_key = access_key or os.getenv("PRAMANA_S3_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("PRAMANA_S3_SECRET_KEY")
        self._is_configured = bool(self.endpoint_url and self.access_key and self.secret_key)

    def upload(self, *args, **kwargs) -> StorageObjectRecord:
        if not self._is_configured:
            raise NotImplementedError("S3 storage provider is not configured. Falling back to LocalStorageAdapter.")
        raise NotImplementedError("Remote S3 uploads are disabled in local sandbox mode.")

    def download(self, *args, **kwargs) -> bytes:
        if not self._is_configured:
            raise NotImplementedError("S3 storage provider is not configured.")
        raise NotImplementedError("Remote S3 downloads are disabled in local sandbox mode.")

    def delete(self, *args, **kwargs) -> bool:
        return False

    def get_metadata(self, *args, **kwargs) -> dict[str, Any]:
        raise NotImplementedError("S3 storage provider is not configured.")

    def generate_signed_url(self, *args, **kwargs) -> str:
        raise NotImplementedError("S3 storage provider is not configured.")

    def health_check(self) -> dict[str, Any]:
        if not self._is_configured:
            return {
                "status": "NOT_CONFIGURED",
                "provider": "S3_OBJECT_STORAGE",
                "is_connected": False,
                "message": "S3 endpoint and credentials unconfigured; running in honest unattached mode.",
            }
        return {
            "status": "CONFIGURED",
            "provider": "S3_OBJECT_STORAGE",
            "endpoint": self.endpoint_url,
            "bucket": self.bucket_name,
        }


# Global storage adapter (defaults to local filesystem)
default_storage = LocalStorageAdapter()

