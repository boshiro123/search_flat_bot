from typing import Iterable, List, Dict
import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from .config import load_config
from .state import StateStore
from .models import Listing
from .database import UserFilter

# Состояния для conversation handlers
WAITING_FOR_PRICE_MAX = 1


def format_listing_message(item: Listing, chat_type: str = "private") -> str:
    """Форматирование сообщения об объявлении"""
    parts = [
        f"🏠 <b>{item.source.upper()}</b>",
        f"📝 {item.title}" if item.title else None,
        f"💰 {item.price}" if item.price else None,
        f"📍 {item.location}" if item.location else None,
        f"🔗 <a href='{item.url}'>Перейти к объявлению</a>",
    ]
    return "\n".join([p for p in parts if p])


def matches_filter(item: Listing, user_filter: UserFilter) -> bool:
    """
    Проверка, соответствует ли объявление фильтру пользователя
    
    Args:
        item: Объявление
        user_filter: Фильтр пользователя
    
    Returns:
        True если объявление подходит под фильтр
    """
    # Фильтр по источнику
    if user_filter.sources and item.source not in user_filter.sources:
        return False
    
    # Фильтр по цене (только максимальная)
    if item.price:
        try:
            # Извлекаем числовое значение из строки цены
            price_match = re.search(r'(\d+(?:\.\d+)?)', item.price.replace(',', ''))
            if price_match:
                price_value = float(price_match.group(1))
                if price_value > user_filter.max_price:
                    return False
        except (ValueError, AttributeError):
            pass
    
    return True


