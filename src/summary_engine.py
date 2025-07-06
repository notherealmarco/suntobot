"""LLM integration for generating summaries."""

import openai
import logging
import re
import math
from typing import List, Optional, Tuple
from datetime import timedelta

from config import Config
from database import Message
from time_utils import format_timestamp_for_display
import markdown


logger = logging.getLogger(__name__)


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
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY, base_url=Config.OPENAI_BASE_URL
        )

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count based on character count."""
        return len(text) // Config.CHARS_PER_TOKEN

    def _chunk_messages(self, messages: List[Message], chunk_size: int, overlap: int) -> List[List[Message]]:
        """
        Split messages into overlapping chunks to preserve conversation continuity.
        
        Args:
            messages: List of messages to chunk
            chunk_size: Target number of messages per chunk
            overlap: Number of messages to overlap between chunks
            
        Returns:
            List of message chunks with overlap
        """
        if len(messages) <= chunk_size:
            return [messages]
        
        chunks = []
        start = 0
        
        while start < len(messages):
            end = min(start + chunk_size, len(messages))
            chunk = messages[start:end]
            chunks.append(chunk)
            
            # If this is the last chunk, break
            if end >= len(messages):
                break
                
            # Move start position with overlap consideration
            start = end - overlap
            
        return chunks

    async def _summarize_chunk(self, messages: List[Message], chunk_index: int, total_chunks: int) -> str:
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
            chunk_index=chunk_index + 1,
            total_chunks=total_chunks
        )

        formatted_messages = self._format_messages_for_chunk(messages, chunk_index, total_chunks)
        
        try:
            response = await self.client.chat.completions.create(
                model=Config.SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": chunk_prompt},
                    {"role": "user", "content": formatted_messages},
                ],
                max_tokens=400,  # Limit chunk summaries to keep them concise
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to summarize chunk {chunk_index}: {e}")
            return f"[Error summarizing chunk {chunk_index + 1}]"

    def _format_messages_for_chunk(self, messages: List[Message], chunk_index: int, total_chunks: int) -> str:
        """Format messages for chunk summarization."""
        if not messages:
            return ""
            
        start_time = format_timestamp_for_display(messages[0].timestamp)
        end_time = format_timestamp_for_display(messages[-1].timestamp)
        
        formatted_lines = [
            f"Chat Chunk {chunk_index + 1} of {total_chunks}",
            f"Time Range: {start_time} to {end_time}",
            f"Messages in chunk: {len(messages)}",
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
                if message.forward_from == "user" or message.forward_from == "hidden_user":
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

    async def _create_meta_summary(self, chunk_summaries: List[str], requesting_username: str, time_range_desc: str, total_messages: int) -> str:
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
        valid_summaries = [s for s in chunk_summaries if s.strip() and not s.startswith("[Error")]
        
        if not valid_summaries:
            return f"Unable to generate summary for {time_range_desc} due to processing errors."
            
        meta_prompt = Config.SYSTEM_PROMPT.replace(
            "{username}", requesting_username
        ).replace("{time_range}", time_range_desc) + Config.META_SUMMARY_PROMPT_SUFFIX.format(
            num_chunks=len(valid_summaries),
            username=requesting_username
        )

        chunks_text = "\n\n".join([f"Part {i+1}: {summary}" for i, summary in enumerate(valid_summaries)])
        
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
            return f"Summary for {time_range_desc}:\n\n" + "\n\n".join([f"• {s}" for s in valid_summaries])

    async def generate_smart_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """
        Generate summary using Smart Hybrid approach based on message volume.
        
        Args:
            messages: List of messages to summarize
            requesting_username: User requesting the summary
            time_range_desc: Description of the time range
            
        Returns:
            Generated summary
        """
        if not messages:
            return f"No messages found in the specified time period ({time_range_desc})."

        message_count = len(messages)
        logger.info(f"Generating smart summary for {message_count} messages")

        # Small volume: Process everything live (simple approach)
        if message_count <= Config.SMALL_SUMMARY_THRESHOLD:
            logger.info(f"Using simple processing for {message_count} messages")
            return await self._generate_simple_summary(messages, requesting_username, time_range_desc)
        
        # Medium volume: Use chunking with overlap
        elif message_count <= Config.MEDIUM_SUMMARY_THRESHOLD:
            logger.info(f"Using chunked processing for {message_count} messages")
            return await self._generate_chunked_summary(messages, requesting_username, time_range_desc)
        
        # Large volume: Use progressive summarization
        else:
            logger.info(f"Using progressive processing for {message_count} messages")
            return await self._generate_progressive_summary(messages, requesting_username, time_range_desc)

    async def _generate_simple_summary(self, messages: List[Message], requesting_username: str, time_range_desc: str) -> str:
        """Generate summary for small message volumes using existing approach."""
        formatted_messages = self._format_messages_for_llm(messages, requesting_username, time_range_desc)
        
        # Check if we're approaching token limits even for "simple" processing
        estimated_tokens = self._estimate_tokens(formatted_messages)
        if estimated_tokens > Config.MAX_CONTEXT_TOKENS * 0.8:  # Use 80% of limit as safety margin
            logger.warning(f"Simple summary approaching token limit ({estimated_tokens} tokens), falling back to chunked")
            return await self._generate_chunked_summary(messages, requesting_username, time_range_desc)
        
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
            # Fallback to chunked approach
            return await self._generate_chunked_summary(messages, requesting_username, time_range_desc)

    async def _generate_chunked_summary(self, messages: List[Message], requesting_username: str, time_range_desc: str) -> str:
        """Generate summary using overlapping chunks for medium message volumes."""
        chunks = self._chunk_messages(messages, Config.SUMMARY_CHUNK_SIZE, Config.SUMMARY_CHUNK_OVERLAP)
        logger.info(f"Created {len(chunks)} chunks for chunked summary")
        
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            chunk_summary = await self._summarize_chunk(chunk, i, len(chunks))
            if chunk_summary:
                chunk_summaries.append(chunk_summary)
        
        return await self._create_meta_summary(chunk_summaries, requesting_username, time_range_desc, len(messages))

    async def _generate_progressive_summary(self, messages: List[Message], requesting_username: str, time_range_desc: str) -> str:
        """Generate summary using progressive approach for large message volumes."""
        # For very large volumes, use larger chunks to reduce API calls
        large_chunk_size = Config.SUMMARY_CHUNK_SIZE * 2
        chunks = self._chunk_messages(messages, large_chunk_size, Config.SUMMARY_CHUNK_OVERLAP)
        logger.info(f"Created {len(chunks)} large chunks for progressive summary")

        # First pass: Summarize each large chunk
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            chunk_summary = await self._summarize_chunk(chunk, i, len(chunks))
            if chunk_summary:
                chunk_summaries.append(chunk_summary)
        
        # If we still have too many chunk summaries, do a second pass
        if len(chunk_summaries) > 8:  # Arbitrary threshold for second-level chunking
            logger.info(f"Performing second-level summarization for {len(chunk_summaries)} chunk summaries")

            # Group chunk summaries into meta-chunks
            meta_chunks = []
            chunk_size = 4  # Group 4 summaries at a time
            for i in range(0, len(chunk_summaries), chunk_size):
                meta_chunk = chunk_summaries[i:i + chunk_size]
                meta_chunks.append(meta_chunk)

            # Summarize each meta-chunk
            meta_summaries = []
            for i, meta_chunk in enumerate(meta_chunks):
                combined_text = "\n\n".join([f"Section {j+1}: {summary}" for j, summary in enumerate(meta_chunk)])

                try:
                    response = await self.client.chat.completions.create(
                        model=Config.SUMMARY_MODEL,
                        messages=[
                            {"role": "system", "content": Config.META_CHUNK_SYSTEM_PROMPT.format(num_sections=len(meta_chunk))},
                            {"role": "user", "content": combined_text},
                        ],
                        max_tokens=500,
                    )
                    
                    meta_summary = response.choices[0].message.content.strip()
                    meta_summaries.append(meta_summary)
                    
                except Exception as e:
                    logger.error(f"Failed to create meta-chunk summary {i}: {e}")
                    # Fallback: just combine the summaries with basic formatting
                    meta_summaries.append(" | ".join(meta_chunk))
            
            # Use meta-summaries for final summary
            chunk_summaries = meta_summaries
        
        return await self._create_meta_summary(chunk_summaries, requesting_username, time_range_desc, len(messages))

    async def generate_summary(
        self, messages: List[Message], requesting_username: str, time_range_desc: str
    ) -> str:
        """
        Generate summary using Smart Hybrid approach.
        This method automatically chooses the best strategy based on message volume.
        """
        try:
            raw_summary = await self.generate_smart_summary(messages, requesting_username, time_range_desc)
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
