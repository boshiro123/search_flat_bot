import json
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime

from .config import DATA_DIR


STATE_FILE = DATA_DIR / "state.json"


class StateStore:
    def __init__(self, path: Path = STATE_FILE) -> None:
        self.path = path
        self.seen_ids_by_source: Dict[str, Set[str]] = {}
        self.last_date_by_source: Dict[str, Optional[datetime]] = {}
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
        # Загрузка дат
        last_dates_raw = data.get("last_date_by_source") or {}
        self.last_date_by_source = {}
        for k, v in last_dates_raw.items():
            if v:
                try:
                    self.last_date_by_source[k] = datetime.fromisoformat(v)
                except Exception:
                    self.last_date_by_source[k] = None
            else:
                self.last_date_by_source[k] = None

    def _save(self) -> None:
        # Сериализация дат в ISO-формат
        last_dates_ser = {}
        for k, v in self.last_date_by_source.items():
            if v:
                last_dates_ser[k] = v.isoformat()
            else:
                last_dates_ser[k] = None

        payload = {
            "seen_ids_by_source": {k: sorted(list(v)) for k, v in self.seen_ids_by_source.items()},
            "chat_ids": sorted(list(self.chat_ids)),
            "empty_cycles": self.empty_cycles,
            "last_date_by_source": last_dates_ser,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def mark_seen(self, source: str, ids: Set[str]) -> None:
        current = self.seen_ids_by_source.get(source) or set()
        current |= set(ids)
        self.seen_ids_by_source[source] = current
        self._save()

    def is_new(self, source: str, item_id: str, created_at: Optional[datetime] = None) -> bool:
        # Сначала проверяем по ID - это основной критерий
        if item_id in (self.seen_ids_by_source.get(source) or set()):
            return False
        
        # Если есть дата создания — сравниваем с последней сохранённой датой
        # Но отклоняем только если дата СТРОГО меньше (created_at < last)
        # Это позволит обрабатывать несколько объявлений с одинаковой датой (например, Domovita)
        if created_at and source in self.last_date_by_source:
            last = self.last_date_by_source[source]
            if last and created_at < last:
                return False
        return True
    
    def update_last_date(self, source: str, date: Optional[datetime]) -> None:
        if date:
            current = self.last_date_by_source.get(source)
            if not current or date > current:
                self.last_date_by_source[source] = date
                self._save()

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

