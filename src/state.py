"""
Адаптер для работы с состоянием бота через PostgreSQL
Заменяет старую реализацию на базе JSON
"""
from typing import Dict, Set, Optional, List
from datetime import datetime

from .database import Database, User, UserFilter


class StateStore:
    """
    Адаптер для работы с БД вместо JSON.
    Сохраняет обратную совместимость с существующим кодом.
    """
    
    def __init__(self, db: Optional[Database] = None) -> None:
        self.db = db if db else Database()
        # Создаем таблицы при первом запуске
        self.db.create_tables()
    
    # === Методы для работы с просмотренными объявлениями ===
    
    def is_new(self, chat_id: str, source: str, item_id: str, created_at: Optional[datetime] = None) -> bool:
        """
        Проверка, является ли объявление новым для КОНКРЕТНОГО пользователя/канала.
        
        Args:
            chat_id: ID чата пользователя/канала
            source: Источник (kufar, domovita, realt)
            item_id: ID объявления
            created_at: Дата создания объявления
        
        Returns:
            True если объявление новое для этого пользователя
        """
        # Проверяем, видел ли этот пользователь это объявление
        if self.db.is_listing_seen(chat_id, source, item_id):
            return False
        
        # Если есть дата создания - проверяем глобальную последнюю дату
        if created_at:
            last_date = self.db.get_last_date(source)
            if last_date and created_at < last_date:
                return False
        
        return True
    
    def mark_seen(self, chat_id: str, source: str, ids: Set[str]) -> None:
        """
        Отметить объявления как просмотренные для КОНКРЕТНОГО пользователя/канала
        
        Args:
            chat_id: ID чата пользователя/канала
            source: Источник
            ids: Множество ID объявлений
        """
        for item_id in ids:
            self.db.mark_listing_seen(chat_id, source, item_id)
    
    def update_last_date(self, source: str, date: Optional[datetime]) -> None:
        """Обновление последней даты поста для источника (глобально)"""
        if date:
            self.db.update_last_date(source, date)
    
    @property
    def last_date_by_source(self) -> Dict[str, Optional[datetime]]:
        """Получение словаря последних дат по источникам"""
        return self.db.get_all_last_dates()
    
    # === Методы для работы с пользователями/каналами ===
    
    def add_chat(self, chat_id: int, chat_type: str = "private", 
                 username: Optional[str] = None, first_name: Optional[str] = None) -> None:
        """Добавление чата (пользователя или канала)"""
        self.db.add_user(str(chat_id), chat_type, username, first_name)
    
    def remove_chat(self, chat_id: int) -> None:
        """Удаление (деактивация) чата"""
        self.db.remove_user(str(chat_id))
    
    def get_active_chats(self) -> List[User]:
        """Получение всех активных чатов"""
        return self.db.get_active_users()
    
    @property
    def chat_ids(self) -> Set[int]:
        """Получение множества ID всех активных чатов (для совместимости)"""
        users = self.db.get_active_users()
        return {int(u.chat_id) for u in users}
    
    # === Методы для работы с фильтрами ===
    
    def get_user_filter(self, chat_id: int) -> Optional[UserFilter]:
        """Получение фильтра пользователя"""
        return self.db.get_user_filter(str(chat_id))
    
    def update_user_filter(self, chat_id: int, **kwargs) -> Optional[UserFilter]:
        """Обновление фильтра пользователя"""
        return self.db.update_user_filter(str(chat_id), **kwargs)
    
    def get_max_price_from_all_users(self) -> int:
        """Получение максимальной цены из всех пользовательских фильтров"""
        return self.db.get_max_price_from_filters()
    
    # === Методы для счетчика пустых циклов ===
    
    @property
    def empty_cycles(self) -> int:
        """Получение количества пустых циклов"""
        return self.db.get_empty_cycles()
    
    def increment_empty_cycle(self) -> int:
        """Инкремент пустых циклов"""
        return self.db.increment_empty_cycles()
    
    def reset_empty_cycles(self) -> None:
        """Сброс счетчика пустых циклов"""
        self.db.reset_empty_cycles()
    
    # === Deprecated методы (для обратной совместимости) ===
    
    def set_max_price(self, price: int) -> None:
        """
        DEPRECATED: Глобальная установка цены больше не используется.
        Теперь каждый пользователь имеет свой фильтр.
        Для совместимости сохраняем в глобальное состояние.
        """
        self.db.set_global_value("global_max_price", str(price))
    
    def get_max_price(self) -> Optional[int]:
        """
        DEPRECATED: Возвращает максимальную цену из всех пользовательских фильтров.
        """
        return self.get_max_price_from_all_users()
    
    # === Методы для работы с администраторами ===
    
    def set_admin(self, chat_id: int, is_admin: bool = True) -> bool:
        """Установка/снятие роли администратора"""
        return self.db.set_admin(str(chat_id), is_admin)
    
    def is_admin(self, chat_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        return self.db.is_admin(str(chat_id))
