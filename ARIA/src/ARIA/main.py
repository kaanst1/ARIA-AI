# ARIA - Ana Giriş Noktası

import sys
from ARIA.core.engine import ARIAEngine

def doctor():
    engine = ARIAEngine()
    status = engine.doctor()
    
    print("\n🔍 ARIA Sistem Durumu")
    print("=" * 40)
    print(f"Engine      : {status['engine']}")
    print(f"Ollama      : {'✅ Çalışıyor' if status['ollama_running'] else '❌ Kapalı'}")
    print(f"Aktif Model : {status['active_model']}")
    print(f"Modeller    : {', '.join(status['available_models']) or 'Yok'}")
    print(f"Bulut       : {'⚠️ Açık' if status['cloud_fallback'] else '✅ Kapalı'}")
    print("=" * 40)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        doctor()
        return

    from ARIA.orchestrator.router import Orchestrator
    o = Orchestrator()
    o.interactive()

if __name__ == "__main__":
    main()