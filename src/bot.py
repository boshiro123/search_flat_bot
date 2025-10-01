from typing import Iterable
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

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
        self.app.add_handler(CallbackQueryHandler(self.cb_latest, pattern=r"^latest:(kufar|domovita|realt)$"))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        self.state.add_chat(chat_id)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(text="Kufar — последнее", callback_data="latest:kufar"),
                InlineKeyboardButton(text="Domovita — последнее", callback_data="latest:domovita"),
                InlineKeyboardButton(text="Realt — последнее", callback_data="latest:realt"),
            ]
        ])
        await context.bot.send_message(chat_id=chat_id, text="Подписка оформлена. Выберите источник, чтобы получить последнее объявление:", reply_markup=keyboard)

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

    async def cb_latest(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        source = query.data.split(":", 1)[1]
        # Дальнейшая логика реализуется в main через общие функции, чтобы не плодить дублирование
        # Здесь просто проксируем событие через job_queue в общий обработчик, но проще — подтянуть прямо тут
        from .config import load_config
        from .scrapers.kufar import fetch_kufar
        from .scrapers.domovita import fetch_domovita
        from .scrapers.realt import fetch_realt
        from .browser import fetch_rendered_html
        from .scrapers.kufar import parse_kufar_html
        from .scrapers.domovita import parse_domovita_html
        from .scrapers.realt import parse_realt_html

        cfg = load_config()
        url_map = {
            "kufar": cfg.kufar_url,
            "domovita": cfg.domovita_url,
            "realt": cfg.realt_url,
        }
        url = url_map[source]

        # 1) пробуем обычный fetch
        if source == "kufar":
            items = fetch_kufar(url)
        elif source == "domovita":
            items = fetch_domovita(url)
        else:
            items = fetch_realt(url)

        # 2) если пусто — fallback на рендер
        if not items:
            try:
                wait_sel = {
                    "kufar": "a[href*='/item/']",
                    "domovita": "a[href*='/rent/']",
                    "realt": "a[href*='/rent/flat-for-long/']",
                }[source]
                html = await fetch_rendered_html(url, wait_selector=wait_sel)
                if source == "kufar":
                    items = parse_kufar_html(html)
                elif source == "domovita":
                    items = parse_domovita_html(html)
                else:
                    items = parse_realt_html(html)
            except Exception:
                items = []

        if not items:
            await query.edit_message_text(text="Ничего не нашлось. Попробуйте позже.")
            return

        latest = items[0]
        await query.edit_message_text(text=format_listing_message(latest))

    def run_polling(self) -> None:
        self.app.run_polling(close_loop=False)

