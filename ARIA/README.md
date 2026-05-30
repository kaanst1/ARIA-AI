# ARIA — Adaptive Reasoning & Intelligence Assistant

> **Tamamen lokal çalışan kişisel yapay zeka asistanı. Bulut yok. Telemetri yok. Hiçbir veri dışarı çıkmaz.**

ARIA, macOS üzerinde Ollama ile güçlenen çok ajanlı bir kişisel asistan sistemidir. Takvim, mail, müzik, kod, hafıza ve sistem yönetimini tek bir doğal dil arayüzünden kontrol eder.

---

## Kurulum

```bash
git clone https://github.com/kaanst1/ARIA-AI
cd ARIA-AI/ARIA
uv pip install -e .
```

**Ollama gereklidir:**
```bash
brew install ollama
ollama serve
ollama pull qwen2.5:7b   # Ana model
ollama pull llava:latest  # Görsel analiz için
```

**Başlat:**
```bash
bash start.sh
# → API: http://localhost:8000
# → UI:  http://localhost:5173
```

**Durdur:**
```bash
bash stop.sh
```

---

## Ne Yapabilir?

### 🧠 Çok Ajanlı Sistem

ARIA her göreve özel ajan kullanır ve gerektiğinde ajanları otomatik zincirler:

| Ajan | Tetikleyici | Ne Yapar |
|------|-------------|----------|
| `brief` | "günaydın", "sabah briefi" | Takvim + hava + sistem özeti, TTS ile seslendirir |
| `researcher` | "araştır", "haber" | Web arama, RSS, kaynak toplama |
| `deep_research` | "derin araştır" | Çok kaynaklı araştırma + atıf |
| `coder` | "kod yaz", "debug" | Kod üretme, analiz, test |
| `analyst` | "analiz et", "veri" | Dosya/veri analizi |
| `writer` | "makale", "tweet" | İçerik üretme |
| `memory` | "hatırla", "kaydet" | Semantik hafızaya kayıt/sorgulama |
| `planner` | "planla", "adım adım" | ReAct tabanlı çok adımlı görev |
| `chain` | "araştır sonra yaz" | **Çok-ajan otomatik zinciri** |
| `terminal` | "komut", "shell" | Sistem komutları |
| `monitor` | "izle", "takip et" | Süreç ve alert izleme |

#### Agent Zinciri (Chain)
"Yapay zeka trendlerini araştır ve makale yaz" → ARIA otomatik olarak `researcher → writer` zinciri kurar, her adımın çıktısı bir sonrakine girer.

---

### 🔧 Araçlar (40+ Tool)

#### macOS Sistem
| Araç | Komut Örneği |
|------|--------------|
| **Takvim** | "Bugün ne var?", "Yarın 15'e toplantı ekle" |
| **Apple Mail** | "Okunmamış mailler", "X'e mail gönder" |
| **iMessage** | "Y'ye mesaj gönder", "Okunmamış mesajlar" |
| **WhatsApp** | "WhatsApp'tan Z'ye yaz" |
| **Reminders** | "Alışveriş listesine süt ekle" |
| **Apple Notes** | "Notlara ekle", "Notlarda ara" |
| **Contacts** | "Ahmet'in telefonu" |
| **Spotlight** | "PDF dosyalarını bul" |
| **Uygulama Kontrolü** | "Chrome'u aç", "Açık uygulamalar" |
| **Odak Modu** | "DND aç", "Odak modunu kapat" |
| **Ekran Analizi** | "Ekrana bak" — LLaVA görsel analiz |

#### Ses & Konuşma
| Araç | Açıklama |
|------|----------|
| **Voice Mode** | `POST /voice/start` — sürekli dinle→yanıtla→dinle döngüsü, "dur aria" ile kapat |
| **Wake Word** | "Hey ARIA" ile elleri serbest tetikleme (Whisper tiny) |
| **TTS (Türkçe)** | Tüm yanıtlar Emel sesiyle seslendirilir |
| **Ses Kaydı** | Mikrofon butonu → Whisper transkript |

