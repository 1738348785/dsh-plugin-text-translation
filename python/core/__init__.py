"""
Multi-Agent Translator Core Package.
"""

from .models import TranslationItem, GlossaryItem, PipelineEvent
from .tag_protector import TagProtector
from .extractor import UniversalExtractor
from .chunker import SmartBatcher, TranslationBatch
from .cache_manager import TranslationCacheManager

__all__ = [
    "TranslationItem",
    "GlossaryItem",
    "PipelineEvent",
    "TagProtector",
    "UniversalExtractor",
    "SmartBatcher",
    "TranslationBatch",
    "TranslationCacheManager",
]

# Optional LLM dependencies (only needed when running standalone API pipeline)
try:
    from .llm_client import UniversalLLMClient
    from .pipeline import MultiAgentTranslatorPipeline

    __all__.extend(["UniversalLLMClient", "MultiAgentTranslatorPipeline"])
except ImportError:
    pass
