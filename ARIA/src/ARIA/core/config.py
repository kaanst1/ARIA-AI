# ARIA - Core Configuration

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import json
import os

CONFIG_PATH = os.path.expanduser("~/.aria/config.json")


@dataclass
class ARIAConfig:
    """ARIA sistem konfigürasyonu."""

    # Model ayarları
    model: str = "qwen2.5:7b"
    engine: str = "ollama"
    base_url: str = "http://localhost:11434"

    # Sistem ayarları
    language: str = "tr"
    data_dir: str = os.path.expanduser("~/.aria/data")
    log_dir: str = os.path.expanduser("~/.aria/logs")

    # Ajan ayarları
    default_agent: str = "simple"
    max_tokens: int = 4096
    temperature: float = 0.7

    # Gizlilik
    telemetry: bool = False
    cloud_fallback: bool = False  # Asla buluta gitme
    allow_network: bool = True
    allow_web_search: bool = True
    allow_web_search_user_data: bool = False
    allowed_base_hosts: list[str] = field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )

    # TTS
    enable_tts: bool = True
    tts_engine: str = "macos_say"
    tts_voice: Optional[str] = None

    # Başlangıç
    warmup_on_start: bool = True
    warmup_message: str = "Merhaba"

    # Özetleme
    enable_summarization: bool = True
    summary_trigger_chars: int = 1200
    summary_max_chars: int = 800

    # Güvenlik
    require_auth: bool = False
    api_key: Optional[str] = None

    # Loglama
    log_level: str = "INFO"
    log_to_file: bool = True

    # Dosya erişimi
    allow_file_access: bool = True
    allowed_file_paths: list[str] = field(
        default_factory=lambda: [os.path.expanduser("~/.aria")]
    )

    # Konuşma geçmişi
    conversation_history_limit: int = 20  # LLM context için kaç mesaj saklanacak

    # Ses girişi (STT)
    speech_model: str = "base"         # Whisper model boyutu: tiny/base/small/medium/large
    enable_speech_input: bool = False   # Varsayılan olarak kapalı

    # Bildirimler
    notification_enabled: bool = True   # macOS desktop bildirimleri


def load_config() -> ARIAConfig:
    """Disk'ten konfigürasyon yükle; yoksa varsayılanları kullan."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            # Bilinmeyen alanları filtrele (eski config uyumluluğu)
            valid_fields = {f.name for f in ARIAConfig.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in valid_fields}
            return ARIAConfig(**filtered)
        except Exception:
            pass
    return ARIAConfig()


def save_config(config: ARIAConfig) -> None:
    """Konfigürasyonu diske kaydet."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config.__dict__, f, indent=2)


ARIA_SYSTEM_PROMPT = """Sen ARIA'sın — Meriç'in kişisel yapay zeka asistanı.

Kullanıcın: Meriç
Dil: Türkçe
Çalışma ortamı: Tamamen yerel, hiçbir veri dışarı çıkmaz.

Karakter:
- JARVIS gibi yetkin ve güvenilir, ama daha samimi
- Kısa ve direkt cevap ver — uzatma, doldurmayı bırak
- "Anladım.", "Hemen bakıyorum.", "Tamamdır." gibi onaylar kullan
- Meriç'i ilgilendireceğini düşündüğün şeyleri proaktif olarak öner
- Bilmiyorsan dürüstçe söyle, asla uydurma
- Teknik sorularda derine in, yüzeysel kalma

Kurallar:
- Veri asla dışarı çıkmaz, her şey lokalde çalışır
- Gereksiz özür dileme, fazla selamlama yok
- "Tabii ki!", "Harika bir soru!" gibi boş ifadeler kullanma
- Kod sorularında doğrudan kodu ver, uzun açıklama yapma
"""