#### Üretkenlik
| Araç | Açıklama |
|------|----------|
| **Toplantı Asistanı** | `POST /meeting/start` → 15sn chunk Whisper transkript → `POST /meeting/stop` → LLM özet + aksiyon maddeleri + Notes'a kayıt |
| **Pomodoro** | 25/5/15 dk döngü — TTS + macOS bildirimi |
| **Git Zekası** | Commit özeti, git durumu, TODO tarama, diff analizi |
| **Belge Q&A (RAG)** | PDF/DOCX/CSV yükle → ChromaDB → "Bu belgede ne yazıyor?" |
| **Clipboard Geçmişi** | 2sn polling, 50 kayıt |
| **Shell Runner** | Güvenli komut çalıştırma |

#### Bilgi & Hafıza
| Araç | Açıklama |
|------|----------|
| **Semantik Hafıza** | Her konuşma ChromaDB'ye kaydedilir, yeni sorularda otomatik bağlam enjeksiyonu |
| **Obsidian** | Vault not oluştur, daily note'a ekle, grep arama — vault otomatik bulunur |
| **Belge RAG** | PDF/TXT/DOCX/CSV indeksle, doğal dille sor |

#### Güvenlik & Sistem
| Araç | Açıklama |
|------|----------|
| **Keychain** | macOS Keychain güvenli credential yönetimi — `security` komutu üzerinden |
| **Global Hotkey** | `Cmd+Shift+Space` — her uygulamadan ARIA'yı aç |
| **Menu Bar** | macOS system tray ikonu (rumps) |

#### Web & Araştırma
| Araç | Açıklama |
|------|----------|
| **Hava Durumu** | Open-Meteo API — anlık + 7 günlük tahmin |
| **Web Arama** | DuckDuckGo — gizlilik odaklı |
| **RSS** | Feed'lerden haber özeti |
| **Tarayıcı Kontrolü** | Safari/Chrome/Arc — URL aç, sekme, arama |
| **Podcast Özeti** | YouTube/podcast transkript + özet |

---

### 🧠 Hafıza Sistemi

#### Kısa Vadeli (SQLite)
Her oturum saklanır. Context'e son 20 mesaj otomatik eklenir.

#### Uzun Vadeli Semantik (ChromaDB)
Her konuşma vektör hafızaya kaydedilir. Yeni sorularda ilgili geçmiş otomatik enjekte edilir.
```
"Meriç'in doğum günü 15 Mart" → POST /memory
# İleride:
"Doğum gününe ne kadar var?" → ARIA otomatik hatırlar
```

---

### ⚙️ Workflow Motoru

`~/.aria/workflows/` altına YAML koy, otomatik çalışsın:

```yaml
name: sabah_rutini
trigger:
  type: schedule
  cron: "30 7 * * 1-5"
steps:
  - action: weather
    params: {}
  - action: brief
    params: {speak: true}
  - action: notify
    params: {title: "ARIA", message: "Günaydın!"}
```

**Tetikleyiciler:** `schedule` (cron) | `keyword` (kullanıcı mesajında anahtar kelime)

---

### 📄 Belge Q&A (RAG)

```
# Frontend'de 📄 butonuyla sürükle-bırak
# veya API:
POST /documents/upload   (multipart/form-data)
POST /documents/query    {"question": "..."}
GET  /documents          # İndekslenmiş belgeler
```

---

### 📊 Analytics Dashboard

Frontend'de **DASHBOARD** butonu:
- Toplam mesaj ve 7 günlük trend
- Ajan kullanım çubuk grafikleri
- Saatlik aktivite dağılımı

---

### 🔔 Proaktif Bildirimler

| Zamanlama | Eylem |
|-----------|-------|
| Sabah 08:00 | Sabah briefi bildirimi |
| Her 10 dk | 15 dk içinde toplantı → uyarı |
| Her 5 dk | CPU/RAM >%90 → kaynak uyarısı |
| Her saat | RSS yeni içerik kontrolü |
| Her 30 dk | Bağlam analizi + akıllı öneri |
| Her Cuma 18:00 | Haftalık kullanım raporu |
| Her gece 21:00 | Günlük özet kaydı |

