import json
from pathlib import Path
from typing import Dict, Set

from .config import DATA_DIR


STATE_FILE = DATA_DIR / "state.json"


class StateStore:
    def __init__(self, path: Path = STATE_FILE) -> None:
        self.path = path
        self.seen_ids_by_source: Dict[str, Set[str]] = {}
        self.chat_ids: Set[int] = set()
        self.empty_cycles: int = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        self.seen_ids_by_source = {
            k: set(v) for k, v in (data.get("seen_ids_by_source") or {}).items()
        }
        self.chat_ids = set(data.get("chat_ids") or [])
        self.empty_cycles = int(data.get("empty_cycles") or 0)

    def _save(self) -> None:
        payload = {
            "seen_ids_by_source": {k: sorted(list(v)) for k, v in self.seen_ids_by_source.items()},
            "chat_ids": sorted(list(self.chat_ids)),
            "empty_cycles": self.empty_cycles,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def mark_seen(self, source: str, ids: Set[str]) -> None:
        current = self.seen_ids_by_source.get(source) or set()
        current |= set(ids)
        self.seen_ids_by_source[source] = current
        self._save()

    def is_new(self, source: str, item_id: str) -> bool:
        return item_id not in (self.seen_ids_by_source.get(source) or set())

    def add_chat(self, chat_id: int) -> None:
        self.chat_ids.add(chat_id)
        self._save()

    def remove_chat(self, chat_id: int) -> None:
        if chat_id in self.chat_ids:
            self.chat_ids.remove(chat_id)
            self._save()

    def increment_empty_cycle(self) -> int:
        self.empty_cycles += 1
        self._save()
        return self.empty_cycles

    def reset_empty_cycles(self) -> None:
        if self.empty_cycles != 0:
            self.empty_cycles = 0
            self._save()

