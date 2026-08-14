"""
Smart Context-Aware Chunker and Batcher.
Groups translatable items into optimal batches while maintaining sliding
conversation context (preceding/succeeding dialogue) to eliminate context loss.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .models import TranslationItem


class TranslationBatch(BaseModel):
    """A batch of items with sliding conversational context."""
    batch_index: int
    items: List[TranslationItem]
    preceding_context: List[str] = Field(default_factory=list, description="Preceding 2-4 lines for context awareness")
    succeeding_context: List[str] = Field(default_factory=list, description="Following 1-2 lines hint")
    speakers: List[str] = Field(default_factory=list, description="Speakers present in this batch")


class SmartBatcher:
    """Chunks translation items into context-rich batches."""

    @classmethod
    def create_batches(
        cls,
        items: List[TranslationItem],
        batch_size: int = 20,
        context_window_lines: int = 3,
    ) -> List[TranslationBatch]:
        """
        Splits items into batches and attaches preceding/succeeding context lines.
        """
        if not items:
            return []

        batches: List[TranslationBatch] = []
        total = len(items)

        for i in range(0, total, batch_size):
            batch_items = items[i : i + batch_size]
            b_idx = i // batch_size + 1

            # Preceding context lines (from items before this batch)
            pre_start = max(0, i - context_window_lines)
            preceding = []
            for item in items[pre_start:i]:
                prefix = f"[{item.speaker}] " if item.speaker else ""
                preceding.append(f"{prefix}{item.source_text}")

            # Succeeding context lines
            post_end = min(total, i + batch_size + context_window_lines)
            succeeding = []
            for item in items[i + batch_size : post_end]:
                prefix = f"[{item.speaker}] " if item.speaker else ""
                succeeding.append(f"{prefix}{item.source_text}")

            # Collect unique speakers in this batch
            speakers = list({item.speaker for item in batch_items if item.speaker})

            batches.append(
                TranslationBatch(
                    batch_index=b_idx,
                    items=batch_items,
                    preceding_context=preceding,
                    succeeding_context=succeeding,
                    speakers=speakers,
                )
            )

        return batches
