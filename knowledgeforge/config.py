from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    save_root: Path = Path("save")
    max_rounds: int = 3
