import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import DatabaseManager
from summary_engine import SummaryEngine
from time_utils import get_time_range_description, parse_time_interval

logger = logging.getLogger(__name__)


class CommandHandler:
    def __init__(self, db_manager: DatabaseManager, summary_engine: SummaryEngine):
        self.db_manager = db_manager
        self.summary_engine = summary_engine

    async def handle_summary_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message

        if message.chat_id not in Config.WHITELISTED_GROUPS:
            return

        user_id = message.from_user.id
        username = message.from_user.username or f"user_{user_id}"
        chat_id = message.chat_id

        loading_message = await message.reply_text("Generating sunto, waiting... ⏳")

        try:
            time_interval = self._parse_command_arguments(message.text)
            since_timestamp, time_range_desc = self._determine_time_range(
                time_interval, chat_id, user_id
            )

            messages = self.db_manager.get_messages_since(
                chat_id, user_id, since_timestamp
            )

            summary = await self.summary_engine.generate_summary(
                messages=messages,
                requesting_username=username,
                time_range_desc=time_range_desc,
            )

            await loading_message.edit_text(
                f"📋 *Sunto*\n\n{summary}", parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            await loading_message.edit_text("Failed to generate summary.")

    def _parse_command_arguments(self, command_text: str) -> Optional[timedelta]:
        pattern = r"/\w+\s+(\d+[mhd])"
        match = re.search(pattern, command_text)

        if match:
            interval_str = match.group(1)
            return parse_time_interval(interval_str)

        return None

    def _determine_time_range(
        self, time_interval: Optional[timedelta], chat_id: int, user_id: int
    ) -> tuple[datetime, str]:
        if time_interval:
            since_timestamp = datetime.now(timezone.utc) - time_interval
            time_range_desc = get_time_range_description(time_interval)
        else:
            last_message_time = self.db_manager.get_last_user_message_time(
                chat_id, user_id
            ).replace(tzinfo=timezone.utc)
            if last_message_time:
                time_since_last = datetime.now(timezone.utc) - last_message_time
                since_timestamp = last_message_time
                time_range_desc = f"Since your last message ({time_since_last.total_seconds() / 3600:.1f}h ago)"
            else:
                since_timestamp = datetime.now(timezone.utc) - timedelta(hours=24)
                time_range_desc = "Last 24 hours (no previous messages found)"

        return since_timestamp, time_range_desc

    async def handle_start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message

        if message.chat_id not in Config.WHITELISTED_GROUPS:
            return

        welcome_text = (
            f"🤖 *SuntoBot is active!*\n\n"
            f"I'll automatically save messages in this chat and provide summaries when requested.\n\n"
            f"Commands:\n"
            f"• `{Config.SUMMARY_COMMAND}` - Get summary since your last message\n"
            f"• `{Config.SUMMARY_COMMAND} 1h` - Get summary for last hour\n"
            f"• `{Config.SUMMARY_COMMAND} 30m` - Get summary for last 30 minutes\n"
            f"• `{Config.SUMMARY_COMMAND} 2d` - Get summary for last 2 days\n\n"
            f"Supported time formats: `m` (minutes), `h` (hours), `d` (days)"
        )

        await message.reply_text(welcome_text, parse_mode="Markdown")

    async def handle_help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.handle_start_command(update, context)
