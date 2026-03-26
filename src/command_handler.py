import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import telegram
from telegram import Update
from telegram.ext import ContextTypes
from config import Config
from database import DatabaseManager
from summary_engine import SummaryEngine, strip_html_tags, strip_thinking, sanitize_html, split_long_message
from time_utils import get_time_range_description, parse_time_interval

logger = logging.getLogger(__name__)

EDIT_INTERVAL = 3  # seconds between edits to respect Telegram rate limits


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

        loading_message = await message.reply_text(
            "👨‍🍳 Your sunto is being cooked, please wait..."
        )

        try:
            time_interval = self._parse_command_arguments(message.text)
            since_timestamp, time_range_desc = self._determine_time_range(
                time_interval, chat_id, user_id
            )

            messages = self.db_manager.get_messages_since(
                chat_id, user_id, since_timestamp
            )

            if message.chat.username:
                chat_prefix = f"{message.chat.username}"
            else:
                chat_prefix = f"c/{str(chat_id)[4:]}"

            # Stream the summary, progressively editing the loading message
            accumulated_text = ""
            stream_failed = False
            last_edit_time = 0.0
            last_successful_text = ""
            sent_messages = [loading_message]

            try:
                async for chunk in self.summary_engine.generate_summary_stream(
                    messages=messages,
                    requesting_username=username,
                    time_range_desc=time_range_desc,
                ):
                    accumulated_text += chunk
                    now = time.monotonic()
                    
                    if now - last_edit_time >= EDIT_INTERVAL:
                        message_chunks = split_long_message(accumulated_text, max_length=4000)
                        
                        # Process previous completely filled chunks
                        while len(sent_messages) < len(message_chunks):
                            target_index = len(sent_messages) - 1
                            finalized_text = message_chunks[target_index]
                            sanitized = sanitize_html(strip_thinking(finalized_text.strip()), chat_prefix)
                            
                            try:
                                if target_index == 0:
                                    await sent_messages[target_index].edit_text(
                                        f"📋 <b>Sunto</b>\n\n{sanitized}", parse_mode="HTML"
                                    )
                                else:
                                    await sent_messages[target_index].edit_text(
                                        sanitized, parse_mode="HTML"
                                    )
                            except Exception:
                                try:
                                    if target_index == 0:
                                        await sent_messages[target_index].edit_text(
                                            f"📋 Sunto\n\n{strip_html_tags(sanitized)}"
                                        )
                                    else:
                                        await sent_messages[target_index].edit_text(
                                            strip_html_tags(sanitized)
                                        )
                                except Exception as plain_err:
                                    logger.error(f"Failed to finalize chunk {target_index}: {plain_err}")
                                
                            # Send a new message for the next chunk
                            try:
                                new_msg = await message.reply_text("👨‍🍳 Cooking next part...")
                                sent_messages.append(new_msg)
                                last_successful_text = "" # Reset for the new message
                            except Exception as send_err:
                                logger.error(f"Failed to send next chunk placeholder: {send_err}")
                                break # prevent infinite loop
                            
                        # Now deal with the currently streaming chunk (the last one)
                        if len(sent_messages) == len(message_chunks):
                            active_chunk = message_chunks[-1]
                            if len(sent_messages) == 1:
                                current_text = f"📋 <b>Sunto</b>\n\n{active_chunk} ✏️ ..."
                            else:
                                current_text = f"{active_chunk} ✏️ ..."
                            
                            if current_text != last_successful_text:
                                last_edit_time = now
                                try:
                                    await sent_messages[-1].edit_text(current_text, parse_mode="HTML")
                                    last_successful_text = current_text
                                except telegram.error.BadRequest:
                                    try:
                                        # Graceful fallback to plaintext if we have unclosed tags mid-stream
                                        fallback_text = current_text.replace("<b>", "**").replace("</b>", "**")
                                        await sent_messages[-1].edit_text(fallback_text)
                                        last_successful_text = current_text
                                    except Exception as edit_err:
                                        logger.debug(f"Intermediate plain edit error: {edit_err}")
                                except Exception as edit_err:
                                    logger.debug(f"Intermediate edit error: {edit_err}")
            except Exception as stream_err:
                logger.warning(
                    f"Summary streaming failed, falling back to non-streaming: {stream_err}"
                )
                stream_failed = True

            if stream_failed or not accumulated_text:
                summary = await self.summary_engine.generate_summary(
                    messages=messages,
                    requesting_username=username,
                    time_range_desc=time_range_desc,
                    chat_prefix=chat_prefix,
                )
                final_chunks = split_long_message(summary, max_length=4000)
            else:
                final_chunks = split_long_message(accumulated_text, max_length=4000)

            # Universal robust finalize loop for all chunks
            for i, chunk_text in enumerate(final_chunks):
                if i >= len(sent_messages):
                    try:
                        new_msg = await message.reply_text("👨‍🍳 Finishing up...")
                        sent_messages.append(new_msg)
                    except Exception as e:
                        logger.error(f"Failed to append finish msg: {e}")
                        break
                        
                msg_to_edit = sent_messages[i]
                
                # If stream succeeded, we need to sanitize the text here. If failure, generate_summary did it already.
                sanitized_chunk = chunk_text
                if not stream_failed:
                    sanitized_chunk = sanitize_html(strip_thinking(chunk_text.strip()), chat_prefix)
                    
                try:
                    if i == 0:
                        await msg_to_edit.edit_text(f"📋 <b>Sunto</b>\n\n{sanitized_chunk}", parse_mode="HTML")
                    else:
                        await msg_to_edit.edit_text(sanitized_chunk, parse_mode="HTML")
                except Exception as finalize_err:
                    logger.warning(f"Failed to parse HTML in final chunk {i}, using plain text: {finalize_err}")
                    try:
                        if i == 0:
                            await msg_to_edit.edit_text(f"📋 Sunto\n\n{strip_html_tags(sanitized_chunk)}")
                        else:
                            await msg_to_edit.edit_text(strip_html_tags(sanitized_chunk))
                    except Exception as e:
                        logger.error(f"Failed fallback edit for chunk {i}: {e}")

            # Delete any leftover messages if the summary shrank
            for extra_idx in range(len(final_chunks), len(sent_messages)):
                try:
                    await sent_messages[extra_idx].delete()
                except Exception as e:
                    logger.warning(f"Failed to delete unused placeholder message: {e}")

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
            "🤖 <b>SuntoBot is active!</b>\n\n"
            "I'll automatically save messages in this chat and provide summaries when requested.\n\n"
            "Commands:\n"
            "• <code>/sunto</code> - Get summary since your last message\n"
            "• <code>/sunto 1h</code> - Get summary for last hour\n"
            "• <code>/sunto 30m</code> - Get summary for last 30 minutes\n"
            "• <code>/sunto 2d</code> - Get summary for last 2 days\n\n"
            "Supported time formats: <code>m</code> (minutes), <code>h</code> (hours), <code>d</code> (days)"
        )

        await message.reply_text(welcome_text, parse_mode="HTML")

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
                await message.reply_text(
                    f"❌ Group {group_id} not found or already denied."
                )

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

            response_lines = ["🤖 <b>Allowed Groups:</b>\n"]

            for group in allowed_groups:
                escaped_title = telegram.helpers.escape(group.chat_title)
                response_lines.append(
                    f"• <b>{escaped_title}</b>\n"
                    f"  ID: <code>{group.chat_id}</code>\n"
                    f"  Allowed: {group.allowed_at.strftime('%Y-%m-%d %H:%M')}\n"
                )

            response = "\n".join(response_lines)
            await message.reply_text(response, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to list groups: {e}")
            await message.reply_text("Failed to retrieve group list. Please try again.")
