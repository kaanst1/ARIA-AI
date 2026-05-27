# ARIA - Core Configuration

from dataclasses import dataclass, field
from typing import Optional
import json
import os

CONFIG_PATH = os.path.expanduser("~/.aria/config.json")

@dataclass
class ARIAConfig:
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
    allowed_base_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"]) 
    enable_tts: bool = True
    tts_engine: str = "macos_say"
    tts_voice: Optional[str] = None
    warmup_on_start: bool = True
    warmup_message: str = "Merhaba"
    enable_summarization: bool = True
    summary_trigger_chars: int = 1200
    summary_max_chars: int = 800
    require_auth: bool = False
    api_key: Optional[str] = None
    log_level: str = "INFO"
    log_to_file: bool = True
    allow_file_access: bool = True
    allowed_file_paths: list[str] = field(
        default_factory=lambda: [os.path.expanduser("~/.aria")]
    )

def load_config() -> ARIAConfig:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            return ARIAConfig(**data)
    return ARIAConfig()

def save_config(config: ARIAConfig):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config.__dict__, f, indent=2)
ARIA_SYSTEM_PROMPT = """Sen ARIA'sın — Adaptive Reasoning & Intelligence Assistant.

Kullanıcın: Meriç
Dil: Türkçe (aksi belirtilmedikçe)
Karakter: Zeki, direkt, gereksiz lafı olmayan. Jarvis gibi ama daha samimi.

Kurallar:
- Veri asla dışarı çıkmaz, her şey lokalde
- Kısa ve net cevap ver, uzatma
- Meriç "kanka" diye hitap edebilir, sen de samimi ol
- Bilmiyorsan söyle, uydurma
- Teknik konularda derine in, yüzeysel kalma
"""       