class BotApp:
    def __init__(self, state: StateStore) -> None:
        cfg = load_config()
        self.state = state
        self.app = Application.builder().token(cfg.telegram_token).build()
        
        # Основные команды (обрабатываем и обычные сообщения, и channel_post)
        self.app.add_handler(CommandHandler("start", self.cmd_start, filters=filters.ChatType.PRIVATE | filters.ChatType.CHANNEL | filters.ChatType.GROUPS))
        self.app.add_handler(CommandHandler("stop", self.cmd_stop, filters=filters.ChatType.PRIVATE | filters.ChatType.CHANNEL | filters.ChatType.GROUPS))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        
        # Команды для просмотра последних объявлений
        self.app.add_handler(CommandHandler("kufar", self.cmd_kufar))
        self.app.add_handler(CommandHandler("domovita", self.cmd_domovita))
        self.app.add_handler(CommandHandler("realt", self.cmd_realt))
        
        # Информационные команды
        self.app.add_handler(CommandHandler("myfilter", self.cmd_show_filter))
        
        # Секретная команда для получения прав администратора
        self.app.add_handler(CommandHandler("g8ve_8adm1N_2_m3", self.cmd_become_admin))
        
        # Conversation handler для настройки фильтров
        filter_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("filter", self.cmd_filter)],
            states={
                WAITING_FOR_PRICE_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_price_max)],
            },
            fallbacks=[CommandHandler("cancel", self.cmd_cancel)],
        )
        self.app.add_handler(filter_conv_handler)
        
        # Callback handlers
        self.app.add_handler(CallbackQueryHandler(self.cb_delete, pattern=r"^delete$"))
        
        # Error handler
        self.app.add_error_handler(self.error_handler)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /start - подписка на уведомления"""
        chat = update.effective_chat
        user = update.effective_user
        
        # Определяем тип чата
        chat_type = chat.type
        if chat_type in [ChatType.PRIVATE]:
            chat_type_str = "private"
            username = user.username if user else None
            first_name = user.first_name if user else None
        elif chat_type in [ChatType.CHANNEL]:
            chat_type_str = "channel"
            username = chat.title
            first_name = None
        elif chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            chat_type_str = "group"
            username = chat.title
            first_name = None
        else:
            chat_type_str = "private"
            username = None
            first_name = None
        
        # Проверка: если это канал/группа, то может быть только один активный
        if chat_type_str in ["channel", "group"]:
            # Получаем все активные каналы/группы (кроме текущего)
            active_channels = [
                u for u in self.state.get_active_chats() 
                if u.chat_type in ["channel", "group"] and u.chat_id != str(chat.id)
            ]
            
            if active_channels:
                # Уже есть активный канал/группа
                active = active_channels[0]
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"❌ <b>Бот уже используется другим каналом!</b>\n\n",
                    parse_mode=ParseMode.HTML
                )
                return
        
        # Добавляем/активируем пользователя в БД
        self.state.add_chat(chat.id, chat_type_str, username, first_name)
        
        if chat_type_str == "private":
            keyboard = ReplyKeyboardMarkup([
                [KeyboardButton("/kufar"), KeyboardButton("/domovita"), KeyboardButton("/realt")],
                [KeyboardButton("/filter"), KeyboardButton("/myfilter")],
                [KeyboardButton("/help")],
            ], resize_keyboard=True)
            
            await context.bot.send_message(
                chat_id=chat.id,
                text="✅ <b>Подписка оформлена!</b>\n\n"
                     "Я буду присылать вам новые объявления о сдаче квартир в Минске.\n\n"
                     "📋 <b>Доступные команды:</b>\n"
                     "• /filter - настроить максимальную цену\n"
                     "• /myfilter - посмотреть текущие настройки\n"
                     "• /kufar, /domovita, /realt - последние объявления\n"
                     "• /stop - отменить подписку",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        else:
            # Для каналов/групп без клавиатуры
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"✅ <b>Канал/группа подключен!</b>\n\n"
                     f"Буду присылать новые объявления сюда.\n\n"
                     f"Для настройки фильтров напишите боту в личные сообщения.",
                parse_mode=ParseMode.HTML
            )

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /stop - отписка от уведомлений"""
        chat_id = update.effective_chat.id
        self.state.remove_chat(chat_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Подписка отменена. Больше не буду присылать уведомления."
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Команда /help - справка"""
        help_text = """
<b>🤖 Помощь по боту</b>

<b>Основные команды:</b>
• /start - оформить подписку
• /stop - отменить подписку
• /filter - настроить максимальную цену
• /myfilter - посмотреть текущие настройки

<b>Просмотр объявлений:</b>
• /kufar - последнее с Kufar
• /domovita - последнее с Domovita
• /realt - последнее с Realt.by

<b>💡 Фильтры:</b>
Вы можете настроить максимальную цену, до которой вы хотите видеть объявления.

<b>📢 Каналы:</b>
Бот может работать в каналах! Просто добавьте его как администратора с правом публикации сообщений.
        """
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=help_text.strip(),
            parse_mode=ParseMode.HTML
        )

    async def cmd_kufar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_latest(update, context, "kufar")

    async def cmd_domovita(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_latest(update, context, "domovita")

    async def cmd_realt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_latest(update, context, "realt")

    async def cmd_show_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать текущий фильтр пользователя"""
        chat_id = update.effective_chat.id
        user_filter = self.state.get_user_filter(chat_id)
        
        if not user_filter:
            await context.bot.send_message(
                chat_id=chat_id,
                text="У вас еще нет настроенных фильтров. Используйте /filter для настройки."
            )
            return
        
        lines = [
            "<b>🔍 Ваши текущие настройки:</b>\n",
            f"💰 Максимальная цена: {user_filter.max_price} USD",
            f"📱 Источники: Kufar, Domovita, Realt.by",
            "\n💡 Используйте /filter для изменения"
        ]
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode=ParseMode.HTML
        )

    # === Conversation handler для настройки фильтров ===
    
    async def cmd_become_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Секретная команда для получения прав администратора"""
        chat = update.effective_chat
        user = update.effective_user
        
        # Работает только в личных чатах
        if chat.type != ChatType.PRIVATE:
            return
        
        # Даем права администратора
        self.state.set_admin(user.id, True)
        
        await context.bot.send_message(
            chat_id=chat.id,
            text="✅ <b>Вы получили права администратора!</b>\n\n"
                 "Теперь вы можете:\n"
                 "• Настраивать фильтры для каналов через /filter\n"
                 "• Управлять настройками бота",
            parse_mode=ParseMode.HTML
        )
    
    async def cmd_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начало настройки фильтра"""
        chat = update.effective_chat
        user = update.effective_user
        
        # Если это канал - проверяем права администратора
        if chat.type in [ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP]:
            if not self.state.is_admin(user.id):
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="❌ Только администраторы могут настраивать фильтры для каналов.\n\n"
                         "Для получения прав администратора напишите боту в личные сообщения."
                )
                return ConversationHandler.END
        
        chat_id = chat.id
        
        # Получаем текущую цену
        user_filter = self.state.get_user_filter(chat_id)
        current_price = user_filter.max_price if user_filter else 350
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"<b>⚙️ Настройка фильтра</b>\n\n"
                 f"Текущая максимальная цена: {current_price} USD\n\n"
                 f"Введите новую максимальную цену в USD (или /cancel для отмены):",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FOR_PRICE_MAX
    
    async def handle_price_max(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка максимальной цены"""
        chat_id = update.effective_chat.id
        text = update.message.text.strip()
        
        try:
            max_price = int(text)
            
            if max_price <= 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Цена должна быть положительным числом. Попробуйте еще раз или /cancel:"
                )
                return WAITING_FOR_PRICE_MAX
            
            # Сохраняем фильтр
            self.state.update_user_filter(
                chat_id,
                min_price=0,
                max_price=max_price,
                sources=["kufar", "domovita", "realt"]
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>Фильтр сохранен!</b>\n\n"
                     f"💰 Максимальная цена: {max_price} USD\n"
                     f"📱 Источники: Kufar, Domovita, Realt.by\n\n"
                     f"Теперь вы будете получать только объявления до {max_price} USD.",
                parse_mode=ParseMode.HTML
            )
            return ConversationHandler.END
            
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Пожалуйста, введите число или /cancel для отмены:"
            )
            return WAITING_FOR_PRICE_MAX

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена любого диалога"""
        chat_id = update.effective_chat.id
        await context.bot.send_message(chat_id=chat_id, text="❌ Отменено.")
        context.user_data.clear()
        return ConversationHandler.END

    # === Вспомогательные методы ===

    async def _send_latest(self, update: Update, context: ContextTypes.DEFAULT_TYPE, source: str) -> None:
        """Отправка последнего объявления с конкретного источника"""
        chat_id = update.effective_chat.id
        
        from .config import load_config
        from .scrapers.kufar import fetch_kufar, parse_kufar_html
        from .scrapers.domovita import fetch_domovita, parse_domovita_html
        from .scrapers.realt import fetch_realt, parse_realt_html
        from .browser import fetch_rendered_html

        # Получаем фильтр пользователя для определения цены
        user_filter = self.state.get_user_filter(chat_id)
        max_price = user_filter.max_price if user_filter else 350
        
        cfg = load_config(override_max_price=max_price)
        url_map = {
            "kufar": cfg.kufar_url,
            "domovita": cfg.domovita_url,
            "realt": cfg.realt_url,
        }
        url = url_map[source]

        items = []
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
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось получить данные. Попробуйте позже."
            )
            return

        latest = items[0]
        await context.bot.send_message(
            chat_id=chat_id,
            text=format_listing_message(latest),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False
        )

    async def broadcast(self, items_by_user: Dict[int, List[Listing]]) -> None:
        """
        Рассылка объявлений с учетом индивидуальных фильтров
        
        Args:
            items_by_user: Словарь {chat_id: [список объявлений для этого пользователя]}
        """
        if not items_by_user:
            return
        
        delete_button = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🗑 Удалить", callback_data="delete")]
        ])
        
        for chat_id, items in items_by_user.items():
            if not items:
                continue
            
            # Определяем тип чата
            user = self.state.db.get_user_by_chat_id(str(chat_id))
            chat_type = user.chat_type if user else "private"
            
            for item in items:
                try:
                    text = format_listing_message(item, chat_type)
                    
                    # Для приватных чатов добавляем кнопку удаления
                    reply_markup = delete_button if chat_type == "private" else None
                    
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logging.getLogger("bot").warning(f"Failed to send to {chat_id}: {e}")
                    continue

    async def cb_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Удаление сообщения по кнопке"""
        query = update.callback_query
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            await query.answer("Не удалось удалить сообщение", show_alert=True)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок"""
        logger = logging.getLogger("bot.error")
        logger.error("Exception while handling an update:", exc_info=context.error)

    def run_polling(self) -> None:
        """Запуск бота в режиме polling"""
        self.app.run_polling(close_loop=False)
