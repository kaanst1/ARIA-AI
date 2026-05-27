"""Terminal Agent — doğal dil komutlarını shell komutlarına çevirir."""

from __future__ import annotations

import json
import logging

from ARIA.core.engine import ARIAEngine
from ARIA.core.registry import register_agent

logger = logging.getLogger("aria.agents.terminal")

_TERMINAL_SYSTEM = """Sen ARIA'nın Terminal Ajanısın. Kullanıcının doğal dil isteğini güvenli shell komutuna çevirirsin.

Kullanabileceğin komutlar (whitelist):
ls, cat, find, grep, ps, df, du, pwd, echo, date, which, head, tail, wc, sort, uniq, cut, tr, env, uname, whoami, id, uptime

YASAKLI: rm, sudo, curl|bash, wget|sh, dd, mkfs, ve diğer tehlikeli komutlar.

Yanıt formatın:
{"command": "ls -la ~/Desktop", "explanation": "Masaüstünü listele"}

Sadece JSON döndür, başka hiçbir şey yazma."""


_INTERPRETER_SYSTEM = """Sen bir terminal çıktısı yorumlayıcısısın.
Kullanıcının sorusunu, çalıştırılan komutu ve çıktısını alıyorsun.
Çıktıyı Türkçe olarak kullanıcı dostu biçimde açıkla.
Sayısal değerleri, listeleri, durumları anlaşılır şekilde özetle."""


@register_agent("terminal")
class TerminalAgent:
    """Doğal dil → shell komutu → çıktı yorumlama."""

    def __init__(self) -> None:
        self.engine = ARIAEngine()

    def _nl_to_command(self, user_input: str) -> tuple[str, str]:
        """Doğal dili shell komutuna çevir."""
        messages = [
            {"role": "system", "content": _TERMINAL_SYSTEM},
            {"role": "user", "content": user_input},
        ]
        response = self.engine.chat(messages)

        # JSON parse
        try:
            clean = response.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].strip()
            if "{" in clean and "}" in clean:
                clean = clean[clean.index("{"):clean.rindex("}") + 1]
            data = json.loads(clean)
            return data.get("command", ""), data.get("explanation", "")
        except Exception:
            # Direkt komut çıkarmaya çalış
            lines = response.strip().split('\n')
            for line in lines:
                stripped = line.strip()
                if any(stripped.startswith(cmd) for cmd in
                       ["ls", "cat", "find", "grep", "ps", "df", "du", "pwd", "echo",
                        "date", "which", "head", "tail", "wc", "sort", "uname"]):
                    return stripped, "Komut çıkarıldı"
            return "", response

    def _interpret_output(self, user_input: str, command: str, output: dict) -> str:
        """Shell çıktısını yorumla."""
        stdout = output.get("stdout", "")
        stderr = output.get("stderr", "")
        exit_code = output.get("exit_code", 0)

        if exit_code != 0 and stderr:
            return f"Komut başarısız oldu.\nHata: {stderr}"

        if not stdout and not stderr:
            return f"Komut çalıştı ama çıktı üretmedi. (exit: {exit_code})"

        content = stdout or stderr
        messages = [
            {"role": "system", "content": _INTERPRETER_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Kullanıcı sorusu: {user_input}\n"
                    f"Çalıştırılan komut: {command}\n"
                    f"Çıktı:\n{content[:2000]}"
                ),
            },
        ]
        return self.engine.chat(messages)

    def handle(self, user_input: str) -> str:
        """Doğal dil komutunu işle."""
        from ARIA.tools.shell_runner import run_shell

        command, explanation = self._nl_to_command(user_input)

        if not command:
            return f"Komut oluşturulamadı. Lütfen daha spesifik belirtin.\nLLM yanıtı: {explanation}"

        logger.info("Terminal komutu: %s", command)

        # Komutu çalıştır
        output = run_shell(command)

        # Güvenlik reddi
        if output.get("error") == "Güvenlik ihlali":
            return f"Güvenlik: Bu komut çalıştırılamaz.\n{output.get('stderr', '')}"

        # Çıktıyı yorumla
        return self._interpret_output(user_input, command, output)
