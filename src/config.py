"""Configuration management for the bot."""

import os


class Config:
    """Bot configuration from environment variables."""

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    WHITELISTED_GROUPS = [
        int(group_id.strip())
        for group_id in os.getenv("WHITELISTED_GROUPS", "").split(",")
        if group_id.strip()
    ]

    # Database Configuration
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/botdb")

    # LLM Configuration
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SYSTEM_PROMPT = os.getenv(
        "SYSTEM_PROMPT",
        "You are a helpful assistant that creates personalized chat summaries. "
        "You will receive a collection of messages from a Telegram group chat and need to "
        "provide a concise summary tailored for the requesting user. "
        "Guidelines: "
        "- Focus on information most relevant to the requesting user "
        "- Highlight key discussions, decisions, and action items "
        "- Mention when the user was directly addressed or mentioned "
        "- Keep summaries concise (2-3 paragraphs maximum) "
        "- Use a friendly, conversational tone "
        "- If no significant activity occurred, mention this briefly",
    )

    # File Storage
    IMAGE_BASE_DIR = os.getenv("IMAGE_BASE_DIR", "/app/images")

    # Bot Behavior
    SUMMARY_COMMAND = os.getenv("SUMMARY_COMMAND", "/sunto")

    @classmethod
    def validate(cls):
        """Validate required configuration."""
        required_vars = [
            ("TELEGRAM_BOT_TOKEN", cls.TELEGRAM_BOT_TOKEN),
            ("OPENAI_API_KEY", cls.OPENAI_API_KEY),
        ]

        missing = [name for name, value in required_vars if not value]

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        if not cls.WHITELISTED_GROUPS:
            raise ValueError("No whitelisted groups configured in WHITELISTED_GROUPS")

        # Create image directory if it doesn't exist
        os.makedirs(cls.IMAGE_BASE_DIR, exist_ok=True)
