import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


@dataclass
class AppConfig:
    telegram_token: str
    max_price: int
    kufar_url: str
    domovita_url: str
    realt_url: str


def load_config(override_max_price: int = None) -> AppConfig:
    # Поддержка дефолтного токена из пользовательского запроса (если .env не задан)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

    def env_or_default(key: str, default: str) -> str:
        val = os.getenv(key, "")
        val = val.strip() if isinstance(val, str) else ""
        return val or default

    # Максимальная цена парсинга (USD)
    # Приоритет: override_max_price > MAX_PRICE из .env > 350
    if override_max_price is not None:
        max_price = override_max_price
    else:
        max_price_str = os.getenv("MAX_PRICE", "350").strip()
        try:
            max_price = int(max_price_str)
        except ValueError:
            max_price = 350

    return AppConfig(
        telegram_token=token,
        max_price=max_price,
        kufar_url=env_or_default(
            "KUFAR_URL",
            f"https://re.kufar.by/l/minsk/snyat/kvartiru?cur=USD&prc=r%3A0%2C{max_price}",
        ),
        domovita_url=env_or_default(
            "DOMOVITA_URL",
            f"https://domovita.by/minsk/flats/rent?rooms=1%2C2&price%5Bmin%5D=&price%5Bmax%5D={max_price}&price_type=all_usd",
        ),
        realt_url=env_or_default(
            "REALT_URL",
            f"https://realt.by/rent/flat-for-long/?addressV2=%5B%7B%22townUuid%22%3A%224cb07174-7b00-11eb-8943-0cc47adabd66%22%7D%5D&page=1&priceTo={max_price}&priceType=840&rooms=1&rooms=2",
        ),
    )

