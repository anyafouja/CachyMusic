FROM python:3.10-slim

# Install all required dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libopus-dev \
    libopus0 \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the files
COPY . .

# Run the bot
CMD ["python", "main.py"]