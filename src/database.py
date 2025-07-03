from sqlalchemy import (
    BigInteger,
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
    """Model for storing Telegram messages."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(255))
    message_text = Column(Text)
    image_path = Column(String(500))
    timestamp = Column(DateTime, default=func.current_timestamp())
    message_id = Column(BigInteger, unique=True, nullable=False)

    # Index for efficient queries
    __table_args__ = (
        Index("idx_messages_chat_user_time", "chat_id", "user_id", "timestamp"),
    )


class DatabaseManager:
    """Manages database connections and operations."""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def get_session(self):
        """Get a database session."""
        return self.SessionLocal()

    def save_message(
        self,
        chat_id: int,
        user_id: int,
        username: str,
        message_text: str,
        image_path: str,
        message_id: int,
    ):
        """Save a message to the database."""
        session = self.get_session()
        try:
            message = Message(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                message_text=message_text,
                image_path=image_path,
                message_id=message_id,
            )
            session.add(message)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_messages_since(self, chat_id: int, user_id: int, since_timestamp):
        """Get messages since a specific timestamp."""
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

    def get_last_user_message_time(self, chat_id: int, user_id: int):
        """Get the timestamp of the user's last message."""
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
