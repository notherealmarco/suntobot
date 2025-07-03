"""Command handlers for the Telegram bot."""

import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
import logging

from config import Config
from database import DatabaseManager
from summary_engine import SummaryEngine
from time_utils import parse_time_interval, get_time_range_description

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles bot commands."""

    def __init__(self, db_manager: DatabaseManager, summary_engine: SummaryEngine):
        self.db_manager = db_manager
        self.summary_engine = summary_engine

    async def handle_summary_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle summary command (e.g., /sunto)."""
        message = update.message

        # Only respond in whitelisted groups
        if message.chat_id not in Config.WHITELISTED_GROUPS:
            return

        user_id = message.from_user.id
        username = message.from_user.username or f"user_{user_id}"
        chat_id = message.chat_id

        # Parse command arguments
        command_text = message.text
        time_interval = self._parse_command_arguments(command_text)

        try:
            # Determine time range
            if time_interval:
                # Use specified time interval
                since_timestamp = datetime.now() - time_interval
                time_range_desc = get_time_range_description(time_interval)
            else:
                # Default: messages since user's last message
                last_message_time = self.db_manager.get_last_user_message_time(
                    chat_id, user_id
                )
                if last_message_time:
                    # Calculate time since last message
                    time_since_last = datetime.now() - last_message_time
                    since_timestamp = last_message_time
                    time_range_desc = f"Since your last message ({time_since_last.total_seconds() / 3600:.1f}h ago)"
                else:
                    # If no previous message, use last 24 hours
                    since_timestamp = datetime.now() - timedelta(hours=24)
                    time_range_desc = "Last 24 hours (no previous messages found)"

            # Get messages from database
            messages = self.db_manager.get_messages_since(
                chat_id, user_id, since_timestamp
            )

            # Generate summary
            summary = await self.summary_engine.generate_summary(
                messages=messages,
                requesting_username=username,
                time_range_desc=time_range_desc,
            )

            # Send summary as reply
            await message.reply_text(
                f"📋 *Sunto*\n\n{summary}", parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            await message.reply_text(
                "Sorry, I couldn't generate a summary at this time. Please try again later."
            )

    def _parse_command_arguments(self, command_text: str) -> timedelta:
        """Parse time interval from command arguments."""
        # Extract time interval from command (e.g., "/sunto 2h", "/sunto 30m")
        pattern = r"/\w+\s+(\d+[mhd])"
        match = re.search(pattern, command_text)

        if match:
            interval_str = match.group(1)
            return parse_time_interval(interval_str)

        return None

    async def handle_start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle /start command."""
        message = update.message

        # Only respond in whitelisted groups
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
    ):
        """Handle /help command."""
        await self.handle_start_command(update, context)
