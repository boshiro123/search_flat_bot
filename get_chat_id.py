#!/usr/bin/env python3
"""
Вспомогательный скрипт для получения chat_id вашего канала.

Использование:
1. Запустите этот скрипт: python get_chat_id.py
2. Отправьте любое сообщение в канал (где бот является администратором)
3. Скрипт выведет chat_id канала
4. Добавьте этот ID в .env файл: ALLOWED_CHAT_IDS=ваш_chat_id
"""

import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

if not TELEGRAM_BOT_TOKEN:
    print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в .env файле")
    exit(1)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик любых сообщений"""
    chat = update.effective_chat
    
    print("\n" + "="*60)
    print("📋 Информация о чате:")
    print("="*60)
    print(f"Chat ID: {chat.id}")
    print(f"Тип чата: {chat.type}")
    print(f"Название: {chat.title or chat.first_name or 'N/A'}")
    print(f"Username: @{chat.username}" if chat.username else "Username: нет")
    print("="*60)
    print(f"\n✅ Добавьте эту строку в ваш .env файл:")
    print(f"ALLOWED_CHAT_IDS={chat.id}")
    print("\nЕсли нужно несколько каналов, перечислите через запятую:")
    print(f"ALLOWED_CHAT_IDS={chat.id},-1001234567890,-1009876543210")
    print("="*60 + "\n")
    
    # Отправляем подтверждение в чат
    await context.bot.send_message(
        chat_id=chat.id,
        text=f"✅ Chat ID получен: `{chat.id}`\n\nДобавьте его в .env файл.",
        parse_mode="Markdown"
    )

def main():
    """Запуск бота"""
    print("🤖 Бот запущен и ожидает сообщений...")
    print("📝 Отправьте любое сообщение в канал, чтобы получить chat_id")
    print("🛑 Нажмите Ctrl+C для остановки\n")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Обрабатываем все типы сообщений
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    
    # Запускаем бота
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Бот остановлен")

