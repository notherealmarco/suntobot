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


def sanitize_html(text: str) -> str:
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
    # This prevents &lt;script&gt; from becoming <script> after tag processing
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    text = text.replace("<ul>", "").replace("</ul>", "")
    text = text.replace("<li>", "🔸 ").replace("</li>", "\n\n")

    # Define allowed tags (excluding self-closing tags like br)
    allowed_tags = {"b", "i", "u", "s", "code", "pre", "a"}

    # Pattern to match all HTML tags with optional attributes
    tag_pattern = r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>"

    # Find all tags and their positions
    tags = []
    for match in re.finditer(tag_pattern, text):
        is_closing = match.group(1) == "/"
        tag_name = match.group(2).lower()
        attributes = match.group(3).strip()
        full_match = match.group(0)

        tags.append(
            {
                "name": tag_name,
                "is_closing": is_closing,
                "attributes": attributes,
                "full_match": full_match,
                "start": match.start(),
                "end": match.end(),
                "allowed": tag_name in allowed_tags,
            }
        )

    # Build a list of valid tag pairs using a stricter approach
    valid_tags = []
    tag_stack = []

    for tag in tags:
        if not tag["allowed"]:
            continue

        if tag["is_closing"]:
            # Find matching opening tag - must be the most recent one of the same type
            # This ensures proper nesting
            if tag_stack and tag_stack[-1]["name"] == tag["name"]:
                # Found properly nested matching opening tag
                opening_tag = tag_stack.pop()

                # Validate and create clean tag pair
                if tag["name"] == "a":
                    # Special handling for anchor tags - validate href
                    href_match = re.search(
                        r'href\s*=\s*["\']([^"\']*)["\']',
                        opening_tag["attributes"],
                        re.IGNORECASE,
                    )
                    if href_match:
                        href = href_match.group(1)
                        # Validate URL
                        if href.startswith(("http://", "https://", "tg://", "mailto:")):
                            clean_opening = f'<a href="{href}">'
                            clean_closing = "</a>"
                            valid_tags.append(
                                (opening_tag, tag, clean_opening, clean_closing)
                            )
                    # If no valid href, don't add the tag pair
                else:
                    # For other tags, create clean versions
                    clean_opening = f"<{tag['name']}>"
                    clean_closing = f"</{tag['name']}>"
                    valid_tags.append((opening_tag, tag, clean_opening, clean_closing))

            else:
                # Improperly nested or orphaned closing tag
                # Clear the stack of any tags that would be improperly nested
                while tag_stack and tag_stack[-1]["name"] != tag["name"]:
                    tag_stack.pop()

                # If we found a matching tag after clearing improper nesting
                if tag_stack and tag_stack[-1]["name"] == tag["name"]:
                    tag_stack.pop()  # Remove the opening tag but don't create a valid pair

            # Orphaned closing tags are ignored
        else:
            # Opening tag - add to stack
            tag_stack.append(tag)

    # Any remaining tags in stack are unclosed - ignore them

    # Sort valid tags by position for replacement
    valid_tags.sort(key=lambda x: x[0]["start"])

    # Build the result by replacing tags from right to left to preserve positions
    result = text
    for opening_tag, closing_tag, clean_opening, clean_closing in reversed(valid_tags):
        # Replace closing tag first (rightmost)
        result = (
            result[: closing_tag["start"]]
            + clean_closing
            + result[closing_tag["end"] :]
        )
        # Then replace opening tag
        result = (
            result[: opening_tag["start"]]
            + clean_opening
            + result[opening_tag["end"] :]
        )

    # Remove any remaining invalid HTML tags that weren't in valid pairs
    # We need to be careful not to remove the tags we just added
    all_tags_to_remove = []
    for tag in tags:
        # Only remove tags that weren't part of valid pairs
        tag_was_used = False
        for opening_tag, closing_tag, _, _ in valid_tags:
            if (
                tag["start"] == opening_tag["start"]
                and tag["end"] == opening_tag["end"]
            ) or (
                tag["start"] == closing_tag["start"]
                and tag["end"] == closing_tag["end"]
            ):
                tag_was_used = True
                break

        if not tag_was_used:
            all_tags_to_remove.append((tag["start"], tag["end"]))

    # Remove invalid tags from right to left to preserve positions
    for start, end in sorted(all_tags_to_remove, reverse=True):
        result = result[:start] + result[end:]

    # Clean up multiple consecutive newlines and trim
    result = re.sub(r"\n{3,}", "\n\n", result).strip()

    return result


