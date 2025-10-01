## Telegram бот для мониторинга объявлений о аренде квартир (Минск)

Бот парсит 3 сайта каждые 60 секунд и присылает новые объявления:

- [Kufar](https://re.kufar.by/l/minsk/snyat/kvartiru?cur=USD&prc=r%3A0%2C350)
- [Domovita](https://domovita.by/minsk/flats/rent?rooms=1%2C2&price%5Bmin%5D=&price%5Bmax%5D=350&price_type=all_usd)
- [Realt.by](https://realt.by/rent/flat-for-long/?addressV2=%5B%7B%22townUuid%22%3A%224cb07174-7b00-11eb-8943-0cc47adabd66%22%7D%5D&page=1&priceTo=350&priceType=840&rooms=1&rooms=2)

### Быстрый старт

1. Установите зависимости:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2. Создайте файл `.env` по образцу `.env.example` и укажите токен бота:

```env
TELEGRAM_BOT_TOKEN=8013829336:AAE6xcc3C3F1Rp6_KbZbqJvXSBmTtHnSPGM
```

При необходимости измените URL источников.

3. Запуск:

```bash
python -m src.main
```

Команда в Telegram: `/start` — подписывает чат на уведомления.

### Примечания

- Первый запуск прогревает кэш: текущие объявления отмечаются как «уже виденные», чтобы не заспамить чат старыми карточками.
- Хранилище состояния лежит в `data/state.json`.
- Парсеры используют эвристики по HTML. Если сайты поменяют разметку, обновите селекторы в `src/scrapers/`.

### Отсутствие обновлений

Если в течение 5 подряд циклов (по 60 секунд каждый) не появляется ни одного нового объявления, бот отправит уведомление: «За последние N циклов новых объявлений не появилось».

### Запуск в Docker

1. Через docker-compose:

```bash
export TELEGRAM_BOT_TOKEN=8013829336:AAE6xcc3C3F1Rp6_KbZbqJvXSBmTtHnSPGM
docker compose up -d --build
```

2. Логи:

```bash
docker compose logs -f
```

3. Остановка:

```bash
docker compose down
```

Переменные окружения: `TELEGRAM_BOT_TOKEN`, `KUFAR_URL`, `DOMOVITA_URL`, `REALT_URL`. Состояние хранится на volume `./data:/app/data`.
