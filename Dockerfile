FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml uv.lock* ./

# Install uv and dependencies
RUN pip install uv
RUN uv sync --frozen

# Copy migration files, prompts, and source code
COPY run_migration.py ./
COPY alembic ./alembic
COPY alembic.ini ./
COPY prompts ./prompts
COPY src ./src

# Expose port (not needed for bot, but good practice)
EXPOSE 8000

# Run the bot
# CMD ["uv", "run", "python", "src/main.py"]
CMD ["sh", "-c", "uv run run_migration.py upgrade head && uv run python src/main.py"]