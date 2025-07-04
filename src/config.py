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
    SUMMARY_MODEL: str = os.getenv("SUMMARY_MODEL", "gemma3:27b-it-qat")
    IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "gemma3:27b-it-qat")

    # Mention Reply Configuration
    MENTION_CONTEXT_SIZE: int = int(os.getenv("MENTION_CONTEXT_SIZE", "30"))
    MENTION_CONTEXT_HOURS: int = int(os.getenv("MENTION_CONTEXT_HOURS", "4"))
    OLD_MENTION_CONTEXT_SIZE: int = int(os.getenv("OLD_MENTION_CONTEXT_SIZE", "10"))

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
- Usa un tono amichevole e colloquiale
- Ordina i punti elenco in base alla pertinenza per l'utente richiedente, quindi in ordine cronologico
- Sii breve e diretto, evitando dettagli non necessari. I punti elenco dovrebbero essere coincisi e facili da leggere
- Se la history è molto lunga, riassumi i punti principali. Non creare una risposta troppo lunga. Regola il livello di dettagli sulla base delle informazioni da riassumere, in modo da creare mai un messaggio troppo lungo. Tieniti sotto i 600 caratteri se possibile.

Formatta la tua risposta come:
- Argomento 1: Breve riassunto della discussione
- Argomento 2: Breve riassunto della discussione
- Argomento 3: Breve riassunto della discussione

L'utente richiedente è: {username}
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
