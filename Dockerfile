# ETAPA 1: Construir la Web App con Flutter
FROM ghcr.io/cirruslabs/flutter:stable AS flutter-builder
WORKDIR /app
COPY . .
RUN flutter pub get
RUN flutter build web

# ETAPA 2: Configurar Python para el Bot
FROM python:3.11-slim
WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar la Web App construida en la etapa 1 a la carpeta 'web'
# ESTA ES LA MAGIA QUE ARREGLA EL 404
COPY --from=flutter-builder /app/build/web ./web

# Copiar el resto del código del Bot
COPY . .

# Comando de arranque
CMD gunicorn -w 4 -b 0.0.0.0:$PORT api_server:app