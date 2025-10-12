from datetime import datetime
from typing import List, Dict
import logging
import time

from .config import load_config
from .state import StateStore
from .bot import BotApp, matches_filter
from .scrapers.kufar import fetch_kufar, parse_kufar_html
from .scrapers.domovita import fetch_domovita, parse_domovita_html
from .scrapers.realt import fetch_realt, parse_realt_html
from .browser import fetch_rendered_html
from .models import Listing


async def poll_once(state: StateStore, bot: BotApp) -> None:
    """
    Основной цикл парсинга.
    Теперь с поддержкой индивидуальных фильтров для каждого пользователя.
    """
    logger = logging.getLogger("poller")
    t0 = time.perf_counter()
    
    # Получаем максимальную цену из всех пользовательских фильтров
    max_price = state.get_max_price_from_all_users()
    cfg = load_config(override_max_price=max_price)
    logger.info("cycle start (max_price=%d)", max_price)

    # Получаем всех активных пользователей
    active_users = state.get_active_chats()
    if not active_users:
        logger.info("no active users, skipping cycle")
        return
    
    logger.info("active users/channels: %d", len(active_users))

    # Первый запуск: прогреваем кэш
    # Проверяем, есть ли хоть у одного пользователя просмотренные объявления
    has_seen_listings = any(
        state.db.get_seen_count(str(u.chat_id)) > 0 for u in active_users
    )
    
    if not has_seen_listings:
        logger.info("warmup mode: marking all current listings as seen")
        for src, url, fetch in (
            ("kufar", cfg.kufar_url, fetch_kufar),
            ("domovita", cfg.domovita_url, fetch_domovita),
            ("realt", cfg.realt_url, fetch_realt),
        ):
            try:
                items = fetch(url)
                # Отмечаем как просмотренные для всех пользователей
                for user in active_users:
                    state.mark_seen(str(user.chat_id), src, {i.id for i in items})
                # Обновляем даты - находим максимальную дату среди всех объявлений
                if items:
                    items_with_dates = [i for i in items if i.created_at]
                    if items_with_dates:
                        max_date = max(i.created_at for i in items_with_dates)
                        state.update_last_date(src, max_date)
                        logger.info("warmup %s: fetched=%d, max_date=%s", src, len(items), max_date.strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        logger.info("warmup %s: fetched=%d (no dates)", src, len(items))
            except Exception as e:
                logger.warning("warmup %s failed: %s", src, e)
        logger.info("warmup done")
        return

    # === Парсинг всех источников ===
    all_new_items: List[Listing] = []
    kufar_fetched = 0
    kufar_new = 0

    # Kufar
    try:
        kufar_items = fetch_kufar(cfg.kufar_url)
        kufar_fetched = len(kufar_items)
        logger.info("kufar: initial fetch returned %d items", kufar_fetched)
        
        if not kufar_fetched:
            logger.info("kufar: trying playwright fallback")
            try:
                html = await fetch_rendered_html(cfg.kufar_url, wait_selector="a[href*='/item/']")
                kufar_items = parse_kufar_html(html)
                kufar_fetched = len(kufar_items)
                logger.info("kufar: playwright returned %d items", kufar_fetched)
            except Exception as e2:
                logger.warning("kufar playwright fallback failed: %s", e2)
        
        # Собираем новые для каждого пользователя
        for item in kufar_items:
            is_new_for_anyone = False
            for user in active_users:
                if state.is_new(str(user.chat_id), "kufar", item.id, item.created_at):
                    if not is_new_for_anyone:
                        all_new_items.append(item)
                        kufar_new += 1
                        is_new_for_anyone = True
                        # Обновляем last_date ТОЛЬКО для новых объявлений
                        state.update_last_date("kufar", item.created_at)
                        logger.debug("kufar: item %s is new for user %s", item.id, user.chat_id)
        
        logger.info("kufar: fetched=%d globally_new=%d", kufar_fetched, kufar_new)
        if kufar_new > 0:
            logger.info("kufar new sample: %s", ", ".join(f"{i.id}({i.created_at.strftime('%Y-%m-%d %H:%M') if i.created_at else 'no-date'})" for i in kufar_items[:3]))
        
        # Логируем дату последнего поста
        last_date = state.last_date_by_source.get("kufar")
        if last_date:
            logger.info("kufar last post date: %s", last_date.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logger.error("kufar fetch failed: %s", e, exc_info=True)

    # Domovita
    domovita_fetched = 0
    domovita_new = 0
    try:
        domovita_items = fetch_domovita(cfg.domovita_url)
        domovita_fetched = len(domovita_items)
        
        if not domovita_fetched:
            try:
                html = await fetch_rendered_html(cfg.domovita_url, wait_selector="a[href*='/rent/']")
                domovita_items = parse_domovita_html(html)
                domovita_fetched = len(domovita_items)
            except Exception as e2:
                logger.warning("domovita playwright fallback failed: %s", e2)
        
        # Собираем новые
        for item in domovita_items:
            is_new_for_anyone = False
            for user in active_users:
                if state.is_new(str(user.chat_id), "domovita", item.id, item.created_at):
                    if not is_new_for_anyone:
                        all_new_items.append(item)
                        domovita_new += 1
                        is_new_for_anyone = True
                        # Обновляем last_date ТОЛЬКО для новых объявлений
                        state.update_last_date("domovita", item.created_at)
        
        logger.info("domovita: fetched=%d globally_new=%d", domovita_fetched, domovita_new)
        if domovita_new > 0:
            logger.info("domovita new sample urls: %s", ", ".join(i.url for i in domovita_items[:min(3, len(domovita_items))]))
        
        last_date = state.last_date_by_source.get("domovita")
        if last_date:
            logger.info("domovita last post date: %s", last_date.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logger.warning("domovita fetch failed: %s", e)

    # Realt
    realt_fetched = 0
    realt_new = 0
    try:
        realt_items = fetch_realt(cfg.realt_url)
        realt_fetched = len(realt_items)
        
        if not realt_fetched:
            try:
                html = await fetch_rendered_html(cfg.realt_url, wait_selector="a[href*='/rent/flat-for-long/']")
                realt_items = parse_realt_html(html)
                realt_fetched = len(realt_items)
            except Exception as e2:
                logger.warning("realt playwright fallback failed: %s", e2)
        
        # Собираем новые
        for item in realt_items:
            is_new_for_anyone = False
            for user in active_users:
                if state.is_new(str(user.chat_id), "realt", item.id, item.created_at):
                    if not is_new_for_anyone:
                        all_new_items.append(item)
                        realt_new += 1
                        is_new_for_anyone = True
                        # Обновляем last_date ТОЛЬКО для новых объявлений
                        state.update_last_date("realt", item.created_at)
        
        logger.info("realt: fetched=%d globally_new=%d", realt_fetched, realt_new)
        if realt_new > 0:
            logger.info("realt new sample urls: %s", ", ".join(i.url for i in realt_items[:min(3, len(realt_items))]))
        
        last_date = state.last_date_by_source.get("realt")
        if last_date:
            logger.info("realt last post date: %s", last_date.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logger.warning("realt fetch failed: %s", e)

    # === Фильтрация и рассылка ===
    if all_new_items:
        state.reset_empty_cycles()
        
        # Сортируем объявления по дате создания (новые первыми)
        all_new_items.sort(key=lambda x: x.created_at if x.created_at else datetime.min, reverse=True)
        logger.info("sorted %d new items by date (newest first)", len(all_new_items))
        
        # Группируем объявления по пользователям с учетом их фильтров
        items_by_user: Dict[int, List[Listing]] = {}
        
        for user in active_users:
            chat_id = int(user.chat_id)
            user_filter = state.get_user_filter(chat_id)
            
            if not user_filter:
                # Если фильтра нет, показываем все новые объявления
                user_items = [item for item in all_new_items 
                             if state.is_new(str(chat_id), item.source, item.id, item.created_at)]
            else:
                # Применяем фильтр пользователя
                user_items = [
                    item for item in all_new_items
                    if state.is_new(str(chat_id), item.source, item.id, item.created_at)
                    and matches_filter(item, user_filter)
                ]
            
            if user_items:
                items_by_user[chat_id] = user_items
                
                # Отмечаем как просмотренные
                for item in user_items:
                    state.mark_seen(str(chat_id), item.source, {item.id})
                
                logger.info(
                    "user %s: %d items match filter (max_price=%d)",
                    chat_id, len(user_items),
                    user_filter.max_price if user_filter else 999999
                )
        
        # Рассылаем
        if items_by_user:
            await bot.broadcast(items_by_user)
            total_sent = sum(len(items) for items in items_by_user.values())
            logger.info(
                "broadcast complete: %d users received %d total items",
                len(items_by_user), total_sent
            )
        else:
            logger.info("no items matched any user filters")
    else:
        empty = state.increment_empty_cycle()
        logger.info("no new items this cycle, empty_cycles=%d", empty)

    duration = time.perf_counter() - t0
    total_new = len(all_new_items)
    logger.info(
        "cycle complete: %.2fs | kufar=%d/%d | domovita=%d/%d | realt=%d/%d | total_new=%d | empty_cycles=%d",
        duration, kufar_fetched, kufar_new, domovita_fetched, domovita_new,
        realt_fetched, realt_new, total_new, state.empty_cycles,
    )
