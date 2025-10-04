from typing import Iterable
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from .config import load_config
from .state import StateStore
from .models import Listing

# Состояния для conversation handler
WAITING_FOR_PRICE = 1


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
        self.app.add_handler(CommandHandler("kufar", self.cmd_kufar))
        self.app.add_handler(CommandHandler("domovita", self.cmd_domovita))
        self.app.add_handler(CommandHandler("realt", self.cmd_realt))
        self.app.add_handler(CommandHandler("last_dates", self.cmd_last_dates))
        
        # Conversation handler для изменения цены
        price_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("max_price", self.cmd_max_price)],
            states={
                WAITING_FOR_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_new_price)],
            },
            fallbacks=[CommandHandler("cancel", self.cmd_cancel)],
        )
        self.app.add_handler(price_conv_handler)
        
        self.app.add_handler(CallbackQueryHandler(self.cb_latest, pattern=r"^latest:(kufar|domovita|realt)$"))
        self.app.add_handler(CallbackQueryHandler(self.cb_delete, pattern=r"^delete$"))
        self.app.add_error_handler(self.error_handler)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        self.state.add_chat(chat_id)
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("/kufar"), KeyboardButton("/domovita"), KeyboardButton("/realt")],
            [KeyboardButton("/last_dates"), KeyboardButton("/max_price")],
        ], resize_keyboard=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Подписка оформлена. Буду присылать новые объявления.\n\n"
                 "Используйте кнопки ниже для просмотра последних объявлений:",
            reply_markup=keyboard
        )

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        self.state.remove_chat(chat_id)
        await context.bot.send_message(chat_id=chat_id, text="Подписка отменена. Больше не буду присылать.")

    async def cmd_kufar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_latest(update, context, "kufar")

    async def cmd_domovita(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_latest(update, context, "domovita")

    async def cmd_realt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_latest(update, context, "realt")

    async def cmd_last_dates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        lines = ["📅 Дата и время последних постов:\n"]
        
        for source in ["kufar", "domovita", "realt"]:
            last_date = self.state.last_date_by_source.get(source)
            if last_date:
                formatted = last_date.strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"• {source.capitalize()}: {formatted}")
            else:
                lines.append(f"• {source.capitalize()}: Нет данных")
        
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))

    async def cmd_max_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat_id = update.effective_chat.id
        # Получаем текущую цену из state или config
        current_price = self.state.get_max_price()
        if current_price is None:
            cfg = load_config()
            current_price = cfg.max_price
        
        text = (
            f"💰 Текущая максимальная цена: {current_price} USD\n\n"
            f"Введите новую максимальную цену (в USD) или /cancel для отмены:"
        )
        await context.bot.send_message(chat_id=chat_id, text=text)
        return WAITING_FOR_PRICE

    async def handle_new_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat_id = update.effective_chat.id
        text = update.message.text.strip()
        
        try:
            new_price = int(text)
            if new_price <= 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Цена должна быть положительным числом. Попробуйте еще раз или /cancel:"
                )
                return WAITING_FOR_PRICE
            
            # Сохраняем новую цену
            self.state.set_max_price(new_price)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Максимальная цена изменена на {new_price} USD\n\n"
                     f"Новая цена будет применена при следующем цикле парсинга (в течение 60 секунд)."
            )
            return ConversationHandler.END
            
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Пожалуйста, введите корректное число или /cancel для отмены:"
            )
            return WAITING_FOR_PRICE

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat_id = update.effective_chat.id
        await context.bot.send_message(chat_id=chat_id, text="Отменено.")
        return ConversationHandler.END

    async def _send_latest(self, update: Update, context: ContextTypes.DEFAULT_TYPE, source: str) -> None:
        chat_id = update.effective_chat.id
        from .config import load_config
        from .scrapers.kufar import fetch_kufar, parse_kufar_html
        from .scrapers.domovita import fetch_domovita, parse_domovita_html
        from .scrapers.realt import fetch_realt, parse_realt_html
        from .browser import fetch_rendered_html

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
            await context.bot.send_message(chat_id=chat_id, text="Ничего не нашлось. Попробуйте позже.")
            return

        latest = items[0]
        await context.bot.send_message(chat_id=chat_id, text=format_listing_message(latest))

    async def broadcast(self, items: Iterable[Listing]) -> None:
        if not self.state.chat_ids:
            return
        text_chunks = [format_listing_message(i) for i in items]
        delete_button = InlineKeyboardMarkup([[InlineKeyboardButton(text="🗑 Удалить", callback_data="delete")]])
        for chat_id in list(self.state.chat_ids):
            for text in text_chunks:
                try:
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                        reply_markup=delete_button
                    )
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

    async def cb_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            await query.answer("Не удалось удалить сообщение", show_alert=True)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger = logging.getLogger("bot.error")
        logger.error("Exception while handling an update:", exc_info=context.error)
        # Можно отправить уведомление админу, если нужно
        # В данном случае просто логируем

    def run_polling(self) -> None:
        self.app.run_polling(close_loop=False)

