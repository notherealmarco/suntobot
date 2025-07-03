"""Message handling for the Telegram bot."""

import os
import uuid
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image
import logging

from config import Config
from database import DatabaseManager

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming Telegram messages."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages."""
        message = update.message

        # Only process messages from whitelisted groups
        if message.chat_id not in Config.WHITELISTED_GROUPS:
            return

        user_id = message.from_user.id
        username = message.from_user.username
        chat_id = message.chat_id
        message_id = message.message_id
        message_text = message.text
        image_path = None

        # Handle images
        if message.photo:
            try:
                image_path = await self._save_image(message, context)
            except Exception as e:
                logger.error(f"Failed to save image: {e}")

        # Save message to database
        try:
            self.db_manager.save_message(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                message_text=message_text,
                image_path=image_path,
                message_id=message_id,
            )
            logger.debug(f"Saved message {message_id} from user {username}")
        except Exception as e:
            logger.error(f"Failed to save message to database: {e}")

    async def _save_image(self, message, context) -> str:
        """Download and save image from message."""
        # Get the largest photo size
        photo = message.photo[-1]

        # Generate unique filename
        file_extension = ".jpg"
        filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(Config.IMAGE_BASE_DIR, filename)

        # Download the file
        file = await context.bot.get_file(photo.file_id)
        await file.download_to_drive(file_path)

        # Compress the image
        await self._compress_image(file_path)

        return file_path

    async def _compress_image(
        self, file_path: str, max_size: tuple = (1024, 1024), quality: int = 85
    ):
        """Compress image to reduce file size."""
        try:
            with Image.open(file_path) as img:
                # Convert to RGB if necessary
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Resize if necessary
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save with compression
                img.save(file_path, "JPEG", quality=quality, optimize=True)

        except Exception as e:
            logger.error(f"Failed to compress image {file_path}: {e}")
