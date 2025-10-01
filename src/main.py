import asyncio
import logging

from .state import StateStore
from .bot import BotApp
from .poller import poll_once


POLL_INTERVAL_SEC = 60


async def poll_loop(state: StateStore, bot: BotApp) -> None:
    while True:
        await poll_once(state, bot)
        await asyncio.sleep(POLL_INTERVAL_SEC)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    # Понижаем шум от сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    state = StateStore()
    bot = BotApp(state)

    loop = asyncio.get_event_loop()
    loop.create_task(poll_loop(state, bot))
    bot.run_polling()


if __name__ == "__main__":
    main()

