# SuntoBot Setup Guide

This guide will help you set up and run SuntoBot, a Telegram chat summarization bot.

## Quick Setup

### 1. Prerequisites

- Python 3.13+ installed
- PostgreSQL database (can use Docker)
- Telegram Bot Token (from @BotFather)
- OpenAI API key

### 2. Installation

```bash
# Clone and navigate to the project
cd /path/to/suntobot

# Install dependencies
uv sync --extra dev

# Run health check
uv run python health_check.py
```

### 3. Configuration

Create a `.env` file with your settings:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Required
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
WHITELISTED_GROUPS="-1001234567890,-1001234567891"
DATABASE_URL=postgresql://user:pass@localhost:5432/suntobot
OPENAI_API_KEY=your_openai_api_key

# Optional
OPENAI_BASE_URL=https://api.openai.com/v1
IMAGE_BASE_DIR=./images
SUMMARY_COMMAND=/sunto
```

### 4. Database Setup

#### Option A: Docker (Recommended)
```bash
cd demo
docker-compose up -d db
```

#### Option B: Local PostgreSQL
```sql
CREATE DATABASE suntobot;
CREATE USER suntobot WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE suntobot TO suntobot;
```

### 5. Getting Required Information

#### Telegram Bot Token
1. Start a chat with @BotFather on Telegram
2. Send `/newbot`
3. Follow the instructions to create your bot
4. Save the token provided

#### Group IDs
1. Add @raw_info_bot to your Telegram group
2. Send any message in the group
3. The bot will reply with the group's chat_id
4. Remove @raw_info_bot from the group
5. Use the chat_id in WHITELISTED_GROUPS

#### OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key to your .env file

### 6. Running the Bot

#### Development Mode
```bash
uv run python main.py
```

#### Production with Docker
```bash
cd demo
# Edit .env with your configuration
docker-compose up -d
```

### 7. Usage

Once running, the bot will:
- Automatically save messages in whitelisted groups
- Respond to summary commands

Commands:
- `/start` - Show help
- `/sunto` - Get summary since your last message
- `/sunto 1h` - Get summary for last hour
- `/sunto 30m` - Get summary for last 30 minutes
- `/sunto 2d` - Get summary for last 2 days

## Troubleshooting

### Common Issues

1. **Import errors**: Run `uv sync` to install dependencies
2. **Config validation failed**: Check your .env file values
3. **Database connection failed**: Verify DATABASE_URL and database is running
4. **Bot not responding**: Check TELEGRAM_BOT_TOKEN and group IDs

### Health Check
```bash
uv run python health_check.py
```

### Logs
The bot outputs logs to stdout. In production, redirect to a file:
```bash
uv run python main.py > bot.log 2>&1
```

### Testing
```bash
uv run python -m pytest test_bot.py -v
```

## Security Notes

- Keep your .env file secure and never commit it
- Only add the bot to trusted groups
- Regularly rotate your API keys
- Monitor the images directory size
- Use strong database passwords

## Support

- Check the README.md for detailed documentation
- Review logs for error messages
- Run health_check.py to diagnose issues
- Ensure all environment variables are set correctly
