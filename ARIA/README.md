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
ollama pull qwen2.5:7b
```

**API ve Frontend başlat:**
```bash
# Backend (terminal 1)
aria-api

# Frontend (terminal 2)
cd frontend && npm install && npm run dev
```

Tarayıcıda `http://localhost:5173` adresini aç.

---

## Ne Yapabilir?

### 🧠 Çok Ajanlı Sistem

ARIA her göreve özel ajan kullanır:

| Ajan | Tetikleyici | Ne Yapar |
|------|-------------|----------|
| `brief` | "günaydın", "sabah briefi" | Takvim + hava + sistem özeti, TTS ile seslendirir |
| `researcher` | "araştır", "haber", "hava" | Web arama, RSS, kaynak toplama |
| `deep_research` | "derin araştır", "kapsamlı" | Çok kaynaklı araştırma + atıf |
| `coder` | "kod yaz", "debug", "hata" | Kod üretme, analiz, test |
| `analyst` | "analiz et", "veri", "tablo" | Dosya/veri analizi |
| `writer` | "makale", "tweet", "rapor" | İçerik üretme |
| `memory` | "hatırla", "not al", "kaydet" | Semantik hafızaya kayıt/sorgulama |
| `planner` | "planla", "adım adım" | Çok adımlı görev planlama |
| `terminal` | "komut", "shell", "disk" | Sistem komutları |
| `monitor` | "izle", "takip et" | Süreç ve alert izleme |
| `chat` | genel sohbet | Doğrudan LLM yanıtı |

---

### 🔧 Araçlar (35+ Tool)

#### macOS Sistem Entegrasyonu
| Araç | Komut Örneği |
|------|--------------|
| **Takvim** | "Bugün ne var?", "Yarın saat 15'e toplantı ekle" |
| **Apple Mail** | "Okunmamış mailler", "X'e mail gönder" |
| **iMessage** | "Y'ye mesaj gönder", "Okunmamış iMessage'lar" |
| **WhatsApp** | "WhatsApp'tan Z'ye yaz" |
| **Reminders** | "Alışveriş listesine süt ekle" |
| **Apple Notes** | "Notlara ekle", "Notlarda ara" |
| **Contacts** | "Ahmet'in telefonu", "Rehberde ara" |
| **Spotlight** | "PDF dosyalarını bul", "Bu dosya nerede" |
| **Uygulama Kontrolü** | "Chrome'u aç", "Açık uygulamalar" |
| **Odak Modu** | "DND aç", "Odak modunu kapat" |
| **Ekran Analizi** | "Ekrana bak" — LLaVA görsel analiz |

#### Medya & Ses
| Araç | Komut Örneği |
|------|--------------|
| **Spotify** | "Müzik çal", "Sıradaki şarkı", "Ses %50" |
| **TTS (Türkçe)** | Tüm yanıtlar Emel sesiyle seslendirilir |
| **Ses Kaydı (Whisper)** | Mikrofon butonuyla konuş, otomatik transkript |
| **Wake Word** | "Hey ARIA" ile elleri serbest tetikleme |

#### Web & Araştırma
| Araç | Komut Örneği |
|------|--------------|
| **Hava Durumu** | "Hava nasıl?", "3 günlük tahmin" |
| **Web Arama** | DuckDuckGo tabanlı gizlilik odaklı arama |
| **RSS** | Eklenen feed'lerden haber özeti |
| **Tarayıcı Kontrolü** | "Chrome'da aç", "Aktif sekme ne" |
| **Podcast Özeti** | YouTube/podcast özeti |

#### Verimlilik
| Araç | Komut Örneği |
|------|--------------|
| **Pomodoro** | "Pomodoro başlat", 25dk çalış/5dk mola + TTS bildirim |
| **Git Zekası** | "Son commit'leri özetle", "TODO'ları tara", "Diff analizi" |
| **Belge Q&A** | PDF/DOCX/CSV yükle → "Bu belgede ne yazıyor?" |
| **Pano Geçmişi** | 2 saniyede bir otomatik kayıt, 50 giriş |
| **Shell Runner** | Güvenli komut çalıştırma |
| **Log Analizi** | Hata loglarını yorumla |

---

### 🧠 Hafıza Sistemi

#### Kısa Vadeli (SQLite)
Her oturum saklanır. Context'e son 20 mesaj otomatik eklenir.

#### Uzun Vadeli Semantik Hafıza (ChromaDB)
- Her konuşma otomatik vektör hafızaya kaydedilir
- Yeni sorularda ilgili geçmiş otomatik context'e enjekte edilir

```
"Meriç'in doğum günü 15 Mart" → Kalıcı hafızaya kaydedildi
# İleride:
"Doğum gününe ne kadar var?" → ARIA otomatik hatırlar
```

---

### 📄 Belge Q&A (RAG)

PDF, TXT, DOCX, CSV indeksle ve sor:

```
POST /documents/index  {"file_path": "/Users/meric/sozlesme.pdf"}
POST /documents/query  {"question": "Sözleşme bitiş tarihi ne?"}
```

---

### ⚙️ Workflow Motoru

`~/.aria/workflows/` altına YAML koy, otomatik çalışsın:

```yaml
name: sabah_rutini
trigger:
  type: schedule
  cron: "30 7 * * 1-5"   # Hafta içi 07:30
steps:
  - action: weather
    params: {}
  - action: brief
    params: {speak: true}
  - action: notify
    params: {title: "ARIA", message: "Günaydın!"}
```

**Tetikleyiciler:** `schedule` (cron) veya `keyword` (kullanıcı mesajı)  
**Aksiyonlar:** `brief`, `weather`, `tts`, `notify`, `get_unread_emails`, `chat`, `shell`, `remember`

