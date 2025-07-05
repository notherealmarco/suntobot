⚠️ SuntoBot is in an early development stage. Expect issues

# SuntoBot - Telegram Chat Summarization Bot
A Telegram bot that automatically saves chat messages and provides personalized summaries using an LLM when requested by users. The bot operates in groups authorized by admins and stores conversation history in a PostgreSQL database.

## Features
- **Dynamic Group Management**: Admins can allow/deny groups using commands
- **Message Storage**: Save all text messages and compressed images to PostgreSQL
- **Forwarded Message Support**: Tracks and displays information about forwarded messages
- **Personalized Summaries**: Generate summaries tailored to the requesting user
- **Flexible Time Ranges**: Support custom intervals (10m, 1h, 24h, 10d)
- **LLM Integration**: Uses OpenAI API with configurable base URL
  - We recommend running a local Ollama server for LLM processing, using `gemma3`.

## Quick Start

### Option 1: Docker Setup (Recommended)
The easiest way to get started is using Docker Compose with the included PostgreSQL database.

1. **Clone the repository:**
```bash
git clone <repository-url>
cd suntobot
```

2. **Set up environment variables:**
```bash
cp .env.example .env
```

3. **Edit the `.env` file** with your configuration:
```bash
# Required: Get your bot token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Required: Your Telegram user ID (get from @userinfobot)
ADMIN_IDS="123456789"

# Database (use this for Docker setup)
DATABASE_URL=postgresql://suntobot:suntopassword@db:5432/suntobot

# Required: OpenAI API key
OPENAI_API_KEY=your_openai_api_key_here

# Optional: Use different OpenAI-compatible API
OPENAI_BASE_URL=https://api.openai.com/v1

# Optional: Change the models (defaults work with OpenAI)
SUMMARY_MODEL=gpt-4o-mini
IMAGE_MODEL=gpt-4o-mini

# Optional: Mention behavior configuration
MENTION_CONTEXT_SIZE=30
MENTION_CONTEXT_HOURS=4
OLD_MENTION_CONTEXT_SIZE=10

# Optional: Custom system prompts (uncomment to use)
# SYSTEM_PROMPT="Your custom summary prompt..."
# MENTION_SYSTEM_PROMPT="Your custom mention reply prompt..."
```

4. **Start the bot with Docker Compose:**
```bash
# Copy the example docker-compose file
cp docker-compose.example.yml docker-compose.yml

# Start the bot and database
docker-compose up -d

# Check logs
docker-compose logs -f bot
```

### Option 2: Local Development Setup
For development or if you prefer running locally:

#### Prerequisites
- Python 3.13+
- PostgreSQL database
- Telegram Bot Token (from @BotFather)
- OpenAI API key

#### Installation
1. **Clone and setup:**
```bash
git clone <repository-url>
cd suntobot
```

2. **Install dependencies using uv:**
```bash
uv sync
```

3. **Set up environment variables:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. **Set up PostgreSQL database:**
   - Create a PostgreSQL database
   - Update `DATABASE_URL` in `.env` with your database connection string
   - Example: `postgresql://username:password@localhost:5432/suntobot`

5. **Run database migrations:**
```bash
uv run python run_migration.py
```

6. **Run the bot:**
```bash
uv run python src/main.py
```

## Configuration

### Environment Variables
All configuration is done through environment variables in the `.env` file:

| Variable                  | Description                        | Required | Default                   | Example                              |
| ------------------------- | ---------------------------------- | -------- | ------------------------- | ------------------------------------ |
| `TELEGRAM_BOT_TOKEN`      | Telegram bot token from @BotFather | **Yes**  | -                         | `1234567890:ABCdefGHIjklMNOpqrSTUvwx` |
| `ADMIN_IDS`               | Comma-separated admin user IDs     | **Yes**  | -                         | `"123456789,987654321"`              |
| `DATABASE_URL`            | PostgreSQL connection string       | **Yes**  | -                         | `postgresql://user:pass@host:5432/db` |
| `OPENAI_API_KEY`          | OpenAI API key                     | **Yes**  | -                         | `sk-...`                            |
| `OPENAI_BASE_URL`         | OpenAI API base URL                | No       | `https://api.openai.com/v1` | `http://localhost:11434/v1`         |
| `SUMMARY_MODEL`           | Model name for summaries           | No       | `gpt-4o-mini`             | `gemma2:27b`, `claude-3-sonnet`     |
| `IMAGE_MODEL`             | Model name for image analysis      | No       | `gpt-4o-mini`             | `gpt-4o`, `claude-3-sonnet`         |
| `MENTION_CONTEXT_SIZE`    | Messages to include when mentioned | No       | `30`                      | `50`, `20`                          |
| `MENTION_CONTEXT_HOURS`   | Hours to look back for context     | No       | `4`                       | `6`, `2`                            |
| `OLD_MENTION_CONTEXT_SIZE`| Older messages for context         | No       | `10`                      | `15`, `5`                           |
| `SYSTEM_PROMPT`           | Custom system prompt for summaries | No       | Built-in Italian prompt   | See placeholders section below      |
| `MENTION_SYSTEM_PROMPT`   | Custom prompt for mention replies  | No       | Built-in Italian prompt   | `"You are a helpful assistant..."`   |

### Getting Required Values

#### 1. Telegram Bot Token
1. Message @BotFather on Telegram
2. Use `/newbot` command and follow instructions
3. Copy the token provided

