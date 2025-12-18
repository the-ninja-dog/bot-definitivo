# Stage 1: Build Flutter Web
FROM ghcr.io/cirruslabs/flutter:3.16.0 AS flutter-builder

WORKDIR /app
COPY . .

# Enable web support and build
# Setting base-href to / because Flask serves it at root
RUN flutter config --enable-web
RUN flutter build web --release --base-href /

# Stage 2: Python Backend with Static Files
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python Backend code
COPY . .

# Copy Built Flutter Web Assets from Stage 1
# Renaming to 'web' to match Flask configuration and reduce confusion
COPY --from=flutter-builder /app/build/web ./web

# Env vars
ENV PORT=5000
EXPOSE 5000

# Run
CMD ["python", "api_server.py"]
