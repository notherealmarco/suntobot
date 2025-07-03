import logging

from PIL import Image
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import DatabaseManager
from image_analyzer import ImageAnalyzer

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.image_analyzer = ImageAnalyzer()

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message

        if message.chat_id not in Config.WHITELISTED_GROUPS:
            return

        user_id = message.from_user.id
        username = message.from_user.username
        chat_id = message.chat_id
        message_id = message.message_id
        message_text = message.text
        image_description = None

        if message.photo:
            try:
                image_description = await self._process_image(message, context)
                logger.info(f"Image analyzed: {image_description}")
            except Exception as e:
                logger.error(f"Failed to process/analyze image: {e}")

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
        photo = message.photo[-1]

        file = await context.bot.get_file(photo.file_id)
        image_bytes = BytesIO()
        await file.download_to_memory(image_bytes)
        image_bytes.seek(0)

        compressed_image_data = await self._compress_image_in_memory(image_bytes)

        if compressed_image_data:
            return await self.image_analyzer.analyze_image_data(compressed_image_data)

        return None

    async def _compress_image_in_memory(
        self, image_bytes: BytesIO, max_size: tuple = (1024, 1024), quality: int = 85
    ) -> bytes:
        try:
            with Image.open(image_bytes) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                output = BytesIO()
                img.save(output, "JPEG", quality=quality, optimize=True)
                return output.getvalue()

        except Exception as e:
            logger.error(f"Failed to compress image in memory: {e}")
            return None
