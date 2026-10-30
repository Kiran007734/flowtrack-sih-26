from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile


class StorageError(RuntimeError):
    pass


class LocalPrivateStorage:
    """Private development adapter. It accepts generated keys only, never client paths."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        normalized = PurePosixPath(key)
        if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
            raise StorageError("Invalid managed storage key")
        candidate = (self.root / Path(*normalized.parts)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("Storage key escapes the managed namespace") from exc
        return candidate

    def store(self, key: str, content: bytes) -> None:
        path = self._path_for_key(key)
        if path.exists():
            raise StorageError("Generated storage key already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, path)
        except OSError as exc:
            if temporary and temporary.exists():
                temporary.unlink(missing_ok=True)
            raise StorageError("Unable to persist the private document") from exc

    def retrieve_path(self, key: str) -> Path:
        path = self._path_for_key(key)
        if not path.is_file():
            raise StorageError("Private document is unavailable")
        return path

    def exists(self, key: str) -> bool:
        try:
            return self._path_for_key(key).is_file()
        except StorageError:
            return False

    def delete(self, key: str) -> None:
        path = self._path_for_key(key)
        path.unlink(missing_ok=True)

    def checksum(self, key: str) -> str:
        digest = sha256()
        with self.retrieve_path(key).open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
