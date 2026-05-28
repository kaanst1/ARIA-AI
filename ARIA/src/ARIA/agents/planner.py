"""ReAct Planning Agent — çok adımlı görev planlama ve yürütme."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from ARIA.core.engine import ARIAEngine
from ARIA.core.registry import register_agent, TOOL_REGISTRY

logger = logging.getLogger("aria.agents.planner")

_PLANNER_SYSTEM = """Sen ARIA'nın Planlama Ajanısın. ReAct döngüsü kullanarak karmaşık görevleri adım adım çözersin.

Her adımda şu formatı kullan:

Thought: [Ne yapman gerektiğini düşün]
Action: [{"tool": "tool_adı", "args": {"param1": "değer1", ...}}]
Observation: [Tool sonucu buraya gelecek]

Eğer görev tamamlandıysa:
Final Answer: [Kapsamlı sonuç açıklaması]

Mevcut araçlar:
{tool_list}

KURALLAR:
1. Her Action'dan sonra Observation'ı bekle
2. Maksimum 5 iterasyon
3. Action MUTLAKA geçerli JSON olmalı
4. Bilinmeyen tool kullanma
5. Final Answer ile bitir
"""


def _format_tool_list() -> str:
    """Mevcut tool'ları listele."""
    tools = list(TOOL_REGISTRY.keys())
    return ", ".join(tools) if tools else "(tool yok)"


def _parse_action(text: str) -> Optional[dict]:
    """Action: {...} formatından JSON çıkar."""
    # Action: satırını bul
    action_match = re.search(r'Action:\s*(\{.+?\})', text, re.DOTALL)
    if not action_match:
        return None
    try:
        return json.loads(action_match.group(1))
    except json.JSONDecodeError:
        # Tek satır JSON dene
        lines = text.split('\n')
        for line in lines:
            if 'Action:' in line:
                json_part = line.split('Action:', 1)[1].strip()
                try:
                    return json.loads(json_part)
                except Exception:
                    pass
    return None


def _call_tool(tool_name: str, args: dict) -> str:
    """Tool'u çağır ve sonucu string olarak döndür."""
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if not tool_fn:
        return f"Hata: '{tool_name}' tool'u bulunamadı. Mevcut: {list(TOOL_REGISTRY.keys())[:10]}"

    try:
        result = tool_fn(**args) if args else tool_fn()
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, indent=2)[:2000]
        return str(result)[:2000]
    except Exception as exc:
        return f"Tool hatası ({tool_name}): {exc}"


@register_agent("planner")
class PlannerAgent:
    """ReAct döngüsü ile çok adımlı görev planlama ve yürütme."""

    def __init__(self) -> None:
        self.engine = ARIAEngine()
        self.max_iterations = 5

    def handle(self, user_input: str) -> str:
        """Kullanıcının görevini ReAct döngüsü ile çöz."""
        tool_list = _format_tool_list()
        system_prompt = _PLANNER_SYSTEM.format(tool_list=tool_list)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Görev: {user_input}\n\nBaşla:"},
        ]

        full_trace = []
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            logger.info("PlannerAgent iterasyon %d", iteration)

            # LLM'den Thought/Action al
            response = self.engine.chat(messages)
            full_trace.append(response)

            # Final Answer kontrolü
            if "Final Answer:" in response:
                final_match = re.search(r'Final Answer:\s*(.*)', response, re.DOTALL)
                if final_match:
                    return final_match.group(1).strip()
                return response

            # Action parse et
            action = _parse_action(response)
            if action is None:
                # Action bulunamadı — doğrudan cevap döndür
                return response

            tool_name = action.get("tool", "")
            tool_args = action.get("args", {})

            # Tool çağır
            observation = _call_tool(tool_name, tool_args)
            logger.info("Tool: %s → %s...", tool_name, observation[:100])

            # Mesajlara ekle
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"Observation: {observation}\n\nDevam et veya Final Answer yaz:"
            })

        # Max iterasyon aşıldı
        summary = f"Planlama tamamlandı ({iteration} adım):\n\n"
        summary += "\n---\n".join(full_trace[-3:])
        return summary