---

### 📱 iOS Shortcut Entegrasyonu

Siri Shortcut'ta "URL Al" aksiyonuyla:

```
POST http://aria-ip:8000/shortcut
{"message": "hava nasıl", "format": "text"}

GET  http://aria-ip:8000/shortcut/brief    # Sabah briefi (düz metin)
GET  http://aria-ip:8000/shortcut/weather  # Hava durumu (tek satır)
```

---

## Klavye Kısayolları (Frontend)

| Kısayol | Eylem |
|---------|-------|
| `Cmd+K` | Command Palette — 15 komut, arrow key navigasyon |
| `Cmd+Shift+K` | Yeni oturum |
| `Cmd+Shift+Space` | ARIA'yı sistem genelinde aç |
| `?` | Klavye kısayol rehberi |
| `Escape` | Modalları kapat |
| `Drag & Drop` | Dosya analiz et / belge yükle |

---

## CLI Komutları

```bash
aria doctor                           # Sistem sağlık kontrolü
aria ask "günaydın"                   # Tek seferlik soru
aria ask "araştır kuantum" --agent researcher
aria memory search "geçen haftaki proje"
aria memory add "Meriç'in doğum günü 15 Mart"
aria memory count
aria workflow list
aria workflow run sabah_rutini
aria workflow delete eski_workflow
aria config show
aria config set weather_city Istanbul
aria config set model qwen2.5:14b
aria report weekly
aria report daily
aria serve --port 8000
aria doctor
```

---

## API Referansı (125 endpoint)

### Temel
```
POST /chat              — Streaming chat (SSE)
GET  /status            — Sistem durumu
GET  /models            — Yüklü modeller
GET  /models/smart-select?query=...
GET  /config | PATCH /config
```

### Ses & Voice
```
POST /voice/start | /voice/stop | GET /voice/status
POST /speech/chat         — STT + LLM + TTS döngüsü
POST /speak | /speak/stop
POST /speech/record/start | /speech/record/stop
GET  /wake-word/status
```

### Oturumlar & Hafıza
```
GET/POST /sessions | DELETE /sessions/{id}
GET  /sessions/{id}/export
POST /memory | GET /memory/search
```

### macOS Araçları
```
GET  /weather | /weather/forecast
POST /notes | GET /notes | GET /notes/search
POST /app/open | /app/quit | GET /app/running
GET  /contacts/search
POST /focus/enable | /focus/disable
GET  /spotlight/search
GET  /clipboard/history
GET  /context/suggest | /context/frontmost-app | /context/upcoming-meetings
```

### Mesajlaşma
```
POST /mail/send | GET /mail/unread
GET  /email/smart-inbox
POST /email/classify | /email/draft
POST /imessage/send | GET /imessage/unread
POST /whatsapp/send
```

### Belge & RAG
```
POST /documents/upload | /documents/index | /documents/query
GET  /documents
```

### Toplantı
```
POST /meeting/start | /meeting/stop
GET  /meeting/status | /meeting/list
```

### Obsidian
```
GET  /obsidian/info
POST /obsidian/setup | /obsidian/note | /obsidian/daily
GET  /obsidian/search | /obsidian/note
```

### Keychain
```
POST /keychain/set | GET /keychain/get
DELETE /keychain/{key} | GET /keychain/list
```

### Workflow & Otomasyon
```
GET/POST /workflows
POST /workflows/{name}/run
DELETE /workflows/{name}
POST /chain              — Çok-ajan zinciri
```

### Üretkenlik
```
POST /pomodoro/start | /pomodoro/stop | GET /pomodoro/status
GET  /git/log | /git/status | /git/todos
POST /reports/weekly | GET /reports/list
GET  /health/summary | /health/steps
GET  /analytics/usage | /analytics/patterns
```

### Medya
```
POST /spotify/play | /spotify/pause | /spotify/next
GET  /spotify/current | POST /spotify/volume
POST /screen/analyze | GET /screen/capture
```

