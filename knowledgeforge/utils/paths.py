from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def sanitize_path_segment(value: str, fallback: str) -> str:
    cleaned = value.strip().replace("/", "-").replace("\\", "-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or fallback


def slugify_filename(value: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or fallback


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
