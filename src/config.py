"""Configuration management for the bot."""

import os
from pathlib import Path
from dotenv import load_dotenv
from typing import List

load_dotenv()


def _load_prompt_from_file(filename: str) -> str:
    """Load prompt content from a text file in the prompts directory."""
    # Get the directory where this config.py file is located
    current_dir = Path(__file__).parent
    # Navigate to the prompts directory (one level up from src, then into prompts)
    prompts_dir = current_dir.parent / "prompts"
    file_path = prompts_dir / filename
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    except Exception as e:
        raise Exception(f"Error reading prompt file {file_path}: {e}")


class Config:
    """Bot configuration from environment variables."""

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ADMIN_IDS: List[int] = [
        int(admin_id.strip())
        for admin_id in os.getenv("ADMIN_IDS", "").split(",")
        if admin_id.strip()
    ]

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://user:pass@localhost/botdb"
    )

    # LLM Configuration
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Model Configuration
    SUMMARY_MODEL: str = os.getenv("SUMMARY_MODEL", "gpt-4o-mini")
    IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "gpt-4o-mini")

    # Mention Reply Configuration
    MENTION_CONTEXT_SIZE: int = int(os.getenv("MENTION_CONTEXT_SIZE", "30"))
    MENTION_CONTEXT_HOURS: int = int(os.getenv("MENTION_CONTEXT_HOURS", "4"))
    OLD_MENTION_CONTEXT_SIZE: int = int(os.getenv("OLD_MENTION_CONTEXT_SIZE", "10"))

    # Load prompts from text files
    SYSTEM_PROMPT: str = _load_prompt_from_file("system_prompt.txt")
    SYSTEM_PROMPT_SUFFIX: str = _load_prompt_from_file("system_prompt_suffix.txt")
    SYSTEM_PROMPT_CHUNK_PREAMBLE: str = _load_prompt_from_file("system_prompt_chunk_preamble.txt")
    MENTION_SYSTEM_PROMPT: str = _load_prompt_from_file("mention_system_prompt.txt")
    CHUNK_SYSTEM_PROMPT: str = _load_prompt_from_file("chunk_system_prompt.txt")
    CHUNK_SYSTEM_PROMPT_SUFFIX: str = _load_prompt_from_file("chunk_system_prompt_suffix.txt")
    META_SUMMARY_SYSTEM_PROMPT: str = _load_prompt_from_file("meta_summary_system_prompt.txt")
    META_SUMMARY_SYSTEM_PROMPT_SUFFIX: str = _load_prompt_from_file("meta_summary_system_prompt_suffix.txt")

    # Image Analysis Configuration
    IMAGE_ANALYSIS_ENABLED: bool = (
        os.getenv("IMAGE_ANALYSIS_ENABLED", "true").lower() == "true"
    )

    # Chunk sizes for medium and large summaries
    SUMMARY_CHUNK_SIZE: int = int(os.getenv("SUMMARY_CHUNK_SIZE", "70"))

    # Parallel processing configuration
    MAX_PARALLEL_CHUNKS: int = int(os.getenv("MAX_PARALLEL_CHUNKS", "2"))

    @classmethod
    def validate(cls) -> None:
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

        if not cls.ADMIN_IDS:
            raise ValueError("No admin IDs configured in ADMIN_IDS")
