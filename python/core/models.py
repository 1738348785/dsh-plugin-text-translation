"""
Data models for Multi-Agent Translator.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TranslationItem(BaseModel):
    """Represents a single translatable line or unit."""
    id: str = Field(description="Unique identifier or line index")
    source_text: str = Field(description="Original source text")
    translated_text: Optional[str] = Field(default=None, description="Translated text")
    speaker: Optional[str] = Field(default=None, description="Character or speaker name if any")
    context: Optional[str] = Field(default=None, description="Surrounding context or notes")
    masked_text: Optional[str] = Field(default=None, description="Text with tags replaced by placeholders")
    tag_map: Dict[str, str] = Field(default_factory=dict, description="Mapping of placeholder -> original tag")
    status: str = Field(default="pending", description="Status: pending, translating, translated, reviewed, error")
    error: Optional[str] = Field(default=None, description="Error message if translation failed")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Format-specific metadata for reconstruction")


class GlossaryItem(BaseModel):
    """Represents a terminology or character name mapping."""
    source: str = Field(description="Source term or character name")
    target: str = Field(description="Target translation")
    category: str = Field(default="general", description="Category: character, location, item, skill, general")
    note: Optional[str] = Field(default="", description="Optional note or context")


class PipelineEvent(BaseModel):
    """Event emitted during pipeline execution for real-time UI/CLI updates."""
    phase: str = Field(description="Current phase name: extract, analyze, translate, review, assemble, complete, error")
    progress: float = Field(default=0.0, description="Progress percentage 0.0 ~ 100.0")
    total_items: int = Field(default=0)
    completed_items: int = Field(default=0)
    message: str = Field(default="")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Optional payload (e.g. newly translated items, glossary)")