class SummaryEngine:
    def __init__(self, db_manager):
        self.client = openai.AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY, base_url=Config.OPENAI_BASE_URL
        )
        self.chunk_cache_manager = ChunkCacheManager(db_manager)

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count based on character count."""
        return len(text) // Config.CHARS_PER_TOKEN

    async def _summarize_chunk(
        self, messages: List[Message], chunk_index: int, total_chunks: int
    ) -> str:
        """
        Summarize a single chunk of messages.

        Args:
            messages: Messages to summarize
            chunk_index: Index of current chunk (0-based)
            total_chunks: Total number of chunks

        Returns:
            Summary of the chunk
        """
        if not messages:
            return ""

        # Create a focused system prompt for chunk summarization
        chunk_prompt = Config.CHUNK_SYSTEM_PROMPT.format(
            chunk_index=chunk_index + 1, total_chunks=total_chunks
        )

        formatted_messages = self._format_messages_for_chunk(
            messages, chunk_index, total_chunks
        )

        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "user", "content": formatted_messages},
                    {"role": "system", "content": chunk_prompt},
                ],
            )

            return (
                response.choices[0]
                .message.content.replace("</start_of_turn>", "")
                .replace("</end_of_turn>", "")
                .strip()
            )

        except Exception as e:
            logger.error(f"Failed to summarize chunk {chunk_index}: {e}")
            return f"[Error summarizing chunk {chunk_index + 1}]"

    def _format_messages_for_chunk(
        self, messages: List[Message], chunk_index: int, total_chunks: int
    ) -> str:
        """Format messages for chunk summarization."""
        if not messages:
            return ""

        start_time = format_timestamp_for_display(messages[0].timestamp)
        end_time = format_timestamp_for_display(messages[-1].timestamp)

        formatted_lines = [
            f"Time Range: {start_time} to {end_time}",
            "",
            "Messages:",
        ]

        for message in messages:
            username = message.username or f"user_{message.user_id}"
            timestamp = format_timestamp_for_display(message.timestamp)

            content_line = ""
            if message.message_text:
                content_line = message.message_text
            elif message.image_description:
                content_line = f"[sent an image: {message.image_description}]"
            elif message.has_photo:
                content_line = "[sent an image]"

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

    async def _create_meta_summary(
        self,
        chunk_summaries: List[str],
        requesting_username: str,
        time_range_desc: str,
        total_messages: int,
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

        meta_prompt = Config.SYSTEM_PROMPT.replace(
            "{username}", requesting_username
        ).replace(
            "{time_range}", time_range_desc
        ) + Config.META_SUMMARY_PROMPT_SUFFIX.format(
            num_chunks=len(valid_summaries), username=requesting_username
        )

        chunks_text = "\n\n".join(
            [f"Part {i + 1}: {summary}" for i, summary in enumerate(valid_summaries)]
        )

        formatted_input = f"""Summary Request for @{requesting_username}
Time Period: {time_range_desc}
Total Messages Processed: {total_messages}
Number of Summary Parts: {len(valid_summaries)}

Partial Summaries to Combine:
{chunks_text}

