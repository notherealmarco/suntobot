import logging
import os
import uuid

from PIL import Image
from datetime import datetime
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import DatabaseManager
from image_analyzer import ImageAnalyzer

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming Telegram messages."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.image_analyzer = ImageAnalyzer()

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
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
        image_description = None

        # Handle images
        if message.photo:
            try:
                # Process image in memory and get description
                image_description = await self._process_image(message, context)
                logger.info(f"Image analyzed: {image_description}")
            except Exception as e:
                logger.error(f"Failed to process/analyze image: {e}")

        # Save message to database (no image_path needed anymore)
        try:
            self.db_manager.save_message(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                message_text=message_text,
                image_description=image_description,
                message_id=message_id,
            )
            logger.debug(f"Saved message {message_id} from user {username}")
        except Exception as e:
            logger.error(f"Failed to save message to database: {e}")

    async def _process_image(self, message, context) -> str:
        """Process image in memory and return description."""
        # Get the largest photo size
        photo = message.photo[-1]

        # Download image data into memory
        file = await context.bot.get_file(photo.file_id)
        image_bytes = BytesIO()
        await file.download_to_memory(image_bytes)
        image_bytes.seek(0)

        # Compress the image in memory
        compressed_image_data = await self._compress_image_in_memory(image_bytes)

        # Analyze the image content
        if compressed_image_data:
            return await self.image_analyzer.analyze_image_data(compressed_image_data)

        return None

    async def _compress_image_in_memory(
        self, image_bytes: BytesIO, max_size: tuple = (1024, 1024), quality: int = 85
    ) -> bytes:
        """Compress image in memory and return compressed bytes."""
        try:
            with Image.open(image_bytes) as img:
                # Convert to RGB if necessary
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Resize if necessary
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save compressed image to bytes
                output = BytesIO()
                img.save(output, "JPEG", quality=quality, optimize=True)
                return output.getvalue()

        except Exception as e:
            logger.error(f"Failed to compress image in memory: {e}")
            return None
