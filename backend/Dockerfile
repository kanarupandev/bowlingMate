FROM python:3.11-slim

# Install system dependencies for MediaPipe/OpenCV/FFmpeg
# libavcodec-extra + libavformat are REQUIRED for OpenCV to read H.264 videos
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libavcodec-extra \
    libavformat-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install MediaPipe first (heaviest, ~15-20 min) - version 0.10.21 has solutions API
RUN pip install --default-timeout=600 --no-cache-dir mediapipe==0.10.21

# Install remaining requirements
RUN pip install --default-timeout=300 --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the application (mocks enabled for testing)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
