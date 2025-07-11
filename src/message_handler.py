import logging

import telegram
from PIL import Image
from io import BytesIO
from telegram import Update
from telegram.constants import MessageOriginType
from telegram.ext import ContextTypes

from config import Config
from database import DatabaseManager
from image_analyzer import ImageAnalyzer
from summary_engine import SummaryEngine, strip_html_tags

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming Telegram messages."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.image_analyzer = ImageAnalyzer()
        self.summary_engine = SummaryEngine(db_manager)
        self.bot_username = None

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming messages."""
        message = update.message

        if not message:
            logger.info("Received an update without a message.")
            return

        # Only process messages from allowed groups
        if not self.db_manager.is_group_allowed(message.chat_id):
            return

        user_id = message.from_user.id
        username = message.from_user.username or " ".join(
            filter(None, [message.from_user.first_name, message.from_user.last_name])
        )
        chat_id = message.chat_id
        message_id = message.message_id
        message_text = message.text
        image_description = None
        has_photo = False

        # Handle reply context - format message text to include reply information
        if message.reply_to_message and message_text:
            reply_author = message.reply_to_message.from_user.username or " ".join(
                filter(
                    None,
                    [
                        message.reply_to_message.from_user.first_name,
                        message.reply_to_message.from_user.last_name,
                    ],
                )
            )
            reply_text = message.reply_to_message.text or ""

            # Check if we're replying to a photo
            replied_to_photo_description = None
            if message.reply_to_message.photo:
                # Try to get the photo description from database
                try:
                    replied_message_from_db = self.db_manager.get_message_by_message_id(
                        message.reply_to_message.message_id
                    )
                    if (
                        replied_message_from_db
                        and replied_message_from_db.image_description
                    ):
                        replied_to_photo_description = (
                            replied_message_from_db.image_description
                        )
                except Exception as e:
                    logger.debug(
                        f"Could not retrieve photo description for reply context: {e}"
                    )

            if reply_text:
                message_text = (
                    f"[Replying to {reply_author}: '{reply_text}'] {message_text}"
                )
            elif replied_to_photo_description:
                message_text = f"[Replying to {reply_author}'s photo: {replied_to_photo_description}] {message_text}"
            elif message.reply_to_message.photo:
                message_text = f"[Replying to {reply_author}'s photo] {message_text}"
            else:
                message_text = f"[Replying to {reply_author}] {message_text}"

        # Check for forwarded message information
        is_forwarded = False
        forward_from_username = None
        forward_from = None

        if message.forward_origin:
            is_forwarded = True
            if message.forward_origin.type == MessageOriginType.CHANNEL:
                forward_from = "channel"
                forward_from_username = message.forward_origin.chat.title
            elif message.forward_origin.type == MessageOriginType.USER:
                forward_from = "user"
                forward_from_username = (
                    message.forward_origin.sender_user.username
                    or " ".join(
                        filter(
                            None,
                            [
                                message.forward_origin.sender_user.first_name,
                                message.forward_origin.sender_user.last_name,
                            ],
                        )
                    )
                )
            elif message.forward_origin.type == MessageOriginType.HIDDEN_USER:
                forward_from = "hidden_user"
                forward_from_username = message.forward_origin.sender_user_name

        # Handle images
        if message.photo and Config.IMAGE_ANALYSIS_ENABLED:
            has_photo = True
            try:
                # Process image in memory and get description
                image_description = await self._process_image(message, context)
                logger.info(f"Image analyzed: {image_description}")
            except Exception as e:
                logger.error(f"Failed to process/analyze image: {e}")
        elif message.photo and not Config.IMAGE_ANALYSIS_ENABLED:
            image_description = None

        # Save message to database
        try:
            self.db_manager.save_message(
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
            logger.debug(f"Saved message {message_id} from user {username}")
        except Exception as e:
            logger.error(f"Failed to save message to database: {e}")

        # Check for bot mentions after saving the message
        await self._handle_bot_mention(message, context)

        # check if we need to generate a summary
        if message_id % 10 == 0:  # todo change triggering logic
            await self.summary_engine.ensure_chunks_processed(chat_id)

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

    async def _handle_bot_mention(self, message, context):
        """Handle bot mentions in messages."""
        if not message.text:
            return

        # Get bot username if we don't have it yet
        if not self.bot_username:
            try:
                bot_info = await context.bot.get_me()
                self.bot_username = bot_info.username
            except Exception as e:
                logger.error(f"Failed to get bot username: {e}")
                return

        # Check if the bot is mentioned
        mention_text = f"@{self.bot_username}"
        if mention_text.lower() not in message.text.lower():
            return

        logger.info(
            f"Bot mentioned by {message.from_user.username} in chat {message.chat_id}"
        )

        try:
            # Get recent context
            context_messages = self.db_manager.get_context_for_mention(
                chat_id=message.chat_id,
                limit=Config.MENTION_CONTEXT_SIZE,
                hours_back=Config.MENTION_CONTEXT_HOURS,
            )

            # Check if this is a reply to another message
            replied_to_message = None
            has_historical_context = False
            if message.reply_to_message:
                replied_to_message = self.db_manager.get_message_by_message_id(
                    message.reply_to_message.message_id
                )

                # If we found the replied-to message and it's not in recent context,
                # get additional context around that message
                if replied_to_message:
                    # Check if the replied-to message is already in recent context
                    replied_msg_in_context = any(
                        msg.message_id == replied_to_message.message_id
                        for msg in context_messages
                    )

                    if not replied_msg_in_context:
                        # Get context around the replied-to message
                        reply_context = self.db_manager.get_context_around_message(
                            chat_id=message.chat_id,
                            target_timestamp=replied_to_message.timestamp,
                            context_limit=Config.OLD_MENTION_CONTEXT_SIZE,
                        )

                        if reply_context:  # Only if we actually got historical context
                            has_historical_context = True

                            # Merge contexts, removing duplicates and sorting by timestamp
                            all_messages = context_messages + reply_context
                            seen_message_ids = set()
                            unique_messages = []
                            for msg in all_messages:
                                if msg.message_id not in seen_message_ids:
                                    unique_messages.append(msg)
                                    seen_message_ids.add(msg.message_id)

                            # Sort by timestamp to maintain chronological order
                            context_messages = sorted(
                                unique_messages, key=lambda m: m.timestamp
                            )

            # Get image description for current message if it has a photo
            current_image_description = None
            if message.photo:
                try:
                    current_image_description = await self._process_image(
                        message, context
                    )
                    logger.info(
                        f"Image analyzed for mention: {current_image_description}"
                    )
                except Exception as e:
                    logger.error(f"Failed to process/analyze image for mention: {e}")

            # Create a Message object for the current mention
            mention_message_obj = type(
                "obj",
                (object,),
                {
                    "message_id": message.message_id,
                    "user_id": message.from_user.id,
                    "username": message.from_user.username
                    or " ".join(
                        filter(
                            None,
                            [message.from_user.first_name, message.from_user.last_name],
                        )
                    ),
                    "message_text": message.text,
                    "timestamp": message.date,
                    "has_photo": bool(message.photo),
                    "image_description": current_image_description,
                    "is_forwarded": False,
                    "forward_from_username": None,
                    "forward_from": None,
                },
            )

            # Generate reply
            reply_text = await self.summary_engine.generate_mention_reply(
                messages=context_messages,
                mention_message=mention_message_obj,
                replied_to_message=replied_to_message,
                has_historical_context=has_historical_context,
            )

            # Send reply
            try:
                sent_message = await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=reply_text,
                    reply_to_message_id=message.message_id,
                    parse_mode="HTML",
                )
            except telegram.error.BadRequest:
                logger.warning(
                    "Failed to parse HTML in bot reply, sending plain text instead. %s",
                    reply_text,
                )
                sent_message = await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=strip_html_tags(reply_text),
                    reply_to_message_id=message.message_id,
                )

            # Store the bot's reply in the database
            try:
                bot_info = await context.bot.get_me()
                self.db_manager.save_message(
                    chat_id=sent_message.chat_id,
                    user_id=bot_info.id,
                    username=bot_info.username,
                    message_text=reply_text,
                    image_description=None,
                    message_id=sent_message.message_id,
                    has_photo=False,
                    is_forwarded=False,
                    forward_from_username=None,
                    forward_from=None,
                )
                logger.debug(f"Saved bot reply message {sent_message.message_id}")
            except Exception as save_error:
                logger.error(f"Failed to save bot reply to database: {save_error}")

        except Exception as e:
            logger.error(f"Failed to handle bot mention: {e}")
            # Send a simple error message
            try:
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text="Sorry, I encountered an error while processing your request.",
                    reply_to_message_id=message.message_id,
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")