#### 2. Admin User IDs
1. Message @userinfobot on Telegram
2. Copy your user ID from the response
3. For multiple admins, separate IDs with commas: `"123456789,987654321"`

#### 3. OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (starts with `sk-`)

### Using Alternative LLM Providers
SuntoBot supports any OpenAI-compatible API. Examples:

#### Local Ollama
```bash
# In .env
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama  # Can be anything for local Ollama
SUMMARY_MODEL=gemma2:27b
IMAGE_MODEL=gemma2:27b
```

#### Anthropic Claude (via proxy)
```bash
# In .env
OPENAI_BASE_URL=https://your-claude-proxy.com/v1
OPENAI_API_KEY=your_anthropic_api_key
SUMMARY_MODEL=claude-3-sonnet-20240229
IMAGE_MODEL=claude-3-sonnet-20240229
```

### Advanced Configuration

#### Mention Behavior Settings
When users mention the bot in a group, these parameters control how the bot responds:

- **`MENTION_CONTEXT_SIZE`**: Number of recent messages to consider (default: 30)
- **`MENTION_CONTEXT_HOURS`**: Hours of chat history to look back (default: 4)  
- **`OLD_MENTION_CONTEXT_SIZE`**: Additional older messages for context (default: 10)

Example: If a user mentions the bot, it will analyze the last 30 messages within 4 hours, plus 10 older messages for additional context.

#### Model Configuration
- **`SUMMARY_MODEL`**: Model used for generating chat summaries
- **`IMAGE_MODEL`**: Model used for analyzing images in chat (must support vision)

#### Custom System Prompts
You can customize how the bot behaves by setting custom system prompts:

- **`SYSTEM_PROMPT`**: Controls how summaries are generated (default is in Italian)
- **`MENTION_SYSTEM_PROMPT`**: Controls how the bot responds to mentions (default is in Italian)

**Note**: The default prompts are in Italian. If you want English responses, you'll need to set custom prompts.

##### System Prompt Placeholders
The `SYSTEM_PROMPT` supports the following placeholders that are automatically replaced:

- **`{username}`**: The Telegram username of the user requesting the summary
- **`{time_range}`**: A description of the time period being summarized (e.g., "last 2 hours", "since your last message")

Example custom system prompt:
```bash
SYSTEM_PROMPT="You are a helpful assistant that creates summaries for {username}. 
Analyze the messages from {time_range} and provide a concise summary.
Focus on topics that mention or involve {username} directly."
```

The `MENTION_SYSTEM_PROMPT` does not use any placeholders and receives the conversation context directly.

## Usage

### Setting Up Your Bot

#### Step 1: Add Bot to Group
1. Invite your bot to a Telegram group
2. Make sure the bot has permission to read messages

#### Step 2: Allow the Group
An admin must run the `/allow` command in the group:
```
/allow
```
The bot will respond confirming the group is now allowed.

#### Step 3: Start Using Summary Commands
Once allowed, any group member can request summaries:
```
/sunto          # Summary since your last message
/sunto 1h       # Summary for last hour
/sunto 30m      # Summary for last 30 minutes
/sunto 2d       # Summary for last 2 days
```

### Bot Commands

#### User Commands (in allowed groups):
- `/start` - Show welcome message and help
- `/help` - Show help information  
- `/sunto` - Get summary since your last message
- `/sunto <time>` - Get summary for specified time period

#### Admin Commands:
- `/allow` - Allow the current group to use the bot (use in group)
- `/deny <group_id>` - Deny a group from using the bot (use in private chat with bot)
- `/list` - List all allowed groups with IDs (use in private chat with bot)

### Advanced Usage

#### Custom Time Formats
- `m` - minutes (e.g., `30m`, `45m`)
- `h` - hours (e.g., `2h`, `12h`) 
- `d` - days (e.g., `7d`, `30d`)

#### Managing Multiple Groups
Admins can manage multiple groups from a private chat with the bot:
1. Get group IDs using `/list` command
2. Deny groups using `/deny <group_id>`
3. Allow new groups by using `/allow` in the target group

### Troubleshooting

#### Bot Not Responding
1. Check bot logs: `docker-compose logs bot`
2. Verify the bot token in `.env`
3. Ensure the bot has message reading permissions in the group

#### Database Issues
1. Check database logs: `docker-compose logs db`
2. Verify `DATABASE_URL` is correct in `.env`
3. Try restarting: `docker-compose restart`

#### Summary Generation Issues
1. Check your OpenAI API key and usage limits
2. Verify `OPENAI_BASE_URL` if using alternative providers
3. Check logs for specific error messages

#### Group Not Allowed
1. Ensure an admin has run `/allow` in the group
2. Check allowed groups with `/list` in private chat
3. Verify your user ID is in `ADMIN_IDS`

## Docker Management

### Common Docker Commands
```bash
# Start the bot
docker-compose up -d

# Stop the bot
docker-compose down

# Restart the bot
docker-compose restart

# View logs
docker-compose logs -f bot        # Bot logs
docker-compose logs -f db         # Database logs  
docker-compose logs -f            # All logs

# Update to latest version
docker-compose pull
docker-compose up -d

# Reset database (⚠️ deletes all data)
docker-compose down -v
docker-compose up -d
```

### Updating SuntoBot
```bash
# Pull latest image
docker-compose pull bot

# Restart with new version
docker-compose up -d bot
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Open an issue on GitHub
- Check the documentation
- Review the logs for error details