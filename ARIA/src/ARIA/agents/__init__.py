"""Agents package — tüm ajanları import ederek @register_agent decorator'larını tetikler."""

from ARIA.agents.analyst import AnalystAgent
from ARIA.agents.brief import BriefAgent
from ARIA.agents.coder import CoderAgent
from ARIA.agents.memory import MemoryAgent
from ARIA.agents.monitor import MonitorAgent
from ARIA.agents.researcher import ResearcherAgent
from ARIA.agents.writer import WriterAgent
from ARIA.agents.planner import PlannerAgent
from ARIA.agents.terminal_agent import TerminalAgent
from ARIA.agents.research_agent import DeepResearchAgent
from ARIA.agents.chain import ChainAgent

# Tool'ları yükle — @register_tool decorator'larını tetikler
try:
    from ARIA.tools import (  # noqa: F401
        whatsapp_control, speech_input, code_runner,
        shell_runner, clipboard, file_index, rss_reader,
        log_analyzer, github_monitor, translator,
        podcast_summarizer, system_monitor, calendar_tools,
        alarm, reminders, spotify_control, screen_capture,
        mail_control, weather, notes, app_control,
        contacts, focus_mode, browser_control, spotlight_search,
        clipboard_history, document_qa, email_intelligence,
        wake_word, context_awareness, pomodoro, imessage,
        git_intelligence, weekly_report, health,
        voice_mode, meeting_assistant, obsidian, keychain,
        browser_automation, uptime_monitor, voice_journal,
        code_review, smart_clipboard, plugin_system, webhook,
    )
except Exception:
    pass

__all__ = [
    "AnalystAgent", "BriefAgent", "CoderAgent", "MemoryAgent",
    "MonitorAgent", "ResearcherAgent", "WriterAgent", "PlannerAgent",
    "TerminalAgent", "DeepResearchAgent", "ChainAgent",
]
