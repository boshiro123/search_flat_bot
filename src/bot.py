from typing import Iterable
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import load_config
from .state import StateStore
from .models import Listing


def format_listing_message(item: Listing) -> str:
    parts = [
        f"Источник: {item.source}",
        f"Заголовок: {item.title}" if item.title else None,
        f"Цена: {item.price}" if item.price else None,
        f"Локация: {item.location}" if item.location else None,
        f"URL: {item.url}",
    ]
    return "\n".join([p for p in parts if p])


class BotApp:
    def __init__(self, state: StateStore) -> None:
        cfg = load_config()
        self.state = state
        self.app = Application.builder().token(cfg.telegram_token).build()
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("stop", self.cmd_stop))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        self.state.add_chat(chat_id)
        await context.bot.send_message(chat_id=chat_id, text="Подписка оформлена. Буду присылать новые объявления.")

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        self.state.remove_chat(chat_id)
        await context.bot.send_message(chat_id=chat_id, text="Подписка отменена. Больше не буду присылать.")

    async def broadcast(self, items: Iterable[Listing]) -> None:
        if not self.state.chat_ids:
            return
        text_chunks = [format_listing_message(i) for i in items]
        for chat_id in list(self.state.chat_ids):
            for text in text_chunks:
                try:
                    await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                except Exception:
                    # Ошибки чата игнорируем, чтобы не падал процесс
                    continue

    async def notify_no_updates(self, count: int) -> None:
        if not self.state.chat_ids:
            return
        text = f"За последние {count} циклов (по 60 сек) новых объявлений не появилось."
        for chat_id in list(self.state.chat_ids):
            try:
                await self.app.bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                continue

    def run_polling(self) -> None:
        self.app.run_polling(close_loop=False)

