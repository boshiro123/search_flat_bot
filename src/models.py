from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Listing:
    source: str
    id: str
    url: str
    title: Optional[str] = None
    price: Optional[str] = None
    location: Optional[str] = None

