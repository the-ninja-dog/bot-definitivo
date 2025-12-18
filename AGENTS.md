# 🚀 Barberia Bot & Web App - Deployment Guide

## ☁️ Railway Deployment Architecture

This project is configured to run as a **single container** on Railway that hosts both the **Python Backend (Bot)** and the **Flutter Web App (Dashboard)**.

### 🏗️ Build System (Critical)
We use a **Multi-Stage Dockerfile** to build the Flutter app and set up Python.
*   **Stage 1:** `ghcr.io/cirruslabs/flutter` builds the frontend.
*   **Stage 2:** `python:3.11-slim` runs the backend and serves the frontend.

**⚠️ IMPORTANT:**
*   **`Procfile` and `runtime.txt` MUST NOT exist.** If they do, Railway forces the "Nixpacks Python Builder" and ignores our Dockerfile, causing the frontend build to fail.
*   **`railway.json`** is included to explicitly tell Railway to use `builder: DOCKERFILE`.

### 📂 Directory Structure (Runtime)
*   `/app/api_server.py`: Main Flask application.
*   `/app/web/`: Contains the compiled Flutter Web static files (`index.html`, `main.dart.js`, etc.).
*   `api_server.py` is configured to serve `index.html` from `/app/web/` at the root URL `/`.

### 🗄️ Database
The application supports **Dual Mode**:
1.  **SQLite (Default/Local):** Uses `barberia.db`.
2.  **PostgreSQL (Cloud):** If `DATABASE_URL` environment variable is present, it connects using `psycopg2`.
    *   *Action:* Add a PostgreSQL plugin in Railway to persist data.

### 🐛 Troubleshooting 404
If the Web App returns 404:
1.  Check Build Logs: Must see `FROM ghcr.io/cirruslabs/flutter` and `flutter build web`.
2.  If logs say `Using railpack...`, verify `Procfile` is deleted.
3.  Check App Logs: The app prints `📂 CONTENIDO DE CARPETA 'web': [...]` on startup. If this list is empty or missing, the copy step in Dockerfile failed.
