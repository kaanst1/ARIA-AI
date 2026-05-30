"""Plugin Sistemi — YAML veya Python ile yeni araç/komut tanımla."""

from __future__ import annotations

import importlib.util
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from ARIA.core.registry import register_tool, TOOL_REGISTRY

logger = logging.getLogger("aria.tools.plugins")

_PLUGINS_DIR = Path.home() / ".aria" / "plugins"
_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

_EXAMPLE_YAML = """# ARIA Plugin Örneği
name: ornek_plugin
version: "1.0"
description: Örnek plugin — mevcut komutları zincirle
author: "Sen"

commands:
  - name: haber_ve_ozet
    description: Haberleri araştır ve özetle
    steps:
      - agent: researcher
        message: "son teknoloji haberleri"
      - agent: writer
        message: "yukarıdaki haberleri 5 madde olarak özetle: {previous}"
"""


def _load_yaml_plugins() -> list[dict]:
    """~/.aria/plugins/ altındaki YAML plugin'leri yükle."""
    plugins = []
    for path in _PLUGINS_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text())
            if isinstance(data, dict) and data.get("name"):
                data["_file"] = str(path)
                plugins.append(data)
        except Exception as exc:
            logger.warning("Plugin yüklenemedi (%s): %s", path.name, exc)
    return plugins


def _load_python_plugins() -> list[str]:
    """~/.aria/plugins/ altındaki Python plugin'leri yükle ve register et."""
    loaded = []
    for path in _PLUGINS_DIR.glob("*.py"):
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                loaded.append(path.stem)
                logger.info("Python plugin yüklendi: %s", path.stem)
        except Exception as exc:
            logger.warning("Python plugin yüklenemedi (%s): %s", path.name, exc)
    return loaded


def _run_yaml_command(command: dict, user_input: str = "") -> str:
    """YAML komutunu adım adım çalıştır."""
    from ARIA.core.registry import get_agent
    previous = user_input
    results = []

    for step in command.get("steps", []):
        agent_name = step.get("agent", "chat")
        message = step.get("message", user_input)
        message = message.replace("{previous}", previous).replace("{input}", user_input)

        agent_cls = get_agent(agent_name)
        if agent_cls:
            result = agent_cls().handle(message)
        else:
            from ARIA.core.engine import ARIAEngine
            result = ARIAEngine().chat([{"role": "user", "content": message}])

        previous = result
        results.append(f"**{agent_name.upper()}:** {result[:300]}")

    return "\n\n".join(results) if len(results) > 1 else (results[0] if results else "")


@register_tool("plugin_list")
def plugin_list() -> dict:
    """Yüklü plugin'leri listele.

    Returns:
        {'plugins': list[dict], 'count': int}
    """
    yaml_plugins = _load_yaml_plugins()
    python_plugins = [{"name": p, "type": "python"} for p in _PLUGINS_DIR.glob("*.py")]

    plugins = []
    for p in yaml_plugins:
        cmds = [c["name"] for c in p.get("commands", [])]
        plugins.append({
            "name": p["name"],
            "description": p.get("description", ""),
            "version": p.get("version", ""),
            "type": "yaml",
            "commands": cmds,
            "file": p.get("_file", ""),
        })
    for p in [f.stem for f in _PLUGINS_DIR.glob("*.py")]:
        plugins.append({"name": p, "type": "python", "commands": []})

    return {"plugins": plugins, "count": len(plugins), "success": True}


@register_tool("plugin_run")
def plugin_run(plugin_name: str, command_name: str, user_input: str = "") -> dict:
    """YAML plugin komutu çalıştır.

    Args:
        plugin_name: Plugin adı
        command_name: Komut adı
        user_input: Kullanıcı girdisi

    Returns:
        {'result': str}
    """
    plugins = _load_yaml_plugins()
    plugin = next((p for p in plugins if p["name"] == plugin_name), None)
    if not plugin:
        return {"success": False, "error": f"Plugin bulunamadı: {plugin_name}"}

    commands = plugin.get("commands", [])
    command = next((c for c in commands if c["name"] == command_name), None)
    if not command:
        return {"success": False, "error": f"Komut bulunamadı: {command_name}"}

    result = _run_yaml_command(command, user_input)
    return {"success": True, "result": result, "plugin": plugin_name, "command": command_name}


@register_tool("plugin_install")
def plugin_install(yaml_content: str) -> dict:
    """YAML içeriğinden plugin yükle.

    Args:
        yaml_content: Plugin YAML içeriği

    Returns:
        {'success': bool, 'name': str, 'commands': list}
    """
    try:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict) or not data.get("name"):
            return {"success": False, "error": "Geçersiz plugin formatı — 'name' alanı gerekli"}

        name = data["name"].replace(" ", "_")
        path = _PLUGINS_DIR / f"{name}.yaml"
        path.write_text(yaml_content, encoding="utf-8")
        cmds = [c["name"] for c in data.get("commands", [])]
        logger.info("Plugin yüklendi: %s (%d komut)", name, len(cmds))
        return {"success": True, "name": name, "commands": cmds, "file": str(path)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@register_tool("plugin_create_example")
def plugin_create_example() -> dict:
    """Örnek plugin YAML dosyası oluştur.

    Returns:
        {'path': str, 'content': str}
    """
    path = _PLUGINS_DIR / "ornek_plugin.yaml"
    path.write_text(_EXAMPLE_YAML, encoding="utf-8")
    return {
        "success": True,
        "path": str(path),
        "content": _EXAMPLE_YAML,
        "message": f"Örnek plugin oluşturuldu: {path}\nDüzenleyip `plugin_install` ile yükle.",
    }


@register_tool("plugin_delete")
def plugin_delete(plugin_name: str) -> dict:
    """Plugin'i sil.

    Returns:
        {'success': bool}
    """
    path = _PLUGINS_DIR / f"{plugin_name}.yaml"
    py_path = _PLUGINS_DIR / f"{plugin_name}.py"

    deleted = []
    if path.exists():
        path.unlink()
        deleted.append(str(path))
    if py_path.exists():
        py_path.unlink()
        deleted.append(str(py_path))

    if deleted:
        return {"success": True, "deleted": deleted}
    return {"success": False, "error": f"Plugin bulunamadı: {plugin_name}"}


def load_all_plugins() -> int:
    """Tüm plugin'leri yükle — API startup'ta çağrılır."""
    yaml_count = len(_load_yaml_plugins())
    py_count = len(_load_python_plugins())
    total = yaml_count + py_count
    if total:
        logger.info("%d plugin yüklendi (%d YAML, %d Python)", total, yaml_count, py_count)
    return total
