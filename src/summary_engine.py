"""LLM integration for generating summaries."""

import openai
import logging
import re
from typing import List, Optional


from config import Config
from database import Message
from time_utils import format_timestamp_for_display

logger = logging.getLogger(__name__)


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
        
    # Replace <br /> and <br> with newline for better formatting
    text = text.replace('<br />', '\n').replace('<br>', '\n')

    # Decode HTML entities FIRST to prevent creating invalid tags later
    # This prevents &lt;script&gt; from becoming <script> after tag processing
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    
    # Define allowed tags (excluding self-closing tags like br)
    allowed_tags = {'b', 'i', 'u', 's', 'code', 'pre', 'a'}
    
    # Pattern to match all HTML tags with optional attributes
    tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>'
    
    # Find all tags and their positions
    tags = []
    for match in re.finditer(tag_pattern, text):
        is_closing = match.group(1) == '/'
        tag_name = match.group(2).lower()
        attributes = match.group(3).strip()
        full_match = match.group(0)
        
        tags.append({
            'name': tag_name,
            'is_closing': is_closing,
            'attributes': attributes,
            'full_match': full_match,
            'start': match.start(),
            'end': match.end(),
            'allowed': tag_name in allowed_tags
        })
    
    # Build a list of valid tag pairs using a stricter approach
    valid_tags = []
    tag_stack = []
    
    for tag in tags:
        if not tag['allowed']:
            continue
            
        if tag['is_closing']:
            # Find matching opening tag - must be the most recent one of the same type
            # This ensures proper nesting
            found_match = False
            if tag_stack and tag_stack[-1]['name'] == tag['name']:
                # Found properly nested matching opening tag
                opening_tag = tag_stack.pop()
                
                # Validate and create clean tag pair
                if tag['name'] == 'a':
                    # Special handling for anchor tags - validate href
                    href_match = re.search(r'href\s*=\s*["\']([^"\']*)["\']', opening_tag['attributes'], re.IGNORECASE)
                    if href_match:
                        href = href_match.group(1)
                        # Validate URL
                        if href.startswith(('http://', 'https://', 'tg://', 'mailto:')):
                            clean_opening = f'<a href="{href}">'
                            clean_closing = '</a>'
                            valid_tags.append((opening_tag, tag, clean_opening, clean_closing))
                    # If no valid href, don't add the tag pair
                else:
                    # For other tags, create clean versions
                    clean_opening = f'<{tag["name"]}>'
                    clean_closing = f'</{tag["name"]}>'
                    valid_tags.append((opening_tag, tag, clean_opening, clean_closing))
                
                found_match = True
            else:
                # Improperly nested or orphaned closing tag
                # Clear the stack of any tags that would be improperly nested
                while tag_stack and tag_stack[-1]['name'] != tag['name']:
                    tag_stack.pop()
                
                # If we found a matching tag after clearing improper nesting
                if tag_stack and tag_stack[-1]['name'] == tag['name']:
                    tag_stack.pop()  # Remove the opening tag but don't create a valid pair
            
            # Orphaned closing tags are ignored
        else:
            # Opening tag - add to stack
            tag_stack.append(tag)
    
    # Any remaining tags in stack are unclosed - ignore them
    
    # Sort valid tags by position for replacement
    valid_tags.sort(key=lambda x: x[0]['start'])
    
    # Build the result by replacing tags from right to left to preserve positions
    result = text
    for opening_tag, closing_tag, clean_opening, clean_closing in reversed(valid_tags):
        # Replace closing tag first (rightmost)
        result = result[:closing_tag['start']] + clean_closing + result[closing_tag['end']:]
        # Then replace opening tag
        result = result[:opening_tag['start']] + clean_opening + result[opening_tag['end']:]
    
    # Remove any remaining invalid HTML tags that weren't in valid pairs
    # We need to be careful not to remove the tags we just added
    all_tags_to_remove = []
    for tag in tags:
        # Only remove tags that weren't part of valid pairs
        tag_was_used = False
        for opening_tag, closing_tag, _, _ in valid_tags:
            if (tag['start'] == opening_tag['start'] and tag['end'] == opening_tag['end']) or \
               (tag['start'] == closing_tag['start'] and tag['end'] == closing_tag['end']):
                tag_was_used = True
                break
        
        if not tag_was_used:
            all_tags_to_remove.append((tag['start'], tag['end']))
    
    # Remove invalid tags from right to left to preserve positions
    for start, end in sorted(all_tags_to_remove, reverse=True):
        result = result[:start] + result[end:]
    
    # Clean up multiple consecutive newlines and trim
    result = re.sub(r'\n{3,}', '\n\n', result).strip()
    
    return result


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

            raw_summary = response.choices[0].message.content.strip()
            return sanitize_html(raw_summary)

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Sorry, I couldn't generate a summary at this time. Error: {str(e)}"

    async def generate_mention_reply(
        self, messages: List[Message], mention_message: Message, 
        replied_to_message: Optional[Message] = None,
        has_historical_context: bool = False
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
                max_tokens=500,
                temperature=0.7,
            )

            raw_reply = response.choices[0].message.content.strip()
            return sanitize_html(raw_reply)

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
        replied_to_message: Optional[Message] = None,
        has_historical_context: bool = False
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
                "Recent chat context:" if not has_historical_context else "Chat context (includes historical context around the replied message and recent messages):"
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
