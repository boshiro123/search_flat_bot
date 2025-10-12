.PHONY: help build up down restart logs clean migrate shell

help: ## Показать это сообщение помощи
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Собрать Docker образы
	docker compose build

up: ## Запустить все сервисы
	docker compose up --build
	@echo "✅ Сервисы запущены!"
	@echo "📱 Telegram бот: работает"
	@echo "🗄️  pgAdmin: http://localhost:5050 (admin@admin.com / admin)"
	@echo "📊 Postgres: localhost:5432"

down: ## Остановить все сервисы
	docker compose down

restart: ## Перезапустить все сервисы
	docker compose restart

logs: ## Показать логи приложения
	docker compose logs -f search-flat-bot

logs-all: ## Показать логи всех сервисов
	docker compose logs -f

clean: ## Удалить все контейнеры и volumes
	docker compose down -v
	@echo "🗑️  Все данные удалены!"

shell: ## Открыть shell в контейнере приложения
	docker compose exec search-flat-bot /bin/bash

db-shell: ## Открыть PostgreSQL shell
	docker compose exec postgres psql -U bot_user -d search_flat_bot

pgadmin: ## Открыть pgAdmin в браузере
	@echo "🗄️  Открываем pgAdmin..."
	@echo "URL: http://localhost:5050"
	@echo "Email: admin@admin.com"
	@echo "Password: admin"
	@open http://localhost:5050 || xdg-open http://localhost:5050 || echo "Откройте вручную: http://localhost:5050"

get-chat-id: ## Запустить скрипт для получения chat_id
	python get_chat_id.py

status: ## Показать статус сервисов
	docker compose ps

