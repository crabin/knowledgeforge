from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


TOKYO = ZoneInfo("Asia/Tokyo")


def now_iso() -> str:
    return datetime.now(TOKYO).isoformat(timespec="seconds")


def today_compact() -> str:
    return datetime.now(TOKYO).strftime("%Y%m%d")