Please create a final comprehensive summary that combines all parts."""

        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": meta_prompt},
                    {"role": "user", "content": formatted_input},
                ],
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Failed to create meta-summary: {e}")
            # Fallback: return combined summaries with basic formatting
            return f"Summary for {time_range_desc}:\n\n" + "\n\n".join(
                [f"• {s}" for s in valid_summaries]
            )

    async def generate_smart_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """
        Generate summary using Smart Hybrid approach based on message volume.
        Uses cache-aware processing for improved performance.

        Args:
            messages: List of messages to summarize
            requesting_username: User requesting the summary
            time_range_desc: Description of the time range

        Returns:
            Generated summary
        """
        if not messages:
            return (
                f"No messages found in the specified time period ({time_range_desc})."
            )

        message_count = len(messages)
        logger.info(f"Generating smart summary for {message_count} messages")

        # Small volume: Process everything live (simple approach) - no caching benefit
        if message_count <= Config.SMALL_SUMMARY_THRESHOLD:
            logger.info(f"Using simple processing for {message_count} messages")
            return await self._generate_simple_summary(
                messages, requesting_username, time_range_desc
            )

        # Medium/Large volume: Use cache-aware chunking
        else:
            logger.info(f"Using cache-aware processing for {message_count} messages")
            return await self._generate_cache_aware_summary(
                messages, requesting_username, time_range_desc
            )

    async def _generate_cache_aware_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """
        Generate summary using cache-aware chunking for maximum efficiency.

        This method:
        1. Looks for overlapping cached chunks in the database
        2. Uses cached summaries where possible
        3. Only processes uncovered message ranges
        4. Combines cached and live summaries
        """
        # Sort messages by message_id to ensure deterministic processing
        sorted_messages = sorted(messages, key=lambda m: m.message_id)

        if not sorted_messages:
            return (
                f"No messages found in the specified time period ({time_range_desc})."
            )

        chat_id = sorted_messages[0].chat_id
        start_message_id = sorted_messages[0].message_id
        end_message_id = sorted_messages[-1].message_id

        logger.info(
            f"Looking for cached chunks covering range {start_message_id}-{end_message_id}"
        )

        # Get all cached chunks that overlap with our message range
        overlapping_chunks = self.chunk_cache_manager.get_cached_chunks_for_range(
            chat_id, start_message_id, end_message_id
        )

        if not overlapping_chunks:
            logger.info(
                "No overlapping cached chunks found, processing everything live"
            )
            # No cache hits, process everything using deterministic chunking
            return await self._generate_deterministic_chunked_summary(
                sorted_messages, requesting_username, time_range_desc
            )

        # We have some cached chunks, let's be smart about using them
        logger.info(f"Found {len(overlapping_chunks)} overlapping cached chunks")

        # Strategy: Use cached chunks and only process gaps
        all_summaries = []

        # Sort cached chunks by start_message_id
        overlapping_chunks.sort(key=lambda x: x["start_message_id"])

        # Use the cached summaries
        for cached_chunk in overlapping_chunks:
            all_summaries.append(cached_chunk["summary_text"])
            logger.info(
                f"Using cached chunk {cached_chunk['chunk_id']} "
                f"({cached_chunk['start_message_id']}-{cached_chunk['end_message_id']})"
            )

        # Check if cached chunks fully cover our request range
        covered_start = min(chunk["start_message_id"] for chunk in overlapping_chunks)
        covered_end = max(chunk["end_message_id"] for chunk in overlapping_chunks)

        # Check if we have full coverage
        request_fully_covered = (
            covered_start <= start_message_id and covered_end >= end_message_id
        )

        if request_fully_covered:
            logger.info(
                f"Request range {start_message_id}-{end_message_id} is fully covered by cached chunks "
                f"({covered_start}-{covered_end}). Using cached summaries only."
            )
        else:
            # Process messages before the first cached chunk
            if start_message_id < covered_start:
                logger.info(
                    f"Processing uncovered range before cache: {start_message_id}-{covered_start - 1}"
                )
                uncovered_messages = [
                    m
                    for m in sorted_messages
                    if start_message_id <= m.message_id < covered_start
                ]
                if uncovered_messages:
                    # For large uncovered ranges, use proper chunking with caching
                    if len(uncovered_messages) >= Config.SUMMARY_CHUNK_SIZE:
                        logger.info(
                            f"Large uncovered range ({len(uncovered_messages)} messages) - using deterministic chunking with caching"
                        )
                        # Calculate boundaries for the uncovered range
                        uncovered_boundaries = (
                            self.chunk_cache_manager.calculate_chunk_boundaries(
                                uncovered_messages,
                                Config.SUMMARY_CHUNK_SIZE,
                                Config.SUMMARY_CHUNK_OVERLAP,
                            )
                        )
                        # Process with caching enabled
                        uncovered_summaries = (
                            await self._process_chunks_with_boundaries(
                                uncovered_messages,
                                uncovered_boundaries,
                                chat_id,
                                should_cache=True,
                            )
                        )
                        # Insert at beginning (in correct order)
                        for summary in reversed(uncovered_summaries):
                            all_summaries.insert(0, summary)
                    else:
                        # Small uncovered range - process as before
                        logger.info(
                            f"Small uncovered range ({len(uncovered_messages)} messages) - processing without caching"
                        )
                        uncovered_summary = await self._process_uncovered_range(
                            uncovered_messages, len(all_summaries), requesting_username
                        )
                        all_summaries.insert(
                            0, uncovered_summary
                        )  # Insert at beginning

            # Process messages after the last cached chunk
            if end_message_id > covered_end:
                logger.info(
                    f"Processing uncovered range after cache: {covered_end + 1}-{end_message_id}"
                )
                uncovered_messages = [
                    m for m in sorted_messages if m.message_id > covered_end
                ]
                if uncovered_messages:
                    # For large uncovered ranges, use proper chunking with caching
                    if len(uncovered_messages) >= Config.SUMMARY_CHUNK_SIZE:
                        logger.info(
                            f"Large uncovered range ({len(uncovered_messages)} messages) - using deterministic chunking with caching"
                        )
                        # Calculate boundaries for the uncovered range
                        uncovered_boundaries = (
                            self.chunk_cache_manager.calculate_chunk_boundaries(
                                uncovered_messages,
                                Config.SUMMARY_CHUNK_SIZE,
                                Config.SUMMARY_CHUNK_OVERLAP,
                            )
                        )
                        # Process with caching enabled
                        uncovered_summaries = (
                            await self._process_chunks_with_boundaries(
                                uncovered_messages,
                                uncovered_boundaries,
                                chat_id,
                                should_cache=True,
                            )
                        )
                        all_summaries.extend(uncovered_summaries)
                    else:
                        # Small uncovered range - process as before
                        logger.info(
                            f"Small uncovered range ({len(uncovered_messages)} messages) - processing without caching"
                        )
                        uncovered_summary = await self._process_uncovered_range(
                            uncovered_messages, len(all_summaries), requesting_username
                        )
                        all_summaries.append(uncovered_summary)

        logger.info(
            f"Cache-aware summary complete: using {len(overlapping_chunks)} cached chunks, "
            f"processed {len(all_summaries) - len(overlapping_chunks)} new chunks"
        )

        if len(all_summaries) == len(overlapping_chunks):
            logger.info("All content was served from cache - no new processing needed")

        # Check if we need progressive summarization before processing
        total_summary_chars = sum(len(summary) for summary in all_summaries)
        max_chars_for_meta_summary = (
            Config.MAX_CONTEXT_TOKENS * Config.CHARS_PER_TOKEN // 2
        )  # Use half of max tokens for conservative margin

        if total_summary_chars > max_chars_for_meta_summary:
            logger.info(
                f"Using progressive summarization: {len(all_summaries)} summaries with {total_summary_chars} chars exceed {max_chars_for_meta_summary} char limit"
            )
            return await self._apply_progressive_summarization(
                all_summaries, requesting_username, time_range_desc, len(sorted_messages)
            )
        else:
            # Create final meta-summary from all summaries
            return await self._create_meta_summary(
                all_summaries, requesting_username, time_range_desc, len(sorted_messages)
            )

    async def _process_chunks_with_boundaries(
        self,
        messages: List[Message],
        boundaries: List[ChunkBoundary],
        chat_id: int,
        should_cache: bool = False,
        cached_chunks: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Process a list of chunk boundaries and return summaries.

        Args:
            messages: List of messages to process
            boundaries: List of chunk boundaries
            chat_id: Chat ID for caching purposes
            should_cache: Whether to store summaries in cache
            cached_chunks: Pre-existing cached chunks (chunk_id -> summary)

        Returns:
            List of chunk summaries
        """
        summaries = []
        cached_chunks = cached_chunks or {}

        for i, boundary in enumerate(boundaries):
            # Skip incomplete chunks if we're being strict about caching
            if should_cache and not boundary.is_complete:
                logger.info(
                    f"Skipping incomplete chunk from {boundary.start_message_id} to {boundary.end_message_id}"
                )
                continue

            # Get messages for this boundary
            chunk_messages = self.chunk_cache_manager.get_messages_for_boundary(
                messages, boundary
            )
            if not chunk_messages:
                continue

            # Check for cached summary first
            chunk_id = self.chunk_cache_manager.generate_chunk_id(
                chat_id, boundary.start_message_id, boundary.end_message_id
            )

            if chunk_id in cached_chunks:
                logger.info(f"Using cached summary for chunk {chunk_id}")
                summaries.append(cached_chunks[chunk_id])
            else:
                # Generate new summary
                summary = await self._summarize_chunk(
                    chunk_messages, i, len(boundaries)
                )
                if summary:
                    summaries.append(summary)

                    # Store in cache if requested and chunk is complete
                    if should_cache and boundary.is_complete:
                        self.chunk_cache_manager.store_chunk_summary(
                            chat_id, boundary, summary
                        )
                        logger.info(f"Cached new chunk {i + 1}/{len(boundaries)}")

        return summaries

    async def _process_uncovered_range(
        self, messages: List[Message], chunk_index: int, requesting_username: str
    ) -> str:
        """Process a range of messages that aren't covered by cache."""
        if len(messages) <= Config.SMALL_SUMMARY_THRESHOLD:
            # Small range, process directly
            return await self._summarize_chunk(messages, chunk_index, chunk_index + 1)
        else:
            # Large range, use chunking (don't cache uncovered ranges)
            boundaries = self.chunk_cache_manager.calculate_chunk_boundaries(
                messages, Config.SUMMARY_CHUNK_SIZE, Config.SUMMARY_CHUNK_OVERLAP
            )

            chat_id = messages[0].chat_id if messages else 0
            summaries = await self._process_chunks_with_boundaries(
                messages, boundaries, chat_id, should_cache=False
            )

            # If multiple chunks, combine them
            if len(summaries) > 1:
                combined_text = "\n\n".join(
                    [f"Part {i + 1}: {summary}" for i, summary in enumerate(summaries)]
                )
                return f"Combined uncovered range summary:\n{combined_text}"
            else:
                return summaries[0] if summaries else ""

    async def _generate_deterministic_chunked_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """Generate summary using deterministic chunking when no cache is available."""
        # Calculate deterministic chunk boundaries
        boundaries = self.chunk_cache_manager.calculate_chunk_boundaries(
            messages,
            Config.SUMMARY_CHUNK_SIZE,
            Config.SUMMARY_CHUNK_OVERLAP,
        )

        logger.info(f"Processing {len(boundaries)} chunks deterministically (no cache)")

        chat_id = messages[0].chat_id if messages else 0
        all_summaries = await self._process_chunks_with_boundaries(
            messages, boundaries, chat_id, should_cache=True
        )

        return await self._create_meta_summary(
            all_summaries, requesting_username, time_range_desc, len(messages)
        )

    async def _generate_simple_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """Generate summary for small message volumes using existing approach."""
        formatted_messages = self._format_messages_for_llm(
            messages, requesting_username, time_range_desc
        )

        # Check if we're approaching token limits even for "simple" processing
        estimated_tokens = self._estimate_tokens(formatted_messages)
        if (
            estimated_tokens > Config.MAX_CONTEXT_TOKENS * 0.8
        ):  # Use 80% of limit as safety margin
            logger.warning(
                f"Simple summary approaching token limit ({estimated_tokens} tokens), falling back to cache-aware"
            )
            return await self._generate_cache_aware_summary(
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

            raw_summary = response.choices[0].message.content.strip()
            return sanitize_html(raw_summary)

        except Exception as e:
            logger.error(f"Failed to generate simple summary: {e}")
            # Fallback to cache-aware approach
            return await self._generate_cache_aware_summary(
                messages, requesting_username, time_range_desc
            )

    async def _apply_progressive_summarization(
        self,
        summaries: List[str],
        requesting_username: str,
        time_range_desc: str,
        total_messages: int,
    ) -> str:
        """
        Apply progressive summarization when dealing with very large datasets.
        Groups summaries into meta-chunks and summarizes them separately.
        """
        total_summary_chars = sum(len(summary) for summary in summaries)
        max_chars_for_meta_summary = (
            Config.MAX_CONTEXT_TOKENS * Config.CHARS_PER_TOKEN // 2
        )  # Use half of max tokens for conservative margin

        if total_summary_chars <= max_chars_for_meta_summary:
            # Not large enough to require progressive summarization
            return await self._create_meta_summary(
                summaries, requesting_username, time_range_desc, total_messages
            )

        estimated_tokens = total_summary_chars // Config.CHARS_PER_TOKEN
        logger.info(
            f"Performing progressive summarization: {len(summaries)} summaries with {total_summary_chars} chars (~{estimated_tokens} tokens) exceed {max_chars_for_meta_summary} char limit"
        )

        # Group summaries into meta-chunks based on character count
        meta_chunks = []
        current_meta_chunk = []
        current_char_count = 0
        target_chars_per_meta_chunk = (
            max_chars_for_meta_summary // 4
        )  # Aim for 4 meta-chunks initially

        for summary in summaries:
            summary_chars = len(summary)

            # If adding this summary would exceed our target, start a new meta-chunk
            if (
                current_char_count + summary_chars > target_chars_per_meta_chunk
                and current_meta_chunk
            ):
                meta_chunks.append(current_meta_chunk)
                current_meta_chunk = [summary]
                current_char_count = summary_chars
            else:
                current_meta_chunk.append(summary)
                current_char_count += summary_chars

        # Add the last meta-chunk if it has content
        if current_meta_chunk:
            meta_chunks.append(current_meta_chunk)

        # Summarize each meta-chunk
        meta_summaries = []
        for i, meta_chunk in enumerate(meta_chunks):
            meta_chunk_chars = sum(len(s) for s in meta_chunk)
            estimated_tokens = meta_chunk_chars // Config.CHARS_PER_TOKEN
            logger.info(
                f"Processing meta-chunk {i + 1}/{len(meta_chunks)} with {len(meta_chunk)} summaries ({meta_chunk_chars} chars, ~{estimated_tokens} tokens)"
            )

            combined_text = "\n\n".join(
                [f"Section {j + 1}: {summary}" for j, summary in enumerate(meta_chunk)]
            )

            try:
                response = await self.client.chat.completions.create(
                    model=Config.SUMMARY_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": Config.META_CHUNK_SYSTEM_PROMPT.format(
                                num_sections=len(meta_chunk)
                            ),
                        },
                        {"role": "user", "content": combined_text},
                    ],
                )

                meta_summary = response.choices[0].message.content.strip()
                meta_summaries.append(meta_summary)

            except Exception as e:
                logger.error(f"Failed to create meta-chunk summary {i}: {e}")
                # Fallback: just combine the summaries with basic formatting
                meta_summaries.append(" | ".join(meta_chunk))

        # Create final summary from meta-summaries
        return await self._create_meta_summary(
            meta_summaries, requesting_username, time_range_desc, total_messages
        )

    async def generate_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """
        Generate summary using Smart Hybrid approach.
        This method automatically chooses the best strategy based on message volume.
        """
        try:
            raw_summary = await self.generate_smart_summary(
                messages, requesting_username, time_range_desc
            )
            return sanitize_html(raw_summary)
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
                # max_tokens=500,
                # temperature=0.7,
            )

            raw_reply = response.choices[0].message.content.strip()
            return sanitize_html(raw_reply)

        except Exception as e:
            logger.error(f"Failed to generate mention reply: {e}")
            return (
                f"Sorry, I couldn't process your request at this time. Error: {str(e)}"
            )

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
