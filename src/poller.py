from datetime import datetime
from typing import List
import logging
import time

from .config import load_config
from .state import StateStore
from .bot import BotApp
from .scrapers.kufar import fetch_kufar
from .scrapers.domovita import fetch_domovita
from .scrapers.realt import fetch_realt


async def poll_once(state: StateStore, bot: BotApp) -> None:
    logger = logging.getLogger("poller")
    t0 = time.perf_counter()
    cfg = load_config()

    # Первый запуск: прогреваем кэш и выходим без рассылки
    if not state.seen_ids_by_source:
        try:
            for src, url, fetch in (
                ("kufar", cfg.kufar_url, fetch_kufar),
                ("domovita", cfg.domovita_url, fetch_domovita),
                ("realt", cfg.realt_url, fetch_realt),
            ):
                items = fetch(url)
                state.mark_seen(src, {i.id for i in items})
        except Exception:
            pass
        return

    new_items: List = []
    kufar_fetched = 0
    kufar_new = 0

    try:
        kufar_items = fetch_kufar(cfg.kufar_url)
        kufar_fetched = len(kufar_items)
        fresh = [i for i in kufar_items if state.is_new("kufar", i.id)]
        kufar_new = len(fresh)
        if fresh:
            state.mark_seen("kufar", {i.id for i in fresh})
            new_items.extend(fresh)
    except Exception as e:
        logger.warning("kufar fetch failed: %s", e)

    domovita_fetched = 0
    domovita_new = 0
    try:
        domovita_items = fetch_domovita(cfg.domovita_url)
        domovita_fetched = len(domovita_items)
        fresh = [i for i in domovita_items if state.is_new("domovita", i.id)]
        domovita_new = len(fresh)
        if fresh:
            state.mark_seen("domovita", {i.id for i in fresh})
            new_items.extend(fresh)
    except Exception as e:
        logger.warning("domovita fetch failed: %s", e)

    realt_fetched = 0
    realt_new = 0
    try:
        realt_items = fetch_realt(cfg.realt_url)
        realt_fetched = len(realt_items)
        fresh = [i for i in realt_items if state.is_new("realt", i.id)]
        realt_new = len(fresh)
        if fresh:
            state.mark_seen("realt", {i.id for i in fresh})
            new_items.extend(fresh)
    except Exception as e:
        logger.warning("realt fetch failed: %s", e)

    if new_items:
        state.reset_empty_cycles()
        await bot.broadcast(new_items)
    else:
        empty = state.increment_empty_cycle()
        if empty % 5 == 0:
            await bot.notify_no_updates(empty)

    duration = time.perf_counter() - t0
    total_new = len(new_items)
    logger.info(
        "cycle: %.2fs | kufar fetched=%d new=%d | domovita fetched=%d new=%d | realt fetched=%d new=%d | total_new=%d | empty_cycles=%d",
        duration, kufar_fetched, kufar_new, domovita_fetched, domovita_new, realt_fetched, realt_new, total_new, state.empty_cycles,
    )

