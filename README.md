# SuntoBot - Telegram Chat Summarization Bot
A Telegram bot that automatically saves chat messages and provides personalized summaries using an LLM when requested by users. The bot operates across multiple whitelisted groups and stores conversation history in a PostgreSQL database.

## Features
- **Multi-group Support**: Operate in multiple Telegram groups
- **Message Storage**: Save all text messages and compressed images to PostgreSQL
- **Personalized Summaries**: Generate summaries tailored to the requesting user
- **Flexible Time Ranges**: Support custom intervals (10m, 1h, 24h, 10d)
- **LLM Integration**: Uses OpenAI API with configurable base URL

## Quick Start
### Prerequisites
- Python 3.13+
- PostgreSQL database
- Telegram Bot Token (from @BotFather)
- OpenAI API key

### Installation
1. Clone the repository:
```bash
git clone <repository-url>
cd suntobot
```

2. Install dependencies using uv:
```bash
uv sync
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Set up PostgreSQL database and update DATABASE_URL in .env

5. Run the bot:
```bash
uv run python main.py
```

### Docker Setup
For a complete setup with PostgreSQL:

1. Copy environment variables:
```bash
cp .env.example demo/.env
# Edit demo/.env with your configuration
```

2. Run with Docker Compose:
```bash
cd demo
docker-compose up -d
```

## Configuration
### Environment Variables
| Variable             | Description                        | Required | Default                   |
| -------------------- | ---------------------------------- | -------- | ------------------------- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | Yes      | -                         |
| `WHITELISTED_GROUPS` | Comma-separated group IDs          | Yes      | -                         |
| `DATABASE_URL`       | PostgreSQL connection string       | Yes      | -                         |
| `OPENAI_API_KEY`     | OpenAI API key                     | Yes      | -                         |
| `OPENAI_BASE_URL`    | OpenAI API base URL                | No       | https://api.openai.com/v1 |
| `IMAGE_BASE_DIR`     | Directory for storing images       | No       | ./images                  |

## Usage
### Bot Commands
- `/start` - Show welcome message and help
- `/help` - Show help information
- `/sunto` - Get summary since your last message
- `/sunto 1h` - Get summary for last hour
- `/sunto 30m` - Get summary for last 30 minutes
- `/sunto 2d` - Get summary for last 2 days

### Supported Time Formats
- `m` - minutes (e.g., `30m`)
- `h` - hours (e.g., `2h`)
- `d` - days (e.g., `7d`)
