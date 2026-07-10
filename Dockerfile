FROM python:3.12-slim

# Install ffmpeg for video merging
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot/ .

# Create downloads directory
RUN mkdir -p downloads data

CMD ["python", "main.py"]
