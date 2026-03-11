"""LabOS Security Helpers — path validation and sanitization."""

from pathlib import Path


def safe_path_component(value: str) -> str:
    """Sanitize a path component (project_id, agent_id, filename).
    Raises ValueError if it contains path traversal characters."""
    if not value or ".." in value or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"Invalid path component: {value!r}")
    return value


def safe_resolve(base: Path, *parts: str) -> Path:
    """Resolve a path and ensure it stays within the base directory."""
    for p in parts:
        safe_path_component(p)
    resolved = (base / Path(*parts)).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"Path escapes base directory: {resolved}")
    return resolved
