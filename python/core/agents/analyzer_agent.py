"""
Analyzer & Terminology Extraction Sub-Agent.
Scans document/game scripts, identifies genre, character personas,
and automatically extracts domain-specific glossary & lore terms.
"""

from typing import Any, Dict, List, Optional
from ..models import GlossaryItem, TranslationItem
from ..llm_client import UniversalLLMClient


class AnalyzerAgent:
    """Sub-agent responsible for pre-translation analysis & terminology glossary extraction."""

    def __init__(self, llm_client: UniversalLLMClient):
        self.llm_client = llm_client

    async def analyze_and_extract_glossary(
        self,
        items: List[TranslationItem],
        target_lang: str = "zh-CN",
        source_lang: str = "auto",
        max_samples: int = 60,
    ) -> Dict[str, Any]:
        """
        Analyzes sample text and returns genre, style guide, and a list of GlossaryItems.
        """
        if not items:
            return {"genre": "General", "style_guide": "", "glossary": []}

        # 1. Collect representative sample lines (head, middle, tail)
        samples = self._sample_items(items, max_samples)
        sample_text_block = "\n".join(
            f"[{item.speaker or 'Narrator'}]: {item.source_text}" for item in samples
        )

        # 2. Collect unique speaker names
        known_speakers = list({item.speaker for item in items if item.speaker})

        # 3. Prompt the analyzer LLM
        system_prompt = (
            "You are an expert Localization Director and World Lore Analyst specializing in game translation, "
            "literary works, and technical documents. Your task is to analyze the source text sample, "
            "identify the domain/genre, determine the appropriate translation tone, and extract key terms "
            "(character names, locations, skill/magic names, items, proper nouns, and recurring jargon)."
        )

        user_prompt = f"""
Please analyze the following text samples to prepare for translating from '{source_lang}' to '{target_lang}'.

Known Speakers / Characters: {', '.join(known_speakers) if known_speakers else 'None extracted explicitly'}

Sample Text:
---
{sample_text_block}
---

Output your findings in valid JSON format with the following structure:
{{
  "genre": "e.g. Fantasy RPG / Sci-Fi / Modern Casual / Technical Document",
  "style_guide": "Brief guidelines for translators (tone, character persona, formatting rules)",
  "character_personas": [
    {{"name": "Original Name", "target_name": "Standardized Translation", "persona": "Tone/trait description"}}
  ],
  "glossary": [
    {{"source": "Original Term / Character / Skill / Place", "target": "Accurate Translation", "category": "character|location|item|skill|term", "note": "brief explanation"}}
  ]
}}
"""

        try:
            raw_response = await self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                json_mode=True,
            )
            parsed = self.llm_client.parse_json(raw_response)

            glossary_items: List[GlossaryItem] = []
            for g in parsed.get("glossary", []):
                if isinstance(g, dict) and g.get("source") and g.get("target"):
                    glossary_items.append(
                        GlossaryItem(
                            source=str(g["source"]).strip(),
                            target=str(g["target"]).strip(),
                            category=str(g.get("category", "general")).strip(),
                            note=str(g.get("note", "")).strip(),
                        )
                    )

            # Also ensure character personas are included in glossary
            for c in parsed.get("character_personas", []):
                if isinstance(c, dict) and c.get("name") and c.get("target_name"):
                    src = str(c["name"]).strip()
                    tgt = str(c["target_name"]).strip()
                    if not any(g.source.lower() == src.lower() for g in glossary_items):
                        glossary_items.append(
                            GlossaryItem(
                                source=src,
                                target=tgt,
                                category="character",
                                note=str(c.get("persona", "")).strip(),
                            )
                        )

            return {
                "genre": parsed.get("genre", "General Localization"),
                "style_guide": parsed.get("style_guide", ""),
                "glossary": glossary_items,
            }

        except Exception as e:
            # Fallback if LLM fails
            print(f"[AnalyzerAgent] Warning: Analysis failed ({e}), using default fallback.")
            return {
                "genre": "General",
                "style_guide": "Maintain accurate, natural and fluent translation.",
                "glossary": [GlossaryItem(source=s, target=s, category="character") for s in known_speakers],
            }

    @staticmethod
    def _sample_items(items: List[TranslationItem], max_samples: int) -> List[TranslationItem]:
        total = len(items)
        if total <= max_samples:
            return items
        # Take beginning, middle, and end
        step = max(1, total // max_samples)
        sampled = items[0:total:step]
        return sampled[:max_samples]
