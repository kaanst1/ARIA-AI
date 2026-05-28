"""ARIA command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from ARIA.core.engine import ARIAEngine
from ARIA.orchestrator.router import Orchestrator
from ARIA.core.presets import list_presets, apply_preset


# ── Mevcut komutlar ───────────────────────────────────────────────────────────

def _cmd_status(_args: argparse.Namespace) -> None:
    engine = ARIAEngine()
    d = engine.doctor()
    print(f"\n{'='*40}")
    print(f"  ARIA Sistem Durumu")
    print(f"{'='*40}")
    print(f"  Engine      : {d['engine']}")
    print(f"  Ollama      : {'✅ Çalışıyor' if d['ollama_running'] else '❌ Kapalı'}")
    print(f"  Aktif Model : {d['active_model']}")
    print(f"  Modeller    : {', '.join(d['available_models']) or 'Yok'}")
    print(f"  Bulut       : {'⚠️  Açık' if d['cloud_fallback'] else '✅ Kapalı'}")
    print(f"{'='*40}\n")


def _cmd_chat(args: argparse.Namespace) -> None:
    orchestrator = Orchestrator()
    response = orchestrator.dispatch(args.message)
    print(response)


def _cmd_presets(args: argparse.Namespace) -> None:
    if args.action == "list":
        print("\n".join(list_presets()))
    elif args.action == "apply":
        apply_preset(args.name)
        print(f"Preset uygulandi: {args.name}")


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    uvicorn.run("ARIA.api:app", host=args.host, port=args.port)


# ── Yeni komutlar ─────────────────────────────────────────────────────────────

def _cmd_doctor(_args: argparse.Namespace) -> None:
    """Sistem sağlık kontrolü — tüm bileşenleri kontrol et."""
    import subprocess
    print("\n🔍 ARIA Doktor Raporu\n" + "="*50)

    # Ollama
    engine = ARIAEngine()
    d = engine.doctor()
    print(f"{'✅' if d['ollama_running'] else '❌'} Ollama: {'çalışıyor' if d['ollama_running'] else 'kapalı — `ollama serve` çalıştır'}")
    if d['available_models']:
        print(f"   Modeller: {', '.join(d['available_models'])}")

    # ChromaDB
    try:
        import chromadb  # noqa
        print("✅ ChromaDB: kurulu")
    except ImportError:
        print("⚠️  ChromaDB: kurulu değil — `pip install chromadb`")

    # Whisper
    try:
        import faster_whisper  # noqa
        print("✅ Whisper (faster-whisper): kurulu")
    except ImportError:
        print("⚠️  Whisper: kurulu değil — `pip install faster-whisper`")

    # rumps (menu bar)
    try:
        import rumps  # noqa
        print("✅ Menu bar (rumps): kurulu")
    except ImportError:
        print("⚠️  rumps: kurulu değil — `pip install rumps`")

    # pynput (global hotkey)
    try:
        import pynput  # noqa
        print("✅ Global hotkey (pynput): kurulu")
    except ImportError:
        print("⚠️  pynput: kurulu değil — `pip install pynput`")

    # ~/.aria dizini
    from pathlib import Path
    aria_dir = Path.home() / ".aria"
    print(f"{'✅' if aria_dir.exists() else '❌'} ~/.aria dizini: {aria_dir}")

    # API
    try:
        import requests
        r = requests.get("http://localhost:8000/status", timeout=2)
        print(f"✅ API: çalışıyor (http://localhost:8000)")
    except Exception:
        print("⚠️  API: çalışmıyor — `aria serve` veya `aria-api` çalıştır")

    print("="*50 + "\n")


def _cmd_memory(args: argparse.Namespace) -> None:
    """Semantik hafızada ara veya not ekle."""
    if args.action == "search":
        if not args.query:
            print("Kullanım: aria memory search <sorgu>")
            sys.exit(1)
        from ARIA.memory.vector_memory import memory_search
        results = memory_search(args.query, n=args.limit)
        if not results or (len(results) == 1 and "error" in results[0]):
            print("Sonuç bulunamadı veya ChromaDB mevcut değil.")
            return
        print(f"\n🔍 '{args.query}' için {len(results)} sonuç:\n")
        for i, r in enumerate(results, 1):
            rel = r.get("relevance", 0)
            ts = r.get("metadata", {}).get("timestamp", "")[:10]
            content = r.get("content", "")[:200]
            print(f"[{i}] ({ts}) — Benzerlik: {rel:.2f}\n    {content}\n")

    elif args.action == "add":
        if not args.text:
            print("Kullanım: aria memory add <metin>")
            sys.exit(1)
        from ARIA.memory.semantic_context import remember_fact
        ok = remember_fact(args.text, category=args.category)
        print(f"{'✅ Kaydedildi' if ok else '❌ Kaydedilemedi'}: {args.text[:60]}")

    elif args.action == "count":
        from ARIA.memory.vector_memory import _vector_memory
        print(f"Semantik hafızada {_vector_memory.get_count()} kayıt var.")


def _cmd_workflow(args: argparse.Namespace) -> None:
    """Workflow yönetimi."""
    from ARIA.automation.workflow_engine import load_workflows, run_workflow, delete_workflow, list_workflow_names

    if args.action == "list":
        names = list_workflow_names()
        if not names:
            print("Kayıtlı workflow yok. ~/.aria/workflows/ klasörüne YAML ekle.")
            return
        print(f"\n📋 Workflow'lar ({len(names)}):")
        for n in names:
            print(f"  • {n}")

    elif args.action == "run":
        if not args.name:
            print("Kullanım: aria workflow run <isim>")
            sys.exit(1)
        wfs = {w.get("name"): w for w in load_workflows()}
        if args.name not in wfs:
            print(f"❌ '{args.name}' bulunamadı.")
            sys.exit(1)
        print(f"▶ Workflow çalıştırılıyor: {args.name}")
        results = run_workflow(wfs[args.name])
        for step in results:
            status = "✅" if step["success"] else "❌"
            print(f"  {status} {step['action']}: {step.get('result', step.get('error', ''))[:80]}")

    elif args.action == "delete":
        if not args.name:
            print("Kullanım: aria workflow delete <isim>")
            sys.exit(1)
        ok = delete_workflow(args.name)
        print(f"{'✅ Silindi' if ok else '❌ Bulunamadı'}: {args.name}")


def _cmd_config(args: argparse.Namespace) -> None:
    """Konfigürasyon göster veya güncelle."""
    from ARIA.core.config import load_config, save_config
    cfg = load_config()

    if args.action == "show":
        print("\n⚙️  ARIA Konfigürasyonu\n" + "="*40)
        for field in ["model", "language", "tts_voice", "enable_tts",
                      "weather_city", "enable_speech_input", "notification_enabled",
                      "conversation_history_limit", "temperature", "cloud_fallback"]:
            print(f"  {field:<30} = {getattr(cfg, field, '?')}")
        print("="*40 + "\n")

    elif args.action == "set":
        if not args.key or args.value is None:
            print("Kullanım: aria config set <anahtar> <değer>")
            sys.exit(1)
        if not hasattr(cfg, args.key):
            print(f"❌ Bilinmeyen alan: {args.key}")
            sys.exit(1)
        # Tip dönüşümü
        current = getattr(cfg, args.key)
        if isinstance(current, bool):
            val = args.value.lower() in ("true", "1", "yes", "evet")
        elif isinstance(current, int):
            val = int(args.value)
        elif isinstance(current, float):
            val = float(args.value)
        else:
            val = args.value
        setattr(cfg, args.key, val)
        save_config(cfg)
        print(f"✅ {args.key} = {val}")


def _cmd_report(args: argparse.Namespace) -> None:
    """Rapor üret."""
    from ARIA.tools.weekly_report import generate_weekly_report, generate_daily_report
    if args.type == "weekly":
        r = generate_weekly_report(save=True)
        print(r["report"])
        if r["path"]:
            print(f"\n💾 Kaydedildi: {r['path']}")
    else:
        r = generate_daily_report(save=True)
        print(r["report"])
        if r["path"]:
            print(f"\n💾 Kaydedildi: {r['path']}")


def _cmd_ask(args: argparse.Namespace) -> None:
    """Tek seferlik soru-cevap (streaming olmadan)."""
    orchestrator = Orchestrator()
    if args.agent:
        from ARIA.core.registry import get_agent
        agent_cls = get_agent(args.agent)
        if agent_cls:
            print(agent_cls().handle(args.message))
            return
    print(orchestrator.dispatch(args.message))


# ── Parser ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aria",
        description="ARIA — Kişisel AI Asistan CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  aria doctor                          # Sistem sağlık kontrolü
  aria ask "günaydın"                  # Tek seferlik soru
  aria ask "araştır kuantum bilişim" --agent researcher
  aria memory search "geçen haftaki proje"
  aria memory add "Meriç'in doğum günü 15 Mart"
  aria workflow list
  aria workflow run sabah_rutini
  aria config show
  aria config set weather_city Istanbul
  aria config set model qwen2.5:14b
  aria report weekly
  aria serve --port 8000
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status (eski)
    s = sub.add_parser("status", help="Kısa sistem durumu")
    s.set_defaults(func=_cmd_status)

    # doctor (yeni)
    d = sub.add_parser("doctor", help="Kapsamlı sistem sağlık kontrolü")
    d.set_defaults(func=_cmd_doctor)

    # ask (yeni, chat'ten daha gelişmiş)
    ask = sub.add_parser("ask", help="Tek seferlik soru")
    ask.add_argument("message", help="Mesaj veya soru")
    ask.add_argument("--agent", "-a", default=None, help="Belirli ajan kullan")
    ask.set_defaults(func=_cmd_ask)

    # chat (eski)
    chat = sub.add_parser("chat", help="Tek seferlik sohbet (bkz: ask)")
    chat.add_argument("message")
    chat.set_defaults(func=_cmd_chat)

    # memory (yeni)
    mem = sub.add_parser("memory", help="Semantik hafıza işlemleri")
    mem_sub = mem.add_subparsers(dest="action", required=True)
    mem_search = mem_sub.add_parser("search", help="Hafızada ara")
    mem_search.add_argument("query", help="Arama sorgusu")
    mem_search.add_argument("--limit", "-n", type=int, default=5)
    mem_add = mem_sub.add_parser("add", help="Hafızaya not ekle")
    mem_add.add_argument("text", help="Eklenecek metin")
    mem_add.add_argument("--category", "-c", default="genel")
    mem_count = mem_sub.add_parser("count", help="Kayıt sayısını göster")
    mem.set_defaults(func=_cmd_memory)

    # workflow (yeni)
    wf = sub.add_parser("workflow", help="Workflow yönetimi")
    wf_sub = wf.add_subparsers(dest="action", required=True)
    wf_sub.add_parser("list", help="Workflow'ları listele")
    wf_run = wf_sub.add_parser("run", help="Workflow çalıştır")
    wf_run.add_argument("name", help="Workflow adı")
    wf_del = wf_sub.add_parser("delete", help="Workflow sil")
    wf_del.add_argument("name", help="Workflow adı")
    wf.set_defaults(func=_cmd_workflow)

    # config (yeni)
    cfg = sub.add_parser("config", help="Konfigürasyon yönetimi")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)
    cfg_sub.add_parser("show", help="Konfigürasyonu göster")
    cfg_set = cfg_sub.add_parser("set", help="Ayar değiştir")
    cfg_set.add_argument("key", help="Ayar adı (örn: model, weather_city)")
    cfg_set.add_argument("value", help="Yeni değer")
    cfg.set_defaults(func=_cmd_config)

    # report (yeni)
    rep = sub.add_parser("report", help="Rapor üret")
    rep.add_argument("type", choices=["weekly", "daily"], default="daily", nargs="?")
    rep.set_defaults(func=_cmd_report)

    # presets (eski)
    pre = sub.add_parser("presets", help="Preset işlemleri")
    pre.add_argument("action", choices=["list", "apply"])
    pre.add_argument("name", nargs="?", default="")
    pre.set_defaults(func=_cmd_presets)

    # serve (eski)
    srv = sub.add_parser("serve", help="API sunucusunu başlat")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)
    srv.set_defaults(func=_cmd_serve)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
