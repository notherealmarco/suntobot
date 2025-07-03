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

# Copy application code
COPY demo .

# Create images directory
RUN mkdir -p /app/images

# Expose port (not needed for bot, but good practice)
EXPOSE 8000

# Run the bot
CMD ["uv", "run", "python", "main.py"]
