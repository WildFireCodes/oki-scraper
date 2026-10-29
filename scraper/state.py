"""Stan między uruchomieniami (data/state.json)."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

SEEN_LIMIT = 2000
RECENT_LIMIT = 30
EMPTY_STATE = {"sources": {}, "recent": []}


def source_key(url: str) -> str:
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:12]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("sources", {})
    data.setdefault("recent", [])
    return data


def dump_state(state: dict) -> str:
    return json.dumps(state, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def save_state_if_changed(path: str, state: dict) -> bool:
    new = dump_state(state)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == new:
                return False
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return True


def get_source(state: dict, key: str) -> dict:
    return state["sources"].setdefault(
        key, {"seen": [], "failures": 0, "warned": False, "lastOk": None}
    )


def merge_seen(current_ids: list[str], older: list[str]) -> list[str]:
    seen, out = set(), []
    for i in list(current_ids) + list(older):
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out[:SEEN_LIMIT]


def add_recent(state: dict, items: list[dict]) -> None:
    state["recent"] = (items + state["recent"])[:RECENT_LIMIT]
