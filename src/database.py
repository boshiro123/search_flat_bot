"""
Модели базы данных и работа с PostgreSQL
"""
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, JSON, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from sqlalchemy.pool import QueuePool

Base = declarative_base()


class User(Base):
    """Пользователь или канал"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(50), unique=True, nullable=False, index=True)
    chat_type = Column(String(20), nullable=False, default="private")  # private, channel, group
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # Роль администратора
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    filters = relationship("UserFilter", back_populates="user", cascade="all, delete-orphan")
    seen_listings = relationship("SeenListing", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(chat_id={self.chat_id}, type={self.chat_type}, is_admin={self.is_admin})>"


class UserFilter(Base):
    """Фильтры пользователя"""
    __tablename__ = "user_filters"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Фильтры по цене
    min_price = Column(Integer, default=0)
    max_price = Column(Integer, default=350)
    
    # Фильтры по количеству комнат (JSON список: [1, 2, 3])
    rooms = Column(JSON, nullable=True)
    
    # Фильтры по источникам (JSON список: ["kufar", "domovita", "realt"])
    sources = Column(JSON, nullable=True)
    
    # Фильтры по районам/метро (JSON список)
    districts = Column(JSON, nullable=True)
    metro_stations = Column(JSON, nullable=True)
    
    # Дополнительные фильтры
    keywords_include = Column(JSON, nullable=True)  # Ключевые слова, которые должны быть в объявлении
    keywords_exclude = Column(JSON, nullable=True)  # Ключевые слова, которых НЕ должно быть
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="filters")
    
    def __repr__(self):
        return f"<UserFilter(user_id={self.user_id}, price={self.min_price}-{self.max_price}, rooms={self.rooms})>"


class SeenListing(Base):
    """Просмотренные объявления пользователем"""
    __tablename__ = "seen_listings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(50), nullable=False)  # kufar, domovita, realt
    listing_id = Column(String(255), nullable=False)
    seen_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="seen_listings")
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index("idx_user_source_listing", "user_id", "source", "listing_id", unique=True),
        Index("idx_source_listing", "source", "listing_id"),
    )
    
    def __repr__(self):
        return f"<SeenListing(user_id={self.user_id}, source={self.source}, listing_id={self.listing_id})>"


class GlobalState(Base):
    """Глобальное состояние бота (замена state.json)"""
    __tablename__ = "global_state"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<GlobalState(key={self.key})>"


class LastDateBySource(Base):
    """Последняя дата поста для каждого источника"""
    __tablename__ = "last_dates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), unique=True, nullable=False, index=True)
    last_date = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<LastDateBySource(source={self.source}, last_date={self.last_date})>"


class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, database_url: Optional[str] = None):
        if database_url is None:
            database_url = os.getenv(
                "DATABASE_URL",
                "postgresql://bot_user:bot_password@localhost:5432/search_flat_bot"
            )
        
        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False
        )
        
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)
    
    def create_tables(self):
        """Создание всех таблиц"""
        Base.metadata.create_all(self.engine)
    
    def drop_tables(self):
        """Удаление всех таблиц (для тестов)"""
        Base.metadata.drop_all(self.engine)
    
    def get_session(self):
        """Получение сессии для работы с БД"""
        return self.Session()
    
    def close(self):
        """Закрытие всех соединений"""
        self.Session.remove()
        self.engine.dispose()
    
    # === Методы для работы с пользователями ===
    
    def add_user(self, chat_id: str, chat_type: str = "private", 
                 username: Optional[str] = None, first_name: Optional[str] = None) -> User:
        """Добавление нового пользователя или возврат существующего"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if user:
                # Обновляем данные если изменились
                user.is_active = True
                user.chat_type = chat_type
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                user.updated_at = datetime.utcnow()
            else:
                user = User(
                    chat_id=str(chat_id),
                    chat_type=chat_type,
                    username=username,
                    first_name=first_name,
                    is_active=True
                )
                session.add(user)
                
                # Создаем фильтр по умолчанию
                default_filter = UserFilter(
                    user=user,
                    min_price=0,
                    max_price=350,
                    sources=["kufar", "domovita", "realt"]
                )
                session.add(default_filter)
            
            session.commit()
            session.refresh(user)
            return user
        finally:
            session.close()
    
    def remove_user(self, chat_id: str) -> bool:
        """Деактивация пользователя"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if user:
                user.is_active = False
                user.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def get_active_users(self) -> List[User]:
        """Получение всех активных пользователей"""
        session = self.get_session()
        try:
            return session.query(User).filter(User.is_active == True).all()
        finally:
            session.close()
    
    def get_user_by_chat_id(self, chat_id: str) -> Optional[User]:
        """Получение пользователя по chat_id"""
        session = self.get_session()
        try:
            return session.query(User).filter(User.chat_id == str(chat_id)).first()
        finally:
            session.close()
    
    def set_admin(self, chat_id: str, is_admin: bool = True) -> bool:
        """Установка/снятие роли администратора"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if user:
                user.is_admin = is_admin
                user.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def is_admin(self, chat_id: str) -> bool:
        """Проверка, является ли пользователь администратором"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            return user.is_admin if user else False
        finally:
            session.close()
    
    # === Методы для работы с фильтрами ===
    
    def get_user_filter(self, chat_id: str) -> Optional[UserFilter]:
        """Получение активного фильтра пользователя"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if not user:
                return None
            return session.query(UserFilter).filter(
                UserFilter.user_id == user.id,
                UserFilter.is_active == True
            ).first()
        finally:
            session.close()
    
    def update_user_filter(self, chat_id: str, **kwargs) -> Optional[UserFilter]:
        """Обновление фильтра пользователя"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if not user:
                return None
            
            user_filter = session.query(UserFilter).filter(
                UserFilter.user_id == user.id,
                UserFilter.is_active == True
            ).first()
            
            if not user_filter:
                user_filter = UserFilter(user_id=user.id)
                session.add(user_filter)
            
            for key, value in kwargs.items():
                if hasattr(user_filter, key):
                    setattr(user_filter, key, value)
            
            user_filter.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(user_filter)
            return user_filter
        finally:
            session.close()
    
    # === Методы для работы с просмотренными объявлениями ===
    
    def is_listing_seen(self, chat_id: str, source: str, listing_id: str) -> bool:
        """Проверка, видел ли пользователь это объявление"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if not user:
                return False
            
            exists = session.query(SeenListing).filter(
                SeenListing.user_id == user.id,
                SeenListing.source == source,
                SeenListing.listing_id == listing_id
            ).first() is not None
            
            return exists
        finally:
            session.close()
    
    def mark_listing_seen(self, chat_id: str, source: str, listing_id: str):
        """Отметить объявление как просмотренное"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if not user:
                return
            
            # Проверяем, не было ли уже
            exists = session.query(SeenListing).filter(
                SeenListing.user_id == user.id,
                SeenListing.source == source,
                SeenListing.listing_id == listing_id
            ).first()
            
            if not exists:
                seen = SeenListing(
                    user_id=user.id,
                    source=source,
                    listing_id=listing_id
                )
                session.add(seen)
                session.commit()
        finally:
            session.close()
    
    def get_seen_count(self, chat_id: str) -> int:
        """Получить количество просмотренных объявлений пользователем"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.chat_id == str(chat_id)).first()
            if not user:
                return 0
            return session.query(SeenListing).filter(SeenListing.user_id == user.id).count()
        finally:
            session.close()
    
    # === Методы для глобального состояния ===
    
    def get_global_value(self, key: str) -> Optional[str]:
        """Получение глобального значения"""
        session = self.get_session()
        try:
            state = session.query(GlobalState).filter(GlobalState.key == key).first()
            return state.value if state else None
        finally:
            session.close()
    
    def set_global_value(self, key: str, value: str):
        """Установка глобального значения"""
        session = self.get_session()
        try:
            state = session.query(GlobalState).filter(GlobalState.key == key).first()
            if state:
                state.value = value
                state.updated_at = datetime.utcnow()
            else:
                state = GlobalState(key=key, value=value)
                session.add(state)
            session.commit()
        finally:
            session.close()
    
    # === Методы для работы с датами последних постов ===
    
    def get_last_date(self, source: str) -> Optional[datetime]:
        """Получение последней даты поста для источника"""
        session = self.get_session()
        try:
            record = session.query(LastDateBySource).filter(LastDateBySource.source == source).first()
            if record and record.last_date:
                # Нормализуем дату к UTC с timezone
                if record.last_date.tzinfo is None:
                    return record.last_date.replace(tzinfo=timezone.utc)
                return record.last_date.astimezone(timezone.utc)
            return None
        finally:
            session.close()
    
    def update_last_date(self, source: str, last_date: datetime):
        """Обновление последней даты поста для источника"""
        session = self.get_session()
        try:
            # Нормализуем входящую дату к UTC
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=timezone.utc)
            else:
                last_date = last_date.astimezone(timezone.utc)
            
            record = session.query(LastDateBySource).filter(LastDateBySource.source == source).first()
            if record:
                # Нормализуем сохраненную дату для сравнения
                saved_date = record.last_date
                if saved_date and saved_date.tzinfo is None:
                    saved_date = saved_date.replace(tzinfo=timezone.utc)
                
                if not saved_date or last_date > saved_date:
                    record.last_date = last_date
                    record.updated_at = datetime.utcnow()
            else:
                record = LastDateBySource(source=source, last_date=last_date)
                session.add(record)
            session.commit()
        finally:
            session.close()
    
    def get_all_last_dates(self) -> Dict[str, Optional[datetime]]:
        """Получение всех последних дат"""
        session = self.get_session()
        try:
            records = session.query(LastDateBySource).all()
            return {r.source: r.last_date for r in records}
        finally:
            session.close()
    
    # === Методы для счетчика пустых циклов ===
    
    def get_empty_cycles(self) -> int:
        """Получение количества пустых циклов"""
        value = self.get_global_value("empty_cycles")
        return int(value) if value else 0
    
    def increment_empty_cycles(self) -> int:
        """Инкремент пустых циклов"""
        count = self.get_empty_cycles() + 1
        self.set_global_value("empty_cycles", str(count))
        return count
    
    def reset_empty_cycles(self):
        """Сброс счетчика пустых циклов"""
        self.set_global_value("empty_cycles", "0")
    
    def get_max_price_from_filters(self) -> int:
        """Получение максимальной цены из всех активных фильтров"""
        session = self.get_session()
        try:
            result = session.query(UserFilter.max_price).join(User).filter(
                User.is_active == True,
                UserFilter.is_active == True
            ).order_by(UserFilter.max_price.desc()).first()
            return result[0] if result else 350
        finally:
            session.close()

