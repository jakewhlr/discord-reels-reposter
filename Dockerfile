# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Install system dependencies (ffmpeg for video compression)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY bot.py ./
COPY config.py ./
COPY cogs/ ./cogs/
COPY utils/ ./utils/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    discord.py>=2.3.0 \
    yt-dlp>=2023.10.0 \
    python-dotenv>=1.0.0 \
    aiofiles>=23.0.0 \
    ffmpeg-python>=0.2.0

# Create directory for temporary downloads
RUN mkdir -p /app/temp_downloads

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "-u", "bot.py"]