### iOS Shortcut
```
POST /shortcut           — Genel sorgu (düz metin yanıt)
GET  /shortcut/brief     — Sabah briefi
GET  /shortcut/weather   — Hava durumu
```

---

## Konfigürasyon

`~/.aria/config.json`:

```json
{
  "model": "qwen2.5:7b",
  "language": "tr",
  "enable_tts": true,
  "tts_voice": "Emel",
  "weather_city": "Ankara",
  "enable_speech_input": false,
  "notification_enabled": true,
  "conversation_history_limit": 20,
  "cloud_fallback": false,
  "telemetry": false,
  "temperature": 0.7,
  "max_tokens": 4096
}
```

Frontend'deki ⚙️ butonu ile UI'dan değiştirilebilir.

---

## Mimari

```
ARIA/
├── start.sh / stop.sh          # Tek komutla başlat/durdur
├── src/ARIA/
│   ├── api.py                  # FastAPI (125 endpoint)
│   ├── agents/                 # 11 ajan + chain
│   │   └── chain.py            # LLM tabanlı otomatik zincir
│   ├── orchestrator/router.py  # Kural + LLM yönlendirici
│   ├── core/
│   │   ├── engine.py           # Ollama wrapper
│   │   ├── config.py           # Konfigürasyon
│   │   └── smart_router.py     # Karmaşıklık bazlı model seçimi
│   ├── memory/
│   │   ├── conversation_store.py  # SQLite oturum hafızası
│   │   ├── vector_memory.py       # ChromaDB semantik hafıza
│   │   └── semantic_context.py    # Otomatik bağlam enjeksiyonu
│   ├── automation/
│   │   └── workflow_engine.py  # YAML workflow motoru
│   ├── scheduler/
│   │   └── proactive.py        # Arka plan zamanlayıcı (8 görev)
│   ├── learning/
│   │   └── tracker.py          # Kullanım takibi + pattern analizi
│   └── tools/                  # 40+ araç modülü
│       ├── voice_mode.py       # Sürekli ses döngüsü
│       ├── meeting_assistant.py # Toplantı transkript + özet
│       ├── obsidian.py         # Vault entegrasyonu
│       ├── keychain.py         # macOS Keychain
│       ├── weather.py          # Open-Meteo API
│       └── ...
├── frontend/                   # React HUD arayüzü
│   └── src/App.jsx             # Command Palette, Settings, Documents
└── tests/                      # 27 birim testi
```

---

## Obsidian Kurulumu

```bash
# Vault yolunu ayarla (bir kez)
curl -X POST http://localhost:8000/obsidian/setup \
  -H "Content-Type: application/json" \
  -d '{"vault_path": "/Users/meric/Documents/MyVault"}'

# Kullanım
curl -X POST http://localhost:8000/obsidian/daily \
  -H "Content-Type: application/json" \
  -d '{"content": "ARIA ile not aldım", "heading": "Notlar"}'
```

---

## Gizlilik

- Tüm LLM çağrıları `localhost:11434` (Ollama)
- Web arama: DuckDuckGo — kullanıcı verisi içermeyen sorgular
- Hava durumu: Open-Meteo — şehir koordinatı gönderilir, kişisel veri yok
- Telemetri: **Kapalı**
- Bulut fallback: **Kapalı**
- Tüm veriler `~/.aria/` altında yerel saklanır
- API key'ler macOS Keychain'de şifreli saklanır

---

## Gereksinimler

- macOS 13+ (Ventura veya üzeri)
- Python 3.9+ (3.14 için `start.sh` kullan)
- Ollama (`qwen2.5:7b` minimum, `llava` görsel için)
- Node.js 18+ (frontend)
- `uv` paket yöneticisi

**Opsiyonel:**
- `rumps` — Menu bar ikonu
- `pynput` — Global hotkey
- `pymupdf` / `python-docx` — PDF/Word işleme
- `sounddevice` + `faster-whisper` — Ses özellikleri

---

*ARIA — Kişisel AI, Kişisel Cihazında.*
