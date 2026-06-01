from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds")


def parse_iso_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def make_id(prefix: str) -> str:
    clean_prefix = prefix.strip().lower().replace("-", "_")
    return f"{clean_prefix}_{uuid.uuid4().hex}"


def content_hash(content: str) -> str:
    normalized = " ".join(str(content).strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        if default is not None:
            return default
        raise


def clamp(value: float | int | str | None, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return minimum
    if math.isnan(number):
        return minimum
    if number < minimum:
        return minimum
    if number > maximum:
        return maximum
    return number
