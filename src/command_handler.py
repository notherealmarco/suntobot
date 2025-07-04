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

        if not self.db_manager.is_group_allowed(message.chat_id):
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

        if not self.db_manager.is_group_allowed(message.chat_id):
            return

        welcome_text = (
            "🤖 *SuntoBot is active!*\n\n"
            "I'll automatically save messages in this chat and provide summaries when requested.\n\n"
            "Commands:\n"
            "• `/sunto` - Get summary since your last message\n"
            "• `/sunto 1h` - Get summary for last hour\n"
            "• `/sunto 30m` - Get summary for last 30 minutes\n"
            "• `/sunto 2d` - Get summary for last 2 days\n\n"
            "Supported time formats: `m` (minutes), `h` (hours), `d` (days)"
        )

        await message.reply_text(welcome_text, parse_mode="Markdown")

    async def handle_help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.handle_start_command(update, context)

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in Config.ADMIN_IDS

    async def handle_allow_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Allow the current group to use the bot (admin only, in group)."""
        message = update.message

        # Must be used in a group/supergroup
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply_text("This command can only be used in groups.")
            return

        # Check if user is admin
        if not self._is_admin(message.from_user.id):
            await message.reply_text("Only admins can use this command.")
            return

        try:
            chat_title = message.chat.title or f"Group {message.chat_id}"
            self.db_manager.allow_group(
                chat_id=message.chat_id,
                chat_title=chat_title,
                admin_id=message.from_user.id,
            )

            await message.reply_text(
                f"✅ Bot is now allowed in this group: {chat_title}\n"
                f"Authorized by: @{message.from_user.username or message.from_user.first_name}"
            )
            logger.info(
                f"Group {message.chat_id} ({chat_title}) allowed by admin {message.from_user.id}"
            )

        except Exception as e:
            logger.error(f"Failed to allow group: {e}")
            await message.reply_text("Failed to allow this group. Please try again.")

    async def handle_deny_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Deny a group from using the bot (admin only, private chat)."""
        message = update.message

        # Must be used in private chat
        if message.chat.type != "private":
            await message.reply_text("This command can only be used in private chat.")
            return

        # Check if user is admin
        if not self._is_admin(message.from_user.id):
            await message.reply_text("Only admins can use this command.")
            return

        # Parse group ID from command
        try:
            args = message.text.split()
            if len(args) != 2:
                await message.reply_text(
                    "Usage: /deny <group_id>\n\n"
                    "Use /list to see all allowed groups and their IDs."
                )
                return

            group_id = int(args[1])

            if self.db_manager.deny_group(group_id):
                await message.reply_text(f"✅ Bot access denied for group {group_id}")
                logger.info(f"Group {group_id} denied by admin {message.from_user.id}")
            else:
                await message.reply_text(f"❌ Group {group_id} not found or already denied.")

        except ValueError:
            await message.reply_text("Invalid group ID. Please provide a valid number.")
        except Exception as e:
            logger.error(f"Failed to deny group: {e}")
            await message.reply_text("Failed to deny group. Please try again.")

    async def handle_list_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """List all allowed groups (admin only, private chat)."""
        message = update.message

        # Must be used in private chat
        if message.chat.type != "private":
            await message.reply_text("This command can only be used in private chat.")
            return

        # Check if user is admin
        if not self._is_admin(message.from_user.id):
            await message.reply_text("Only admins can use this command.")
            return

        try:
            allowed_groups = self.db_manager.get_allowed_groups()

            if not allowed_groups:
                await message.reply_text("No groups are currently allowed.")
                return

            response_lines = ["🤖 *Allowed Groups:*\n"]

            for group in allowed_groups:
                response_lines.append(
                    f"• *{group.chat_title}*\n"
                    f"  ID: `{group.chat_id}`\n"
                    f"  Allowed: {group.allowed_at.strftime('%Y-%m-%d %H:%M')}\n"
                )

            response = "\n".join(response_lines)
            await message.reply_text(response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Failed to list groups: {e}")
            await message.reply_text("Failed to retrieve group list. Please try again.")
