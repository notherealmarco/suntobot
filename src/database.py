from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(255))
    message_text = Column(Text)
    image_description = Column(Text)  # AI-generated description of the image
    has_photo = Column(Boolean, default=False)  # Track if message contained a photo
    timestamp = Column(DateTime, default=func.current_timestamp())
    message_id = Column(BigInteger, unique=True, nullable=False)

    # Forwarded message information
    is_forwarded = Column(Boolean, default=False)
    forward_from_username = Column(String(255))  # Original author's username
    forward_from = Column(String(255))  # Chat type

    __table_args__ = (
        Index("idx_messages_chat_user_time", "chat_id", "user_id", "timestamp"),
    )


class AllowedGroup(Base):
    __tablename__ = "allowed_groups"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, nullable=False)
    chat_title = Column(String(255))
    allowed_by_admin_id = Column(BigInteger, nullable=False)
    allowed_at = Column(DateTime, default=func.current_timestamp())
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_allowed_groups_chat_id", "chat_id"),
        Index("idx_allowed_groups_active", "is_active"),
    )


class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        # Remove Base.metadata.create_all() - use Alembic migrations instead
        # Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def get_session(self):
        return self.SessionLocal()

    def save_message(
        self,
        chat_id: int,
        user_id: int,
        username: Optional[str],
        message_text: Optional[str],
        image_description: Optional[str],
        message_id: int,
        has_photo: bool = False,
        is_forwarded: bool = False,
        forward_from_username: Optional[str] = None,
        forward_from: Optional[str] = None,
    ) -> None:
        session = self.get_session()
        try:
            message = Message(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                message_text=message_text,
                image_description=image_description,
                message_id=message_id,
                has_photo=has_photo,
                is_forwarded=is_forwarded,
                forward_from_username=forward_from_username,
                forward_from=forward_from,
            )
            session.add(message)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_messages_since(
        self, chat_id: int, user_id: int, since_timestamp: datetime
    ) -> List[Message]:
        session = self.get_session()
        try:
            messages = (
                session.query(Message)
                .filter(
                    Message.chat_id == chat_id, Message.timestamp >= since_timestamp
                )
                .order_by(Message.timestamp.asc())
                .all()
            )
            return messages
        finally:
            session.close()

    def get_context_for_mention(
        self, chat_id: int, limit: int = 30, hours_back: int = 4
    ) -> List[Message]:
        """Get recent messages for mention reply context."""
        from datetime import timedelta

        session = self.get_session()
        try:
            # Get messages from the last N hours or last N messages, whichever is smaller
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)

            messages = (
                session.query(Message)
                .filter(
                    Message.chat_id == chat_id, Message.timestamp >= cutoff_time
                )
                .order_by(Message.timestamp.desc())
                .limit(limit)
                .all()
            )

            # Return in chronological order (oldest first)
            return list(reversed(messages))
        finally:
            session.close()

    def get_message_by_message_id(self, message_id: int) -> Optional[Message]:
        """Get a specific message by its Telegram message ID."""
        session = self.get_session()
        try:
            message = (
                session.query(Message)
                .filter(Message.message_id == message_id)
                .first()
            )
            return message
        finally:
            session.close()

    def allow_group(self, chat_id: int, chat_title: str, admin_id: int) -> None:
        """Allow a group to use the bot."""
        session = self.get_session()
        try:
            # Check if group already exists
            existing = (
                session.query(AllowedGroup)
                .filter(AllowedGroup.chat_id == chat_id)
                .first()
            )

            if existing:
                # Reactivate if it was disabled
                existing.is_active = True
                existing.allowed_by_admin_id = admin_id
                existing.chat_title = chat_title
            else:
                # Create new entry
                allowed_group = AllowedGroup(
                    chat_id=chat_id,
                    chat_title=chat_title,
                    allowed_by_admin_id=admin_id,
                    is_active=True,
                )
                session.add(allowed_group)

            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def deny_group(self, chat_id: int) -> bool:
        """Deny a group from using the bot."""
        session = self.get_session()
        try:
            group = (
                session.query(AllowedGroup)
                .filter(AllowedGroup.chat_id == chat_id)
                .first()
            )

            if group:
                group.is_active = False
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def is_group_allowed(self, chat_id: int) -> bool:
        """Check if a group is allowed to use the bot."""
        session = self.get_session()
        try:
            group = (
                session.query(AllowedGroup)
                .filter(AllowedGroup.chat_id == chat_id, AllowedGroup.is_active)
                .first()
            )

            return group is not None
        finally:
            session.close()

    def get_allowed_groups(self) -> List[AllowedGroup]:
        """Get all allowed groups."""
        session = self.get_session()
        try:
            groups = (
                session.query(AllowedGroup)
                .filter(AllowedGroup.is_active)
                .order_by(AllowedGroup.chat_title)
                .all()
            )

            return groups
        finally:
            session.close()

    def get_context_around_message(
        self, chat_id: int, target_timestamp: datetime, context_limit: int = 10
    ) -> List[Message]:
        """Get messages around a specific timestamp for better context."""
        session = self.get_session()
        try:
            # Get messages before the target timestamp
            messages_before = (
                session.query(Message)
                .filter(
                    Message.chat_id == chat_id,
                    Message.timestamp < target_timestamp
                )
                .order_by(Message.timestamp.desc())
                .limit(context_limit // 2)
                .all()
            )

            # Get messages after the target timestamp  
            messages_after = (
                session.query(Message)
                .filter(
                    Message.chat_id == chat_id,
                    Message.timestamp > target_timestamp
                )
                .order_by(Message.timestamp.asc())
                .limit(context_limit // 2)
                .all()
            )

            # Combine and sort chronologically
            all_messages = list(reversed(messages_before)) + messages_after
            return sorted(all_messages, key=lambda m: m.timestamp)
        finally:
            session.close()