---

### 🤖 Akıllı Model Seçimi

| Karmaşıklık | Örnek | Model |
|-------------|-------|-------|
| Basit | "günaydın", "saat kaç" | `qwen2.5:3b` (hızlı) |
| Orta | "haberleri özetle" | `qwen2.5:7b` |
| Karmaşık | "derin araştırma yap" | `qwen2.5:14b` (varsa) |

---

### 📧 Email Zekası

- **Sınıflandırma**: acil / toplantı / fatura / spam / iş
- **Toplantı tespiti**: Zoom/Teams linki, tarih/saat otomatik çıkarımı
- **Taslak yanıt**: Ton seçimiyle otomatik üretim
- **Smart Inbox**: `GET /email/smart-inbox`

---

### 📊 Analytics Dashboard

Frontend'de DASHBOARD butonu ile açılır:
- Toplam mesaj ve 7 günlük trend
- Ajan kullanım çubuğu grafikleri
- Saatlik aktivite dağılımı

---

### 🔔 Proaktif Bildirimler (Arka Plan)

| Zamanlama | Eylem |
|-----------|-------|
| Sabah 08:00 | Sabah briefi bildirimi |
| Her 10 dk | 15 dk içinde toplantı varsa uyarı |
| Her 5 dk | CPU/RAM %90+ ise kaynak uyarısı |
| Her saat | RSS yeni içerik kontrolü |
| Her 30 dk | Bağlam analizi + akıllı öneri |
| Her Cuma 18:00 | Haftalık kullanım raporu |
| Her gece 21:00 | Günlük özet kaydı |

---

### 🎯 Bağlam Farkındalığı

ARIA aktif uygulamayı ve takvimi analiz eder:
- VS Code açıksa → Kod yardımı önerisi
- Mail açıksa → Gelen kutusu özeti
- 15 dk içinde toplantı → Hazırlık notu teklifi
- Sabah 07-09 → Brief hatırlatması

---

## API Referansı

### Temel
```
POST /chat              — Streaming chat
GET  /status            — Sistem durumu
GET  /models            — Yüklü modeller
```

### Oturumlar
```
GET    /sessions
POST   /sessions
DELETE /sessions/{id}
GET    /sessions/{id}/export
```

### macOS Araçları
```
GET  /weather | /weather/forecast
POST /notes | GET /notes | GET /notes/search
POST /app/open | /app/quit | GET /app/running
GET  /contacts/search
POST /focus/enable | /focus/disable | GET /focus/status
GET  /spotlight/search
GET  /clipboard/history
POST /calendar/add | GET /brief/calendar
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

### Hafıza & Belge
```
POST /memory | GET /memory/search
POST /documents/index | /documents/query | GET /documents
```

### Workflow
```
GET    /workflows
POST   /workflows
POST   /workflows/{name}/run
DELETE /workflows/{name}
```

### Verimlilik
```
POST /pomodoro/start | /pomodoro/stop | GET /pomodoro/status
GET  /git/log | /git/status | /git/todos
POST /reports/weekly | GET /reports/list | /reports/daily
GET  /health/summary | /health/steps
```

### Analitik
```
GET /analytics/usage
GET /analytics/patterns
GET /models/smart-select
```

### Medya
```
POST /speak | /speak/stop | GET /speak/status
POST /spotify/play | /spotify/pause | /spotify/next
GET  /spotify/current | POST /spotify/volume
POST /screen/analyze | GET /screen/capture
POST /speech/chat | /speech/record/start | /speech/record/stop
GET  /wake-word/status
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
  "telemetry": false
}
```

---

## Mimari

```
ARIA/
├── src/ARIA/
│   ├── api.py                    # FastAPI (70+ endpoint)
│   ├── agents/                   # 11 özel ajan
│   ├── orchestrator/router.py    # Kural + LLM yönlendirici
│   ├── core/
│   │   ├── engine.py             # Ollama wrapper
│   │   ├── config.py             # Konfigürasyon
│   │   └── smart_router.py       # Karmaşıklık bazlı model seçimi
│   ├── memory/
│   │   ├── conversation_store.py # SQLite oturum hafızası
│   │   ├── vector_memory.py      # ChromaDB semantik hafıza
│   │   └── semantic_context.py   # Otomatik bağlam enjeksiyonu
│   ├── automation/
│   │   └── workflow_engine.py    # YAML workflow motoru
│   ├── scheduler/
│   │   └── proactive.py          # Arka plan zamanlayıcı (8 görev)
│   ├── learning/
│   │   └── tracker.py            # Kullanım takibi + pattern analizi
│   └── tools/                    # 35+ araç modülü
├── frontend/                     # React HUD arayüzü
└── presets/                      # Hazır yapılandırma şablonları
```

---

## Gizlilik

- Tüm LLM çağrıları `localhost:11434` (Ollama) üzerinden
- Web arama: DuckDuckGo — kullanıcı verisi içermeyen sorgular
- Telemetri: **Kapalı**
- Bulut fallback: **Kapalı**
- Tüm veriler `~/.aria/` altında yerel olarak saklanır

---

## Gereksinimler

- macOS 13+ (Ventura veya üzeri)
- Python 3.9+
- Ollama (`qwen2.5:7b` minimum)
- Node.js 18+ (frontend)
- `uv` paket yöneticisi (önerilir)

**Opsiyonel:**
- `rumps` — Menu bar ikonu
- `pymupdf` / `python-docx` — PDF/Word işleme

---

*ARIA — Kişisel AI, Kişisel Cihazında.*
