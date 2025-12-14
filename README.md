# 🏠 Barbería Bot - Sistema Completo en Railway

Sistema integral para barbería con bot de WhatsApp automático + app Flutter + servidor en la nube.

## 🚀 Quick Start Local

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Ejecutar todo
python iniciar.py todo

# En otra terminal:
flutter run -d edge
```

## ☁️ Desplegar en Railway

### 1. Crear cuenta Railway
- https://railway.app
- Paga $5 USD mínimo

### 2. Conectar a GitHub
- Sube este proyecto a GitHub
- En Railway: "Deploy from GitHub"
- Selecciona tu repo

### 3. Configurar Variables de Entorno
En Railway → Variables:

```
FLASK_ENV=production
PORT=5000
API_KEY=tu_gemini_api_key
BOT_ACTIVO=true
```

### 4. Tu app estará en:
```
https://tu-proyecto-railroad.railway.app
```

## 📱 Barbero accede desde iPhone

1. Abre Safari
2. Entra a tu URL de Railway
3. Funciona como app web

## 🔐 Modelo de Negocio

- **Barbero paga**: $5/mes
- **Tú controlas**: ON/OFF desde la app
- **Si no paga**: desactivas en Railway Dashboard

## 📁 Archivos principales

- `api_server.py` - Servidor Flask
- `bot_whatsapp_playwright.py` - Bot WhatsApp
- `lib/main.dart` - App Flutter
- `main_railway.py` - Entry point Railway

## ⚠️ Nota Importante

**Playwright en Railway**: Requiere navegador. Si no funciona:
- Opción 1: Ejecuta el bot en tu PC (conéctalo al servidor)
- Opción 2: Usa Twilio (API oficial WhatsApp)

¡Listo para vender! 🎉

