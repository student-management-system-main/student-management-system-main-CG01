FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by mysqlclient and numpy/scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure models directory exists for persisted model files
RUN mkdir -p /app/models

EXPOSE 5001

CMD ["python", "app.py"]
