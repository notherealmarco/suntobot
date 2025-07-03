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

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | Yes | - |
| `WHITELISTED_GROUPS` | Comma-separated group IDs | Yes | - |
| `DATABASE_URL` | PostgreSQL connection string | Yes | - |
| `OPENAI_API_KEY` | OpenAI API key | Yes | - |
| `OPENAI_BASE_URL` | OpenAI API base URL | No | https://api.openai.com/v1 |
| `IMAGE_BASE_DIR` | Directory for storing images | No | ./images |
| `SUMMARY_COMMAND` | Command to trigger summaries | No | /sunto |

### Getting Group IDs

To get your Telegram group ID:
1. Add @raw_info_bot to your group
2. Send any message
3. The bot will reply with the group's chat_id
4. Remove @raw_info_bot from the group

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

## Architecture

### Components

- **Message Handler**: Captures and stores messages and images
- **Summary Engine**: Generates personalized summaries using LLM
- **Database Manager**: Handles PostgreSQL operations
- **Command Handler**: Processes bot commands

### Database Schema

```sql
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    username VARCHAR(255),
    message_text TEXT,
    image_path VARCHAR(500),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_id BIGINT UNIQUE NOT NULL
);

CREATE INDEX idx_messages_chat_user_time ON messages(chat_id, user_id, timestamp);
```

## Security

- Only operates in whitelisted groups
- Validates all inputs
- Secure storage of API keys
- Image compression and validation
- Database transaction safety

## Development

### Project Structure

```
suntobot/
├── main.py              # Main bot application
├── config.py            # Configuration management
├── database.py          # Database models and manager
├── message_handler.py   # Message processing
├── command_handler.py   # Command processing
├── summary_engine.py    # LLM integration
├── time_utils.py        # Time parsing utilities
├── pyproject.toml       # Dependencies
├── Dockerfile           # Docker configuration
└── demo/
    └── docker-compose.yml  # Complete setup
```

### Running Tests

```bash
uv run pytest
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Open an issue on GitHub
- Check the documentation
- Review the logs for error details