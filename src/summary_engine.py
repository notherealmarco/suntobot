"""LLM integration for generating summaries."""

import openai
import logging
import re
from typing import List, Optional, Dict
from dataclasses import dataclass

from config import Config
from database import Message
from time_utils import format_timestamp_for_display
import markdown

import asyncio


logger = logging.getLogger(__name__)


@dataclass
class ChunkBoundary:
    """Represents the boundary of a message chunk."""

    start_message_id: int
    end_message_id: int
    message_count: int
    is_complete: bool  # True if chunk has full chunk_size messages


class ChunkCacheManager:
    """Manages deterministic chunking and caching of chunk summaries."""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def generate_chunk_id(self, chat_id: int, start_id: int, end_id: int) -> str:
        """Generate a deterministic chunk ID."""
        return f"{chat_id}_{start_id}_{end_id}"

    def calculate_chunk_boundaries(
        self, messages: List[Message], chunk_size: int, overlap: int
    ) -> List[ChunkBoundary]:
        """
        Calculate deterministic chunk boundaries based on message IDs.

        Args:
            messages: List of messages (must be sorted by message_id)
            chunk_size: Target number of messages per chunk
            overlap: Number of messages to overlap between chunks

        Returns:
            List of chunk boundaries
        """
        if not messages:
            return []

        if len(messages) <= chunk_size:
            return [
                ChunkBoundary(
                    start_message_id=messages[0].message_id,
                    end_message_id=messages[-1].message_id,
                    message_count=len(messages),
                    is_complete=False,  # Less than full chunk size
                )
            ]

        boundaries = []
        start_idx = 0

        while start_idx < len(messages):
            end_idx = min(start_idx + chunk_size, len(messages))
            chunk_messages = messages[start_idx:end_idx]

            boundary = ChunkBoundary(
                start_message_id=chunk_messages[0].message_id,
                end_message_id=chunk_messages[-1].message_id,
                message_count=len(chunk_messages),
                is_complete=(len(chunk_messages) == chunk_size),
            )
            boundaries.append(boundary)

            # If this is the last chunk, break
            if end_idx >= len(messages):
                break

            # Move start position with overlap consideration
            start_idx = end_idx - overlap

        return boundaries

    def get_cached_chunks_for_range(
        self, chat_id: int, start_message_id: int, end_message_id: int
    ) -> List[Dict]:
        """
        Get all cached chunks that overlap with the given message range.

        Args:
            chat_id: Chat ID
            start_message_id: Start of the message range
            end_message_id: End of the message range

        Returns:
            List of cached chunk information with overlap details
        """
        try:
            cached_chunks = self.db_manager.get_cached_chunks_for_range(
                chat_id, start_message_id, end_message_id
            )

            result = []
            for chunk in cached_chunks:
                chunk_info = {
                    "chunk_id": chunk.chunk_id,
                    "start_message_id": chunk.start_message_id,
                    "end_message_id": chunk.end_message_id,
                    "summary_text": chunk.summary_text,
                    "message_count": chunk.message_count,
                }
                result.append(chunk_info)
                logger.info(
                    f"Found overlapping cached chunk: {chunk.chunk_id} "
                    f"({chunk.start_message_id}-{chunk.end_message_id})"
                )

            return result
        except Exception as e:
            logger.error(f"Error retrieving cached chunks: {e}")
            return []

    def get_cached_chunks(
        self, chat_id: int, boundaries: List[ChunkBoundary]
    ) -> Dict[str, str]:
        """
        Get cached summaries for chunk boundaries (legacy method for exact matches).

        Args:
            chat_id: Chat ID
            boundaries: List of chunk boundaries to check

        Returns:
            Dictionary mapping chunk_id to cached summary
        """
        cached_chunks = {}

        for boundary in boundaries:
            # Only check cache for complete chunks
            if boundary.is_complete:
                chunk_id = self.generate_chunk_id(
                    chat_id, boundary.start_message_id, boundary.end_message_id
                )

                cached_summary = self.db_manager.get_chunk_summary(chunk_id)
                if cached_summary:
                    cached_chunks[chunk_id] = cached_summary
                    logger.info(f"Cache hit for exact chunk {chunk_id}")
                else:
                    logger.info(f"Cache miss for exact chunk {chunk_id}")

        return cached_chunks

    def store_chunk_summary(
        self, chat_id: int, boundary: ChunkBoundary, summary: str
    ) -> None:
        """Store a chunk summary in the cache."""
        chunk_id = self.generate_chunk_id(
            chat_id, boundary.start_message_id, boundary.end_message_id
        )

        try:
            self.db_manager.store_chunk_summary(
                chunk_id=chunk_id,
                chat_id=chat_id,
                start_message_id=boundary.start_message_id,
                end_message_id=boundary.end_message_id,
                message_count=boundary.message_count,
                summary_text=summary,
            )
            logger.info(f"Stored chunk summary for {chunk_id}")
        except Exception as e:
            logger.error(f"Failed to store chunk summary for {chunk_id}: {e}")

    def get_messages_for_boundary(
        self, messages: List[Message], boundary: ChunkBoundary
    ) -> List[Message]:
        """Extract messages that fall within a chunk boundary."""
        return [
            msg
            for msg in messages
            if boundary.start_message_id <= msg.message_id <= boundary.end_message_id
        ]


