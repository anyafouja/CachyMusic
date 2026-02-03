FROM python:3.10-slim

# Install FFmpeg dan dependencies yang diperlukan
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && echo "deb http://deb.debian.org/debian bullseye main contrib non-free" >> /etc/apt/sources.list \
    && echo "deb http://deb.debian.org/debian bullseye-updates main contrib non-free" >> /etc/apt/sources.list \
    && apt-get update && apt-get install -y \
    ffmpeg \
    libavcodec-extra \
    && rm -rf /var/lib/apt/lists/*

# Verify FFmpeg installation
RUN ffmpeg -version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
