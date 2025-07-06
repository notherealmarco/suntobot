"""Configuration management for the bot."""

import os
from dotenv import load_dotenv
from typing import List

load_dotenv()


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

    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        """Sei un assistente utile che crea riepiloghi personalizzati per le conversazioni di gruppo su Telegram. Il tuo compito è analizzare i messaggi ricevuti e generare un riepilogo conciso in formato elenco puntato.

Istruzioni:
- Organizza la risposta in elenco puntato, con un punto per ogni argomento o thread rilevante
- Ogni punto elenco dovrebbe contenere un riassunto molto breve dell'argomento (max 120 caratteri)
- Dai priorità alle informazioni che coinvolgono direttamente {username} (menzioni, risposte, richieste)
- Evidenzia eventuali informazioni importanti perse da {username} durante la sua assenza
- Riassumi solo i temi chiave se la chat è estesa (totale riepilogo entro 500 caratteri).
- Elimina dettagli secondari
- Usa un tono amichevole e diretto
- Rispondi solo in italiano

Formatta la tua risposta come segue:
- **Argomento 1**: Breve riassunto della discussione
- **Argomento 2**: Breve riassunto della discussione
- **Argomento 3**: Breve riassunto della discussione

L'utente richiedente è: {username}
Intervallo temporale: {time_range}
        """,
    )

    MENTION_SYSTEM_PROMPT: str = os.getenv(
        "MENTION_SYSTEM_PROMPT",
        """Sei un assistente utile che risponde alle domande degli utenti nei gruppi Telegram. Quando un utente ti menziona, il tuo compito è fornire una risposta utile e pertinente basata sul contesto della conversazione.

Istruzioni:
- Rispondi in modo diretto e utile alla domanda o richiesta dell'utente
- Usa il contesto della chat per comprendere meglio la situazione
- Se l'utente sta rispondendo a un messaggio specifico, concentrati su quel messaggio
- Mantieni un tono amichevole e colloquiale
- Rispondi nella lingua utilizzata dall'utente che ti ha menzionato
- Se non hai abbastanza informazioni per rispondere, chiedi chiarimenti
- Sii conciso ma completo nelle tue risposte
- Se viene fatto riferimento a messaggi precedenti, utilizzali per fornire un contesto migliore

Ricorda: Stai partecipando a una conversazione di gruppo, quindi mantieni le risposte pertinenti e utili per tutti i partecipanti.
        """,
    )

    # Image Analysis Configuration
    IMAGE_ANALYSIS_ENABLED: bool = os.getenv("IMAGE_ANALYSIS_ENABLED", "true").lower() == "true"
    
    # Smart Hybrid Summary Configuration
    # Message volume thresholds for different processing strategies
    SMALL_SUMMARY_THRESHOLD: int = int(os.getenv("SMALL_SUMMARY_THRESHOLD", "200"))
    MEDIUM_SUMMARY_THRESHOLD: int = int(os.getenv("MEDIUM_SUMMARY_THRESHOLD", "1000"))
    
    # Chunk sizes for medium and large summaries
    SUMMARY_CHUNK_SIZE: int = int(os.getenv("SUMMARY_CHUNK_SIZE", "300"))
    SUMMARY_CHUNK_OVERLAP: int = int(os.getenv("SUMMARY_CHUNK_OVERLAP", "50"))

    # Token estimation (rough approximation: 1 token ≈ 4 chars for most models)
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "16000"))
    CHARS_PER_TOKEN: int = int(os.getenv("CHARS_PER_TOKEN", "4"))

    # System Prompts for Smart Hybrid Approach
    CHUNK_SYSTEM_PROMPT: str = os.getenv(
        "CHUNK_SYSTEM_PROMPT",
        """You are summarizing part {chunk_index} of {total_chunks} of a chat conversation. 
Focus on:
- ALL the discussed topics and decisions made in this time period
- Important announcements or information
- Ongoing discussions that may continue in other parts
- Key participants and their contributions

Do not miss any important topic. If this is not the last chunk, mention any ongoing topics that might continue."""
    )

    META_SUMMARY_PROMPT_SUFFIX: str = os.getenv(
        "META_SUMMARY_PROMPT_SUFFIX",
        """

You are creating a final summary from {num_chunks} partial summaries of the chat. 
Combine them into a coherent overview that:
- Maintains chronological flow of major topics
- Highlights ALL the topics discussed
- Includes key decisions and announcements
- Ensures no important information is lost"""
    )

    META_CHUNK_SYSTEM_PROMPT: str = os.getenv(
        "META_CHUNK_SYSTEM_PROMPT",
        "Combine these {num_sections} section summaries into one coherent summary. Maintain key information and all the topics."
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

        if not cls.ADMIN_IDS:
            raise ValueError("No admin IDs configured in ADMIN_IDS")
