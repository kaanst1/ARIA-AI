"""ARIA command-line interface."""

from __future__ import annotations

import argparse
from ARIA.core.engine import ARIAEngine
from ARIA.orchestrator.router import Orchestrator
from ARIA.core.presets import list_presets, apply_preset


def _cmd_status(_args: argparse.Namespace) -> None:
    engine = ARIAEngine()
    print(engine.doctor())


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aria", description="ARIA CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Sistem durumunu goster")
    status.set_defaults(func=_cmd_status)

    chat = sub.add_parser("chat", help="Tek seferlik sohbet")
    chat.add_argument("message", help="Mesaj")
    chat.set_defaults(func=_cmd_chat)

    presets = sub.add_parser("presets", help="Preset islemleri")
    presets.add_argument("action", choices=["list", "apply"])
    presets.add_argument("name", nargs="?", default="")
    presets.set_defaults(func=_cmd_presets)

    serve = sub.add_parser("serve", help="API sunucusunu baslat")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "presets" and args.action == "apply" and not args.name:
        parser.error("presets apply icin isim gerekli")
    args.func(args)


if __name__ == "__main__":
    main()
