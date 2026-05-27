"""Agents package — tüm ajanları import ederek @register_agent decorator'larını tetikler."""

from ARIA.agents.analyst import AnalystAgent
from ARIA.agents.brief import BriefAgent
from ARIA.agents.coder import CoderAgent
from ARIA.agents.memory import MemoryAgent
from ARIA.agents.monitor import MonitorAgent
from ARIA.agents.researcher import ResearcherAgent
from ARIA.agents.writer import WriterAgent

__all__ = [
    "AnalystAgent",
    "BriefAgent",
    "CoderAgent",
    "MemoryAgent",
    "MonitorAgent",
    "ResearcherAgent",
    "WriterAgent",
]
