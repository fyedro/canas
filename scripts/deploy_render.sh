#!/bin/bash
# =============================================================================
#  🏋️  CAÑAS - Deploy a RENDER.com (100% gratis, sin tarjeta de crédito)
# =============================================================================
# Render es la ÚNICA plataforma seria en 2026 que:
#  ✅ No pide tarjeta de crédito
#  ✅ Soporta FastAPI nativamente
#  ✅ 750 horas/mes gratuitas
#  ✅ Despliegue automático desde GitHub
#  ⚠️  Se duerme a los 15 min de inactividad (se despierta solo al entrar)
# =============================================================================

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   🏋️  CAÑAS - Deploy a Render.com                       ║"
echo "║   100% GRATIS - Sin tarjeta de crédito                   ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PASO 1: Sube el código a GitHub"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  cd $HOME/CAÑAS"
echo "  git init"
echo "  git add ."
echo "  git commit -m 'CAÑAS - Gym Tracker'"
echo "  # Crea un repo en https://github.com/new"
echo "  git remote add origin https://github.com/TU_USUARIO/canas.git"
echo "  git push -u origin main"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PASO 2: Regístrate en Render"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1. Ve a https://dashboard.render.com/register"
echo "  2. Regístrate con GitHub (NO pide tarjeta)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PASO 3: Despliega CAÑAS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1. En el dashboard: 'New +' → 'Web Service'"
echo "  2. Conecta tu GitHub y selecciona 'canas'"
echo "  3. Completa:"
echo "     - Name: canas"
echo "     - Runtime: Python 3"
echo "     - Region: la más cercana (Frankfurt o Singapur)"
echo "     - Branch: main"
echo "     - Build Command: pip install -r requirements.txt"
echo "     - Start Command: uvicorn app.main:app --host 0.0.0.0 --port \$PORT"
echo "     - Plan: Free"
echo ""
echo "  4. Haz clic en 'Advanced' y añade:"
echo "     - Variable: SECRET_KEY = (deja que Render la genere)"
echo "     - Variable: DEBUG = false"
echo "     - Variable: PYTHON_VERSION = 3.12.8"
echo ""
echo "  5. 'Create Web Service' y espera 2-3 min"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PASO 4: ✔️  Ya está vivo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Render te dará una URL tipo:"
echo "  https://canas.onrender.com"
echo ""
echo "  📱 Funciona en PC y móvil"
echo "  ⚠️  La primera carga tarda 30-60s (se despierta)"
echo "  💾 Los datos se guardan en SQLite (persisten aunque hiberne)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💰 Alternativa: subida local con ngrok (sin dormir)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Si prefieres no tener tiempos de espera:"
echo "  1. brew install ngrok"
echo "  2. ngrok http 8000"
echo "  Te da una URL pública mientras tu PC esté encendido"
echo ""
