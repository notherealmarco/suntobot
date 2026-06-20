"""Image analysis service using multimodal LLM."""

import base64
import logging
from typing import Optional
from config import Config
from llm_client import LLMClient
from summary_engine import strip_thinking

logger = logging.getLogger(__name__)


def _extract_description(msg) -> Optional[str]:
    content = msg.content
    if isinstance(content, list):
        text = "".join(
            block.text for block in content if hasattr(block, "text")
        )
    elif isinstance(content, str):
        text = content
    else:
        text = ""
    if not text:
        text = getattr(msg, "reasoning_content", "") or ""
    text = text.strip()
    if not text:
        return None
    return strip_thinking(text) or None


class ImageAnalyzer:
    def __init__(self):
        self.llm_client = LLMClient()

    async def analyze_image_data(self, image_data: bytes) -> Optional[str]:
        try:
            # Encode the image data
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Prepare the prompt for image analysis
            prompt = (
                "Describe this image in a concise way (1-2 sentences). "
                "Focus on the main subject, activity, or content. "
                "If there's text in the image, include key information from it. "
                "Be specific and factual."
            )

            response = await self.llm_client.create_chat_completion(
                model=Config.IMAGE_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "low",
                                },
                            },
                        ],
                    }
                ],
            )

            msg = response.choices[0].message
            description = _extract_description(msg)
            logger.info(f"Generated image description: {description!r}")
            return description

        except Exception as e:
            logger.error(f"Failed to analyze image data: {e}")
            return None
