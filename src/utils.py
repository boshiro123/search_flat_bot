from typing import Any, Optional
from datetime import datetime, timezone


def normalize_price(value: Any, default_currency: str = "$") -> Optional[str]:
    if value is None:
        return None

    # Если это объект с полем display — используем его как есть
    if isinstance(value, dict):
        display = value.get("display")
        if display:
            return display.strip()
        raw = value.get("value")
        if raw is None:
            return None
        try:
            num = float(raw)
            if num.is_integer():
                return f"{int(num)} {default_currency}"
            return f"{num:.2f} {default_currency}"
        except Exception:
            return f"{raw} {default_currency}".strip()

    # Числовые типы: приводим к float
    if isinstance(value, (int, float)):
        num = float(value)
        # Эвристика: большие значения трактуем как центы (например, 35000 => 350.00)
        if num >= 1000:
            num = num / 100.0
        if num.is_integer():
            return f"{int(num)} {default_currency}"
        return f"{num:.2f} {default_currency}"

    # Строки
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Если уже есть валюта — оставляем как есть
        lowers = s.lower()
        if "$" in s or "usd" in lowers or "byn" in lowers or "руб" in lowers or "р." in lowers:
            return s
        # Если только цифры/.,/, пробуем распарсить
        try:
            s_norm = s.replace(" ", "").replace(",", ".")
            num = float(s_norm)
            if num >= 1000:
                num = num / 100.0
            if num.is_integer():
                return f"{int(num)} {default_currency}"
            return f"{num:.2f} {default_currency}"
        except Exception:
            return s

    # Иные типы — строковое представление
    return str(value)


def normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Нормализует datetime к UTC с timezone.
    
    Если datetime без timezone (naive) - считаем его UTC и добавляем timezone.
    Если datetime с timezone - конвертируем в UTC.
    
    Args:
        dt: datetime объект (может быть naive или aware)
        
    Returns:
        datetime с timezone UTC или None
    """
    if dt is None:
        return None
    
    # Если datetime без timezone (naive) - считаем его UTC
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    
    # Если datetime с timezone - конвертируем в UTC
    return dt.astimezone(timezone.utc)

