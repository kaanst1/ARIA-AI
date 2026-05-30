"""Agent Zinciri — tek komutla birden fazla ajanı sırayla çalıştır."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from ARIA.core.engine import ARIAEngine
from ARIA.core.registry import register_agent

logger = logging.getLogger("aria.agents.chain")

_CHAIN_SYSTEM = """Sen ARIA'nın Zincir Planlayıcısısın.
Kullanıcının isteğini analiz et ve hangi ajanların hangi sırayla çalışması gerektiğini belirle.

Mevcut ajanlar:
- researcher: web araştırması, haber toplama, bilgi arama
- deep_research: kapsamlı çok kaynaklı araştırma
- analyst: veri ve dosya analizi
- writer: makale, rapor, tweet, içerik üretme
- coder: kod yazma ve debug
- brief: sabah özeti
- memory: hafızaya kayıt ve sorgulama
- planner: karmaşık görev planı
- terminal: shell komutları
- chat: genel yanıt, özetleme, format değiştirme

SADECE şu JSON formatında cevap ver (başka hiçbir şey yazma):
{
  "chain": [
    {"agent": "ajan_adı", "task": "bu ajanın yapacağı görev", "use_previous": true/false},
    ...
  ],
  "description": "Zincirin kısa açıklaması"
}

use_previous=true ise önceki ajanın çıktısı bu ajana girdi olarak verilir."""


@dataclass
class ChainStep:
    agent: str
    task: str
    use_previous: bool = False
    result: str = ""
    success: bool = False


@dataclass
class ChainResult:
    steps: list[ChainStep] = field(default_factory=list)
    final_output: str = ""
    description: str = ""
    success: bool = False


def _plan_chain(user_input: str, engine: ARIAEngine) -> Optional[list[dict]]:
    """LLM ile zincir planı üret."""
    messages = [
        {"role": "system", "content": _CHAIN_SYSTEM},
        {"role": "user", "content": f"Görev: {user_input}"},
    ]
    try:
        raw = engine.chat(messages)
        clean = raw.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].strip()
        if "{" in clean:
            clean = clean[clean.index("{"):clean.rindex("}") + 1]
        data = json.loads(clean)
        return data
    except Exception as exc:
        logger.warning("Zincir planı parse edilemedi: %s", exc)
        return None


def _run_agent(agent_name: str, task: str) -> str:
    """Tek bir ajanı çalıştır."""
    from ARIA.core.registry import get_agent
    agent_cls = get_agent(agent_name)
    if agent_cls:
        try:
            return agent_cls().handle(task)
        except Exception as exc:
            logger.warning("Ajan %s hatası: %s", agent_name, exc)
            return f"[Hata: {exc}]"
    # Bilinmeyen ajan → chat
    from ARIA.core.engine import ARIAEngine
    return ARIAEngine().chat([{"role": "user", "content": task}])


def run_chain(user_input: str) -> ChainResult:
    """Kullanıcı girdisini analiz et, ajan zinciri planla ve çalıştır."""
    engine = ARIAEngine()
    result = ChainResult()

    plan_data = _plan_chain(user_input, engine)
    if not plan_data:
        # Fallback: tek adım
        plan_data = {
            "chain": [{"agent": "chat", "task": user_input, "use_previous": False}],
            "description": "Tekil yanıt",
        }

    result.description = plan_data.get("description", "")
    chain = plan_data.get("chain", [])
    logger.info("Zincir planı: %s", [s.get("agent") for s in chain])

    previous_output = ""
    for i, step_data in enumerate(chain):
        agent = step_data.get("agent", "chat")
        task = step_data.get("task", user_input)
        use_prev = step_data.get("use_previous", False)

        # Önceki çıktıyı göreve ekle
        if use_prev and previous_output:
            task = f"{task}\n\nÖnceki adım çıktısı:\n{previous_output}"

        logger.info("[%d/%d] Ajan: %s", i + 1, len(chain), agent)
        step = ChainStep(agent=agent, task=task, use_previous=use_prev)

        step.result = _run_agent(agent, task)
        step.success = not step.result.startswith("[Hata:")
        previous_output = step.result
        result.steps.append(step)

    result.final_output = previous_output
    result.success = any(s.success for s in result.steps)
    return result


@register_agent("chain")
class ChainAgent:
    """Çok-ajan zinciri yürüten orkestratör."""

    def handle(self, user_input: str) -> str:
        result = run_chain(user_input)
        if len(result.steps) == 1:
            return result.final_output

        # Çok adımlı zincir → adımları özetle
        header = f"**{result.description}** ({len(result.steps)} adım)\n\n"
        steps_summary = "\n\n".join(
            f"**{i+1}. {s.agent.upper()}:** {s.result[:600]}"
            for i, s in enumerate(result.steps)
        )
        return header + steps_summary
