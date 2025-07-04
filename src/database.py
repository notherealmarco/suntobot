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


class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
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

    def get_last_user_message_time(
        self, chat_id: int, user_id: int
    ) -> Optional[datetime]:
        session = self.get_session()
        try:
            last_message = (
                session.query(Message)
                .filter(Message.chat_id == chat_id, Message.user_id == user_id)
                .order_by(Message.timestamp.desc())
                .first()
            )

            return last_message.timestamp if last_message else None
        finally:
            session.close()
            session.close()
