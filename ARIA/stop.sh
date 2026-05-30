#!/usr/bin/env bash
# ARIA durdurma scripti

echo ""
echo "ARIA durduruluyor..."

# API
if [ -f /tmp/aria_api.pid ]; then
    kill $(cat /tmp/aria_api.pid) 2>/dev/null && echo "✅ API durduruldu" || echo "⚠️  API zaten kapalıydı"
    rm -f /tmp/aria_api.pid
else
    PID=$(lsof -ti:8000 2>/dev/null)
    [ -n "$PID" ] && kill $PID 2>/dev/null && echo "✅ API durduruldu"
fi

# Frontend
if [ -f /tmp/aria_frontend.pid ]; then
    kill $(cat /tmp/aria_frontend.pid) 2>/dev/null && echo "✅ Frontend durduruldu" || echo "⚠️  Frontend zaten kapalıydı"
    rm -f /tmp/aria_frontend.pid
else
    PID=$(lsof -ti:5173 2>/dev/null)
    [ -n "$PID" ] && kill $PID 2>/dev/null && echo "✅ Frontend durduruldu"
fi

echo "ARIA kapatıldı."
echo ""
