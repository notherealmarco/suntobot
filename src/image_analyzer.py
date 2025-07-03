"""Image analysis service using multimodal LLM."""

import base64
import openai
import logging
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """Handles image analysis using multimodal LLM."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY, base_url=Config.OPENAI_BASE_URL
        )

    async def analyze_image_data(self, image_data: bytes) -> Optional[str]:
        """
        Analyze image data and return a description.

        Args:
            image_data: Raw image bytes

        Returns:
            Description of the image content or None if analysis fails
        """
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

            response = await self.client.chat.completions.create(
                model="clusterino.gemma3:27b-it-qat",  # Using your multimodal model
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "low",  # Use "low" for faster processing
                                },
                            },
                        ],
                    }
                ],
                max_tokens=150,
                temperature=0.3,
            )

            description = response.choices[0].message.content.strip()
            logger.info(f"Generated image description: {description}")
            return description

        except Exception as e:
            logger.error(f"Failed to analyze image data: {e}")
            return None
