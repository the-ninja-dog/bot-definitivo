# Script de limpieza y ejecución segura
Write-Host "🧹 Limpiando procesos antiguos..." -ForegroundColor Yellow
Stop-Process -Name "msedge" -ErrorAction SilentlyContinue
Stop-Process -Name "chrome" -ErrorAction SilentlyContinue
Stop-Process -Name "python" -ErrorAction SilentlyContinue

Write-Host "🧹 Borrando sesión anterior..." -ForegroundColor Yellow
if (Test-Path "whatsapp_session_edge") {
    Remove-Item -Recurse -Force "whatsapp_session_edge"
}

Write-Host "🚀 Iniciando Bot con Microsoft Edge..." -ForegroundColor Green
python bot_whatsapp_playwright.py
