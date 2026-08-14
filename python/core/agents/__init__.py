"""
Multi-Agent Translation Sub-Agents Package.
"""

from .assembler_agent import AssemblerAgent

__all__ = ["AssemblerAgent"]

# Optional LLM sub-agents (only needed when running standalone API pipeline)
try:
    from .analyzer_agent import AnalyzerAgent
    from .translator_agent import TranslatorAgent
    from .reviewer_agent import ReviewerAgent

    __all__.extend(["AnalyzerAgent", "TranslatorAgent", "ReviewerAgent"])
except ImportError:
    pass
