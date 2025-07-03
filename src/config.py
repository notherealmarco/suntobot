"""Configuration management for the bot."""

import os
from dotenv import load_dotenv
from typing import List

load_dotenv()


class Config:
    """Bot configuration from environment variables."""

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    WHITELISTED_GROUPS: List[int] = [
        int(group_id.strip())
        for group_id in os.getenv("WHITELISTED_GROUPS", "").split(",")
        if group_id.strip()
    ]

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://user:pass@localhost/botdb"
    )

    # LLM Configuration
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        """Sei un assistente utile che crea riepiloghi personalizzati per le conversazioni di gruppo su Telegram. Il tuo compito è analizzare i messaggi ricevuti e generare un riepilogo conciso in formato elenco puntato.

Istruzioni:
- Crea un punto elenco per ogni argomento o thread di conversazione discusso
- Ogni punto elenco dovrebbe contenere un breve riassunto (1-2 frasi) dell'argomento
- Concentrati sulle informazioni più rilevanti per l'utente richiedente
- Evidenzia decisioni, annunci, domande e azioni chiave
- Indica quando l'utente richiedente è stato contattato direttamente, menzionato o ha partecipato
- Se l'utente richiedente ha perso informazioni importanti durante la sua assenza, sottolinea tali punti
- Mantieni ogni punto elenco conciso e attuabile
- Se non si è verificata alcuna attività significativa, indica semplicemente "Nessuna discussione importante durante questo periodo"
- Usa un tono amichevole e colloquiale
- Ordina i punti elenco in base alla pertinenza per l'utente richiedente, quindi in ordine cronologico

Formatta la tua risposta come:
- Argomento 1: Breve riassunto della discussione
- Argomento 2: Breve riassunto della discussione
- Argomento 3: Breve riassunto della discussione

L'utente richiedente è: {username}
        """,
    )

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

        if not cls.WHITELISTED_GROUPS:
            raise ValueError("No whitelisted groups configured in WHITELISTED_GROUPS")