def strip_thinking(text: str) -> str:
    """
    Removes all text between <think> and </think> tags, including the tags.

    Args:
        text (str): Input text potentially containing <think>...</think> segments.

    Returns:
        str: Text with all <think>...</think> blocks removed.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def strip_html_tags(text: str) -> str:
    """
    Strip all HTML tags from the input text.

    This function uses a regular expression to remove all HTML tags,
    leaving only the raw text content.
    """
    if not text:
        return text
    # Use regex to remove all HTML tags
    return re.sub(r"<[^>]+>", "", text).strip()


def sanitize_html(text: str, chat_prefix: str = "") -> str:
    """
    Sanitize HTML to only allow properly formed Telegram-supported tags.

    Telegram supports these HTML tags:
    - <b>bold</b>
    - <i>italic</i>
    - <u>underline</u>
    - <s>strikethrough</s>
    - <code>monospace</code>
    - <pre>preformatted</pre>
    - <a href="URL">link</a>

    This function ensures:
    - Only allowed tags are kept
    - All tags are properly matched (opening/closing pairs)
    - Malformed tags are removed
    - Nested tags are handled correctly
    """
    if not text:
        return text

    # First, convert markdown to HTML
    text = markdown.markdown(text)

    # Replace <br /> and <br> with newline for better formatting
    text = (
        text.replace("<br />", "\n")
        .replace("<br>", "\n")
        .replace("<strong>", "<b>")
        .replace("</strong>", "</b>")
        .replace("<em>", "<i>")
        .replace("</em>", "</i>")
        .replace("</end_of_turn>", "")
        .replace("</start_of_turn>", "")
    )

    # Decode HTML entities FIRST to prevent creating invalid tags later
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    text = text.replace("<ul>", "").replace("</ul>", "")
    text = text.replace("<li>", "🔸 ").replace("</li>", "\n\n")

    # Define allowed tags
    allowed_tags = {"b", "i", "u", "s", "code", "pre", "a"}

    # Simple approach: strip all HTML except allowed tags with proper validation
    # Use a more straightforward regex approach

    # First pass: handle complete anchor elements specially
    def process_anchor_element(match):
        opening_tag = match.group(1)
        link_text = match.group(2)

        href_match = re.search(
            r'href\s*=\s*["\']([^"\']*)["\']', opening_tag, re.IGNORECASE
        )

        if href_match:
            href = href_match.group(1)
            if href.startswith(("http://", "https://", "tg://", "mailto:")):
                return f'<a href="{href}">{link_text}</a>'
            elif href.isdigit():
                return f'<a href="https://t.me/{chat_prefix}/{href}">{link_text}</a>'
            elif "," in href:
                # Handle comma-separated message IDs like "123, 456, 789"
                message_ids = [id_str.strip() for id_str in href.split(",")]
                valid_ids = [id_str for id_str in message_ids if id_str.isdigit()]

                if valid_ids:
                    # Create multiple links, use original text for first link, incremental numbers for others
                    links = []
                    for i, msg_id in enumerate(valid_ids):
                        if i == 0:
                            # Use original link text for the first link
                            links.append(
                                f'<a href="https://t.me/{chat_prefix}/{msg_id}">{link_text}</a>'
                            )
                        else:
                            # Use incremental numbers (2, 3, 4, etc.) for subsequent links
                            links.append(
                                f'<a href="https://t.me/{chat_prefix}/{msg_id}">{i + 1}</a>'
                            )
                    return " ".join(links)  # Changed from ", ".join() to " ".join()

        # Invalid href, return just the text content
        return link_text

    # Process complete anchor elements (opening tag + content + closing tag)
    text = re.sub(
        r"(<a\b[^>]*>)(.*?)</a>", process_anchor_element, text, flags=re.DOTALL
    )

    # Keep only allowed tags and remove all others
    # Pattern to match all remaining HTML tags (anchor elements already processed)
    def replace_tag(match):
        tag_name = match.group(2).lower() if match.group(2) else ""
        is_closing = match.group(1) == "/"

        if tag_name in allowed_tags:
            if is_closing:
                return f"</{tag_name}>"
            else:
                return f"<{tag_name}>"
        else:
            # Remove disallowed tags
            return ""

    # Apply the tag filtering - only process non-anchor tags since anchors are already handled
    text = re.sub(r"<(/?)(?!a\b)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>", replace_tag, text)

    # Clean up multiple consecutive newlines and trim
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text


class SummaryEngine:
    def __init__(self, db_manager):
        self.client = openai.AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY, base_url=Config.OPENAI_BASE_URL
        )
        self.db_manager = db_manager
        self.chunk_cache_manager = ChunkCacheManager(db_manager)

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count based on character count."""
        return len(text) // Config.CHARS_PER_TOKEN

    async def _create_meta_summary(
        self,
        chunk_summaries: List[str],
        time_range_desc: str,
    ) -> str:
        """
        Create a final meta-summary from chunk summaries.

        Args:
            chunk_summaries: List of individual chunk summaries
            requesting_username: User requesting the summary
            time_range_desc: Description of the time range
            total_messages: Total number of messages processed

        Returns:
            Final comprehensive summary
        """
        if not chunk_summaries:
            return f"No content to summarize for {time_range_desc}."

        # Filter out empty summaries
        valid_summaries = [
            s for s in chunk_summaries if s.strip() and not s.startswith("[Error")
        ]

        if not valid_summaries:
            return f"Unable to generate summary for {time_range_desc} due to processing errors."

        chunks_text = "\n\n".join(
            [f"Part {i + 1}: {summary}" for i, summary in enumerate(valid_summaries)]
        )

        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": Config.META_SUMMARY_SYSTEM_PROMPT.format(
                            num_chunks=len(valid_summaries)
                        ),
                    },
                    {
                        "role": "user",
                        "content": chunks_text
                        + "\n\n"
                        + Config.META_SUMMARY_SYSTEM_PROMPT_SUFFIX.format(
                            time_range=time_range_desc
                        ),
                    },
                ],
            )



            return strip_thinking(response.choices[0].message.content).strip()

        except Exception as e:
            logger.error(f"Failed to create meta-summary: {e}")
            # Fallback: return combined summaries with basic formatting
            return f"Summary for {time_range_desc}:\n\n" + "\n\n".join(
                [f"• {s}" for s in valid_summaries]
            )

    async def ensure_chunks_processed(self, chat_id: int) -> int:
        """
        Ensure at most SUMMARY_CHUNK_SIZE messages remain unprocessed.

        Simple logic with parallel processing:
        1. Get all unprocessed messages
        2. If >= 70 unprocessed, process multiple chunks in parallel (up to MAX_PARALLEL_CHUNKS)
        3. Repeat until < 70 unprocessed messages remain

        Returns:
            Number of new chunks processed
        """

        chunks_processed = 0

        while True:
            unprocessed_messages = await self._get_unprocessed_messages(chat_id)

            if len(unprocessed_messages) < Config.SUMMARY_CHUNK_SIZE:
                break

            # Determine how many chunks we can process in parallel
            num_possible_chunks = len(unprocessed_messages) // Config.SUMMARY_CHUNK_SIZE
            num_chunks_to_process = min(num_possible_chunks, Config.MAX_PARALLEL_CHUNKS)

            # Create tasks for parallel processing
            tasks = []
            for i in range(num_chunks_to_process):
                start_idx = i * Config.SUMMARY_CHUNK_SIZE
                end_idx = start_idx + Config.SUMMARY_CHUNK_SIZE
                chunk_to_process = unprocessed_messages[start_idx:end_idx]

                task = self._process_and_cache_chunk(
                    chat_id, chunk_to_process, chunks_processed + i
                )
                tasks.append(task)

            logger.info(
                f"Processing {num_chunks_to_process} chunks in parallel for chat {chat_id}"
            )

            # Execute all chunks in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successful chunks
            successful_chunks = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to process chunk {i}: {result}")
                else:
                    successful_chunks += 1

            chunks_processed += successful_chunks
            logger.info(
                f"Successfully processed {successful_chunks}/{num_chunks_to_process} chunks"
            )

        if chunks_processed > 0:
            logger.info(f"Processed {chunks_processed} new chunks for chat {chat_id}")

        return chunks_processed

    async def _get_unprocessed_messages(self, chat_id: int) -> List[Message]:
        """
        Get all messages that are not covered by any cached chunk.
        Returns them sorted by message_id (oldest first).
        """
        # Get all messages for this chat
        all_messages = self.db_manager.get_recent_messages(chat_id, limit=50000)
        if not all_messages:
            return []

        # Get all cached chunks for this chat
        cached_chunks = self.db_manager.get_cached_chunks_for_chat(chat_id)
        if not cached_chunks:
            # No cached chunks, all messages are unprocessed
            return sorted(all_messages, key=lambda m: m.message_id)

        # Find messages not covered by any cached chunk
        unprocessed = []
        for message in all_messages:
            is_covered = False
            for chunk in cached_chunks:
                if chunk.start_message_id <= message.message_id <= chunk.end_message_id:
                    is_covered = True
                    break
            if not is_covered:
                unprocessed.append(message)

        return sorted(unprocessed, key=lambda m: m.message_id)

    async def _get_unprocessed_messages_in_range(
        self, chat_id: int, start_message_id: int, end_message_id: int
    ) -> List[Message]:
        """
        Get unprocessed messages within a specific message ID range.
        """
        unprocessed_messages = await self._get_unprocessed_messages(chat_id)

        # Filter to only messages in the requested range
        return [
            msg
            for msg in unprocessed_messages
            if start_message_id <= msg.message_id <= end_message_id
        ]

    async def _create_final_summary(
        self,
        combined_content: str,
        requesting_username: str,
        time_range_desc: str,
        message_count: int,
    ) -> str:
        """
        Create a final summary from combined cached summaries and raw content.
        """
        try:
            # Use the proper Config system prompt for final summaries
            system_prompt = Config.SYSTEM_PROMPT.replace(
                "{username}", requesting_username
            ).replace("{time_range}", time_range_desc)

            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"{Config.SYSTEM_PROMPT_CHUNK_PREAMBLE + '\n\n'}Partial summaries for period {time_range_desc}:\n{combined_content}\n\n{Config.SYSTEM_PROMPT_SUFFIX}",
                    },
                ],
            )

            return strip_thinking(response.choices[0].message.content).strip()

        except Exception as e:
            logger.error(f"Failed to create final summary: {e}")
            return f"Summary for {time_range_desc} ({message_count} messages):\n\n{combined_content}"

    async def generate_smart_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """
        Generate summary using the simple, efficient approach:
        1. Ensure chunks are processed (at most 70 unprocessed messages)
        2. Use cached summaries for processed messages + raw text for unprocessed tail
        """
        if not messages:
            return (
                f"No messages found in the specified time period ({time_range_desc})."
            )

        chat_id = messages[0].chat_id
        logger.info(
            f"Generating smart summary for {len(messages)} messages in chat {chat_id}"
        )

        # Ensure chunks are processed first
        await self.ensure_chunks_processed(chat_id)

        # Get the message range we need to summarize
        start_message_id = messages[0].message_id
        end_message_id = messages[-1].message_id

        # Get cached summaries that cover part of this range
        cached_summaries = []
        cached_chunks = self.db_manager.get_cached_chunks_for_range(
            chat_id, start_message_id, end_message_id
        )
        for chunk in cached_chunks:
            cached_summaries.append(chunk.summary_text)

        # Get unprocessed messages in this range
        unprocessed_messages = await self._get_unprocessed_messages_in_range(
            chat_id, start_message_id, end_message_id
        )

        # Build the final content
        content_parts = []

        if len(cached_summaries) > 10:
            while len(cached_summaries) > 0:
                # Take the first 10 cached summaries
                part_summaries = cached_summaries[: min(10, len(cached_summaries))]
                cached_summaries = cached_summaries[min(10, len(cached_summaries)) :]

                meta_summary = await self._create_meta_summary(
                    part_summaries,
                    time_range_desc,
                )
                content_parts.append(meta_summary)

        if cached_summaries:
            content_parts.extend(cached_summaries)
            logger.info(f"Using {len(cached_summaries)} cached summaries")

        if unprocessed_messages:
            # Add raw unprocessed messages
            raw_content = self._format_messages_for_llm(
                unprocessed_messages, requesting_username, time_range_desc
            )
            content_parts.append(f"Recent messages:\n{raw_content}")
            logger.info(f"Including {len(unprocessed_messages)} unprocessed messages")

        if not content_parts:
            return (
                f"No content found for the specified time period ({time_range_desc})."
            )

        # Generate final summary
        if len(content_parts) == 1 and not cached_summaries:
            # Only unprocessed messages - use simple approach
            return await self._generate_simple_summary(
                messages, requesting_username, time_range_desc
            )
        else:
            # Combine cached + unprocessed content
            combined_content = "\n\n".join(content_parts)
            return await self._create_final_summary(
                combined_content, requesting_username, time_range_desc, len(messages)
            )

    async def generate_summary(
        self,
        messages: List[Message],
        requesting_username: str,
        time_range_desc: str,
        chat_prefix: str = "",
    ) -> str:
        """
        Main entry point for generating summaries.
        Uses the simple, efficient approach.
        """
        try:
            raw_summary = await self.generate_smart_summary(
                messages, requesting_username, time_range_desc
            )
            return sanitize_html(raw_summary, chat_prefix)
        except Exception as e:
            logger.error(f"Failed to generate smart summary: {e}")
            return f"Sorry, I couldn't generate a summary at this time. Error: {str(e)}"

    async def generate_mention_reply(
        self,
        messages: List[Message],
        mention_message: Message,
        replied_to_message: Optional[Message] = None,
        has_historical_context: bool = False,
    ) -> str:
        """Generate a reply to a mention in the chat."""
        if not messages:
            return "I don't have enough context to provide a helpful response."

        formatted_context = self._format_messages_for_mention_reply(
            messages, mention_message, replied_to_message, has_historical_context
        )

        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": Config.MENTION_SYSTEM_PROMPT},
                    {"role": "user", "content": formatted_context},
                ],
            )

            raw_reply = strip_thinking(response.choices[0].message.content.strip())
            return sanitize_html(raw_reply)

        except Exception as e:
            logger.error(f"Failed to generate mention reply: {e}")
            return (
                f"Sorry, I couldn't process your request at this time. Error: {str(e)}"
            )

    def _format_messages_for_llm(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        formatted_lines = []

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
                    original_author = "hidden author"

                formatted_lines.append(
                    f"{message.message_id} [{timestamp}] {username} forwarded from {original_author}: {content_line}"
                )
            else:
                formatted_lines.append(
                    f"{message.message_id} [{timestamp}] {username}: {content_line}"
                )

        formatted_lines.append(f"\nRequesting User: @{requesting_username}")
        if time_range_desc != "":
            formatted_lines.append(f"Time Period: {time_range_desc}")

        return (
            "\n".join(formatted_lines)
            .replace("</end_of_turn>", "")
            .replace("</start_of_turn>", "")
            .replace("\n\n", "\n")
        )

    def _format_messages_for_mention_reply(
        self,
        messages: List[Message],
        mention_message: Message,
        replied_to_message: Optional[Message] = None,
        has_historical_context: bool = False,
    ) -> str:
        """Format messages for mention reply context."""
        formatted_lines = []

        # Add context about the mention request
        mention_username = mention_message.username or f"user_{mention_message.user_id}"

        if replied_to_message:
            # User is asking about a specific message
            replied_username = (
                replied_to_message.username or f"user_{replied_to_message.user_id}"
            )
            replied_timestamp = format_timestamp_for_display(
                replied_to_message.timestamp
            )

            # Format the replied-to message content
            replied_content = ""
            if replied_to_message.message_text:
                replied_content = replied_to_message.message_text
            elif replied_to_message.image_description:
                replied_content = (
                    f"[sent an image: {replied_to_message.image_description}]"
                )
            elif replied_to_message.has_photo:
                replied_content = "[sent an image]"

            formatted_lines.extend(
                [
                    f"User @{mention_username} is asking about this message:",
                    f"[{replied_timestamp}] {replied_username}: {replied_content}",
                    "",
                    f"@{mention_username} says: {mention_message.message_text}",
                    "",
                    "Recent chat context:"
                    if not has_historical_context
                    else "Chat context (includes historical context around the replied message and recent messages):",
                ]
            )
        else:
            # General mention without reply
            formatted_lines.extend(
                [
                    f"User @{mention_username} mentioned the bot:",
                    f"@{mention_username} says: {mention_message.message_text}",
                    "",
                    "Recent chat context:",
                ]
            )

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
                content_line = (
                    f"[sent an image: {message.image_description.replace('\n', ' ')}]"
                )
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

    async def pre_warm_cache(self, chat_id: int) -> int:
        """
        Pre-warm the cache by processing chunks when needed.
        This should be called after new messages are added to a chat.

        Returns:
            Number of chunks processed
        """
        logger.info(f"Pre-warming cache for chat {chat_id}")
        return await self.ensure_chunks_processed(chat_id)

    async def _generate_chunk_summary(self, messages: List[Message]) -> str:
        """
        Generate a summary for a chunk of messages.
        Simple method that formats messages and sends to LLM for summarization.
        """
        if not messages:
            return ""

        logger.info(f"Generating summary for chunk of {len(messages)} messages")

        # Format messages for LLM
        formatted_content = self._format_messages_for_llm(messages, "system", "")

        while True:
            try:
                # Generate summary using OpenAI with proper Config prompt
                response = await self.client.chat.completions.create(
                    model=Config.SUMMARY_MODEL,
                    reasoning_effort= None,
                    messages=[
                        {
                            "role": "system",
                            "content": Config.CHUNK_SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": formatted_content
                            + "\n\n"
                            + Config.CHUNK_SYSTEM_PROMPT_SUFFIX,
                        },
                    ],
                )

                summary = strip_thinking((
                    response.choices[0]
                    .message.content.strip()
                    .replace("</end_of_turn>", "")
                    .replace("</start_of_turn>", "")
                ))
                logger.info("Successfully generated chunk summary")
                return summary

            except Exception as e:
                logger.error(f"Failed to generate chunk summary: {e}, retrying")
                await asyncio.sleep(5)

    async def _generate_simple_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """Generate summary for small message volumes using simple approach."""
        formatted_messages = self._format_messages_for_llm(
            messages, requesting_username, time_range_desc
        )

        system_prompt = Config.SYSTEM_PROMPT.replace(
            "{username}", requesting_username
        ).replace("{time_range}", time_range_desc)

        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted_messages},
                ],
            )

            raw_summary = strip_thinking(response.choices[0].message.content.strip())
            return raw_summary

        except Exception as e:
            logger.error(f"Failed to generate simple summary: {e}")
            return f"Failed to generate summary: {str(e)}"

    async def _process_and_cache_chunk(
        self, chat_id: int, chunk_messages: List[Message], chunk_index: int
    ) -> str:
        """
        Process a single chunk of messages and cache the result.

        Args:
            chat_id: Chat ID
            chunk_messages: Messages to process
            chunk_index: Index of this chunk (for logging)

        Returns:
            The generated summary
        """
        if not chunk_messages:
            return ""

        logger.info(
            f"Processing chunk {chunk_index + 1} of {len(chunk_messages)} messages ({chunk_messages[0].message_id}-{chunk_messages[-1].message_id}) for chat {chat_id}"
        )

        # Generate summary
        summary = await self._generate_chunk_summary(chunk_messages)

        # Cache the summary
        chunk_id = (
            f"{chat_id}_{chunk_messages[0].message_id}_{chunk_messages[-1].message_id}"
        )
        self.db_manager.store_chunk_summary(
            chunk_id=chunk_id,
            chat_id=chat_id,
            start_message_id=chunk_messages[0].message_id,
            end_message_id=chunk_messages[-1].message_id,
            message_count=len(chunk_messages),
            summary_text=summary,
        )

        logger.info(f"Cached chunk {chunk_index + 1}: {chunk_id}")
        return summary

    async def startup_initialization(self) -> None:
        """
        Initialize chunk processing for all existing chats at startup.
        This ensures that any backlog of unprocessed messages gets handled.
        """
        logger.info("Starting chunk processing initialization for all chats...")

        try:
            # Get all chat IDs that have messages
            chat_ids = self.db_manager.get_all_chat_ids()

            if not chat_ids:
                logger.info("No chats found for initialization")
                return

            logger.info(f"Found {len(chat_ids)} chats to initialize")

            # Process chunks for each chat
            total_chunks_processed = 0
            successful_chats = 0

            for chat_id in chat_ids:
                try:
                    chunks_processed = await self.ensure_chunks_processed(chat_id)
                    total_chunks_processed += chunks_processed
                    successful_chats += 1

                    if chunks_processed > 0:
                        logger.info(
                            f"Chat {chat_id}: processed {chunks_processed} chunks"
                        )
                    else:
                        logger.debug(f"Chat {chat_id}: no chunks needed processing")

                except Exception as e:
                    logger.error(f"Failed to initialize chat {chat_id}: {e}")
                    continue

            logger.info(
                f"Initialization complete: processed {total_chunks_processed} chunks across {successful_chats}/{len(chat_ids)} chats"
            )

        except Exception as e:
            logger.error(f"Failed during startup initialization: {e}")
