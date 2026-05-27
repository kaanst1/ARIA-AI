# ARIA Frontend

ARIA'nın React + Vite tabanlı kullanıcı arayüzü.  
React + Vite UI for the ARIA assistant.

---

## 🇹🇷 Türkçe

### Gereksinimler

- Node.js ≥ 18
- Çalışan ARIA API (`aria serve` — varsayılan: `http://localhost:8000`)

### Kurulum ve Çalıştırma

```bash
npm install

# İsteğe bağlı: API adresini özelleştir
cp .env.example .env.local
# VITE_API_URL=http://localhost:8000

# Geliştirme sunucusu
npm run dev        # http://localhost:5173

# Production build
npm run build
npm run preview
```

### Özellikler

| Özellik | Açıklama |
|---------|----------|
| **Ajan seçici** | Sol panelden 8 ajan arasında geçiş |
| **Streaming** | Token token SSE — cevaplar yazılırken görünür |
| **Canlı sistem durumu** | `/status` endpoint'ten gerçek Ollama durumu ve model adı |
| **Klavye kısayolları** | `Enter` gönder, `Shift+Enter` yeni satır |
| **Responsive** | Mobil için daraltılmış panel + 2 sütun ajan grid |

### Ortam Değişkenleri

`.env.local` dosyası oluşturarak özelleştir (`.env.example`'den kopyala):

```env
# Backend API adresi — boş bırakılırsa localhost:8000 kullanılır
VITE_API_URL=http://localhost:8000
```

### Proje Yapısı

```
frontend/
├── src/
│   ├── App.jsx        # Ana bileşen (sohbet, streaming, ajan yönetimi)
│   ├── App.css        # Tüm stiller
│   ├── index.css      # CSS değişkenleri, reset, font import
│   └── main.jsx       # React entry point
├── .env.example       # Ortam değişkeni şablonu
├── vite.config.js     # Vite yapılandırması (dev proxy dahil)
└── package.json
```

### Geliştirici Notu

`vite.config.js` dev modunda `/chat`, `/status` vb. isteklerini `localhost:8000`'e proxy'ler. `VITE_API_URL` ayarlanmamışsa bu proxy devreye girer. Production'da backend'i aynı origin'de servis et ya da `VITE_API_URL`'yi aç.

---

## 🇬🇧 English

### Requirements

- Node.js ≥ 18
- Running ARIA API (`aria serve` — default: `http://localhost:8000`)

### Setup

```bash
npm install
cp .env.example .env.local   # optional — customise API URL
npm run dev                   # http://localhost:5173
```

### Features

- **Agent switcher** — 8 specialised agents in the sidebar
- **Streaming UI** — SSE token-by-token, live cursor animation
- **Live system status** — real Ollama state and model name from `/status`
- **Keyboard shortcuts** — `Enter` to send, `Shift+Enter` for newline
- **Responsive layout** — collapses to mobile-friendly grid

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | Backend API base URL |
