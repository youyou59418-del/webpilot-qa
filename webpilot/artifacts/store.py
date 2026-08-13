from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SENSITIVE_KEY_TOKENS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "value",
)


@dataclass(frozen=True)
class ArtifactReference:
    run_id: str
    name: str
    path: str


class ArtifactStore:
    """Filesystem artifact store with path containment and secret redaction."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create_run(self, run_id: str) -> Path:
        return self._run_dir(run_id, create=True)

    def write_json(
        self,
        *,
        run_id: str,
        name: str,
        payload: Any,
    ) -> ArtifactReference:
        path = self._artifact_path(run_id=run_id, name=name)
        sanitized = self.redact(payload)
        path.write_text(
            json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return self._reference(run_id, name, path)

    def write_text(
        self,
        *,
        run_id: str,
        name: str,
        text: str,
    ) -> ArtifactReference:
        path = self._artifact_path(run_id=run_id, name=name)
        path.write_text(text, encoding="utf-8")
        return self._reference(run_id, name, path)

    def list_run(self, run_id: str) -> list[ArtifactReference]:
        run_dir = self._run_dir(run_id, create=False)
        if not run_dir.exists():
            return []
        return [
            self._reference(run_id, path.name, path)
            for path in sorted(run_dir.iterdir())
            if path.is_file()
        ]

    @classmethod
    def redact(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): (
                    "[REDACTED]"
                    if cls._is_sensitive_key(str(key))
                    else cls.redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls.redact(item) for item in value]
        if isinstance(value, tuple):
            return [cls.redact(item) for item in value]
        if hasattr(value, "model_dump"):
            return cls.redact(value.model_dump(mode="json"))
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        normalized = key.lower().replace("-", "_")
        return any(token in normalized for token in _SENSITIVE_KEY_TOKENS)

    def _artifact_path(self, *, run_id: str, name: str) -> Path:
        if not _SAFE_COMPONENT.fullmatch(name):
            raise ValueError("Artifact name must be a single safe file name.")
        run_dir = self._run_dir(run_id, create=True)
        path = (run_dir / name).resolve()
        if path.parent != run_dir:
            raise ValueError("Artifact path escapes the run directory.")
        return path

    def _run_dir(self, run_id: str, *, create: bool) -> Path:
        if not _SAFE_COMPONENT.fullmatch(run_id):
            raise ValueError("run_id must contain only safe path characters.")
        path = (self.root / run_id).resolve()
        if path.parent != self.root:
            raise ValueError("run_id escapes artifact root.")
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _reference(
        self,
        run_id: str,
        name: str,
        path: Path,
    ) -> ArtifactReference:
        return ArtifactReference(
            run_id=run_id,
            name=name,
            path=str(path.relative_to(self.root)),
        )
