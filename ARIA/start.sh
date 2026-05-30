#!/usr/bin/env bash
# ARIA başlangıç scripti

set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$BASE_DIR/.venv"
SRC="$BASE_DIR/src"
FRONTEND="$BASE_DIR/frontend"

export PYTHONPATH="$SRC:${PYTHONPATH:-}"

_info()  { echo "  $1"; }
_ok()    { echo "✅ $1"; }
_warn()  { echo "⚠️  $1"; }
_err()   { echo "❌ $1"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "          ARIA — Başlatılıyor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Ollama kontrolü
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    _ok "Ollama çalışıyor"
else
    _warn "Ollama kapalı — başlatılıyor..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
fi

# API zaten çalışıyor mu?
if curl -s http://localhost:8000/status > /dev/null 2>&1; then
    _ok "ARIA API zaten çalışıyor (port 8000)"
else
    _info "API başlatılıyor..."
    PYTHONPATH="$SRC" "$VENV/bin/python3" -m uvicorn ARIA.api:app \
        --host 0.0.0.0 --port 8000 \
        > /tmp/aria_api.log 2>&1 &
    API_PID=$!
    echo "$API_PID" > /tmp/aria_api.pid
    sleep 5
    if curl -s http://localhost:8000/status > /dev/null 2>&1; then
        _ok "ARIA API başlatıldı (PID: $API_PID)"
    else
        _err "API başlatılamadı! Log: /tmp/aria_api.log"
        tail -5 /tmp/aria_api.log
        exit 1
    fi
fi

# Frontend zaten çalışıyor mu?
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    _ok "Frontend zaten çalışıyor (port 5173)"
else
    _info "Frontend başlatılıyor..."
    npm --prefix "$FRONTEND" run dev > /tmp/aria_frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" > /tmp/aria_frontend.pid
    sleep 3
    _ok "Frontend başlatıldı (PID: $FRONTEND_PID)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🤖 ARIA Hazır!"
echo "     UI  → http://localhost:5173"
echo "     API → http://localhost:8000"
echo "     Docs→ http://localhost:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Tarayıcıda aç
open http://localhost:5173 2>/dev/null || true
