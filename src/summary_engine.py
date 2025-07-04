"""LLM integration for generating summaries."""

import openai
import logging
from typing import List, Optional


from config import Config
from database import Message
from time_utils import format_timestamp_for_display

logger = logging.getLogger(__name__)


class SummaryEngine:
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY, base_url=Config.OPENAI_BASE_URL
        )

    async def generate_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        if not messages:
            return (
                f"No messages found in the specified time period ({time_range_desc})."
            )

        formatted_messages = self._format_messages_for_llm(
            messages, requesting_username, time_range_desc
        )

        system_prompt = (
            f"{Config.SYSTEM_PROMPT}\n\n"
            f"The requesting user is: {requesting_username}\n"
            f"Time period: {time_range_desc}"
        )

        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted_messages},
                ],
                max_tokens=500,
                temperature=0.7,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Sorry, I couldn't generate a summary at this time. Error: {str(e)}"

    async def generate_mention_reply(
        self, messages: List[Message], mention_message: Message, 
        replied_to_message: Optional[Message] = None
    ) -> str:
        """Generate a reply to a mention in the chat."""
        if not messages:
            return "I don't have enough context to provide a helpful response."

        formatted_context = self._format_messages_for_mention_reply(
            messages, mention_message, replied_to_message
        )

        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": Config.MENTION_SYSTEM_PROMPT},
                    {"role": "user", "content": formatted_context},
                ],
                max_tokens=500,
                temperature=0.7,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Failed to generate mention reply: {e}")
            return f"Sorry, I couldn't process your request at this time. Error: {str(e)}"

    def _format_messages_for_llm(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        formatted_lines = [
            "Chat Summary Request",
            f"Requesting User: @{requesting_username}",
            f"Time Period: {time_range_desc}",
            f"Total Messages: {len(messages)}",
            "",
            "Messages:",
        ]

        for message in messages:
            username = message.username or f"user_{message.user_id}"
            timestamp = format_timestamp_for_display(message.timestamp)

            # Determine the display format based on content type
            content_line = ""
            if message.message_text:
                content_line = message.message_text
            elif message.image_description:
                content_line = f"[sent an image: {message.image_description}]"
            elif message.has_photo:
                # Image was sent but analysis is pending or disabled
                content_line = "[sent an image]"

            # Format the message with forwarding information if applicable
            if message.is_forwarded:
                if (
                    message.forward_from == "user"
                    or message.forward_from == "hidden_user"
                ):
                    original_author = message.forward_from_username
                elif message.forward_from == "channel":
                    original_author = f"channel {message.forward_from_username}"
                else:
                    original_author = "unknown author"

                formatted_lines.append(
                    f"[{timestamp}] {username} forwarded from {original_author}: {content_line}"
                )
            else:
                formatted_lines.append(f"[{timestamp}] {username}: {content_line}")

        return "\n".join(formatted_lines)

    def _format_messages_for_mention_reply(
        self, messages: List[Message], mention_message: Message,
        replied_to_message: Optional[Message] = None
    ) -> str:
        """Format messages for mention reply context."""
        formatted_lines = []
        
        # Add context about the mention request
        mention_username = mention_message.username or f"user_{mention_message.user_id}"
        
        if replied_to_message:
            # User is asking about a specific message
            replied_username = replied_to_message.username or f"user_{replied_to_message.user_id}"
            replied_timestamp = format_timestamp_for_display(replied_to_message.timestamp)
            
            # Format the replied-to message content
            replied_content = ""
            if replied_to_message.message_text:
                replied_content = replied_to_message.message_text
            elif replied_to_message.image_description:
                replied_content = f"[sent an image: {replied_to_message.image_description}]"
            elif replied_to_message.has_photo:
                replied_content = "[sent an image]"
            
            formatted_lines.extend([
                f"User @{mention_username} is asking about this message:",
                f"[{replied_timestamp}] {replied_username}: {replied_content}",
                "",
                f"@{mention_username} says: {mention_message.message_text}",
                "",
                "Recent chat context:"
            ])
        else:
            # General mention without reply
            formatted_lines.extend([
                f"User @{mention_username} mentioned the bot:",
                f"@{mention_username} says: {mention_message.message_text}",
                "",
                "Recent chat context:"
            ])
        
        # Add recent messages for context (excluding the mention message itself)
        for message in messages:
            if message.message_id == mention_message.message_id:
                continue  # Skip the mention message as it's already included above
                
            username = message.username or f"user_{message.user_id}"
            timestamp = format_timestamp_for_display(message.timestamp)

            # Format message content using existing logic
            content_line = ""
            if message.message_text:
                content_line = message.message_text
            elif message.image_description:
                content_line = f"[sent an image: {message.image_description}]"
            elif message.has_photo:
                content_line = "[sent an image]"

            # Format with forwarding information if applicable
            if message.is_forwarded:
                if (
                    message.forward_from == "user"
                    or message.forward_from == "hidden_user"
                ):
                    original_author = message.forward_from_username
                elif message.forward_from == "channel":
                    original_author = f"channel {message.forward_from_username}"
                else:
                    original_author = "unknown author"

                formatted_lines.append(
                    f"[{timestamp}] {username} forwarded from {original_author}: {content_line}"
                )
            else:
                formatted_lines.append(f"[{timestamp}] {username}: {content_line}")

        return "\n".join(formatted_lines)
