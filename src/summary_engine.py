"""LLM integration for generating summaries."""

import openai
import logging
from typing import List


from config import Config
from database import Message
from time_utils import format_timestamp_for_display

logger = logging.getLogger(__name__)


class SummaryEngine:
    """Handles LLM-based summary generation."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY, base_url=Config.OPENAI_BASE_URL
        )

    async def generate_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """Generate a personalized summary for the requesting user."""
        if not messages:
            return (
                f"No messages found in the specified time period ({time_range_desc})."
            )

        # Format messages for LLM
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
                model="clusterino.gemma3:27b-it-qat",
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

    def _format_messages_for_llm(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """Format messages for LLM consumption."""
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

            if message.message_text:
                formatted_lines.append(
                    f"[{timestamp}] {username}: {message.message_text}"
                )
            elif message.image_description:
                formatted_lines.append(
                    f"[{timestamp}] {username}: [sent an image: {message.image_description}]"
                )

        return "\n".join(formatted_lines)
        return "\n".join(formatted_lines)
