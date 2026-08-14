"""
Parallel Translation Sub-Agent Worker.
Translates individual batches with tag protection, glossary enforcement,
context awareness, and speaker tone adaptation.
"""

from typing import Dict, List, Optional
from ..models import GlossaryItem, TranslationItem
from ..chunker import TranslationBatch
from ..llm_client import UniversalLLMClient


class TranslatorAgent:
    """Sub-agent worker responsible for translating a single batch of items."""

    def __init__(self, llm_client: UniversalLLMClient):
        self.llm_client = llm_client

    async def translate_batch(
        self,
        batch: TranslationBatch,
        target_lang: str = "zh-CN",
        source_lang: str = "auto",
        glossary: Optional[List[GlossaryItem]] = None,
        style_guide: str = "",
    ) -> List[TranslationItem]:
        """
        Translates all items in the batch concurrently or via structured JSON request.
        """
        if not batch.items:
            return []

        # 1. Format Glossary for prompt
        glossary_text = ""
        if glossary:
            # Filter relevant glossary items or top items
            g_lines = [f"- {g.source} => {g.target} ({g.category})" for g in glossary[:50]]
            glossary_text = "\n".join(g_lines)

        # 2. Format Preceding Context
        context_text = ""
        if batch.preceding_context:
            context_text = "Preceding Dialogue History:\n" + "\n".join(f"> {line}" for line in batch.preceding_context)

        # 3. Format Items to translate
        items_payload = []
        for item in batch.items:
            entry = {
                "id": str(item.id),
                "text": item.masked_text or item.source_text,
            }
            if item.speaker:
                entry["speaker"] = item.speaker
            items_payload.append(entry)

        # 4. Construct System Prompt
        system_prompt = f"""You are a master localization expert specializing in translating into {target_lang}.
Your goal is to produce natural, fluent, and highly immersive localization while strictly respecting game formatting constraints.

CRITICAL RULES:
1. TAG PRESERVATION: You will see placeholders like `⟦TAG_0⟧`, `⟦TAG_1⟧`, etc. You MUST KEEP THEM 100% INTACT.
   - NEVER alter, remove, translate, or split these placeholders.
   - Place them in natural corresponding positions in the translated sentence.
2. GLOSSARY CONFORMANCE: Strictly translate terms according to the Glossary table below.
3. CONVERSATION TONE: Use the context history and speaker roles to match natural speech rhythms, politeness levels, and character personalities.
4. OUTPUT SPECIFICATION: You MUST respond ONLY with a valid JSON array of objects:
   [
     {{"id": "...", "text": "Translated text with ⟦TAG_X⟧ preserved"}}
   ]
"""

        user_prompt = f"""
Source Language: {source_lang}
Target Language: {target_lang}

{f"Style Guide / Tone: {style_guide}" if style_guide else ""}

{f"Glossary / Proper Nouns Reference:\n{glossary_text}\n" if glossary_text else ""}

{context_text}

Lines to Translate:
```json
{self._to_json_str(items_payload)}
```

Please output the translation JSON array:
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
            
            # Convert parsed list or dict into lookup
            trans_lookup: Dict[str, str] = {}
            if isinstance(parsed, list):
                for obj in parsed:
                    if isinstance(obj, dict) and "id" in obj and "text" in obj:
                        trans_lookup[str(obj["id"])] = str(obj["text"])
            elif isinstance(parsed, dict):
                # Could be {"translations": [...]} or {"id": "text"}
                if "translations" in parsed and isinstance(parsed["translations"], list):
                    for obj in parsed["translations"]:
                        if isinstance(obj, dict) and "id" in obj and "text" in obj:
                            trans_lookup[str(obj["id"])] = str(obj["text"])
                else:
                    for k, v in parsed.items():
                        trans_lookup[str(k)] = str(v)

            # Assign translations to items
            result_items: List[TranslationItem] = []
            for item in batch.items:
                translated = trans_lookup.get(str(item.id))
                if translated is None:
                    # Fallback to source if missing
                    item.translated_text = item.masked_text or item.source_text
                    item.status = "error"
                    item.error = "Missing translation in LLM response"
                else:
                    item.translated_text = translated
                    item.status = "translated"
                result_items.append(item)

            return result_items

        except Exception as e:
            # Fallback on batch failure
            print(f"[TranslatorAgent] Error on batch {batch.batch_index}: {e}")
            for item in batch.items:
                item.translated_text = item.masked_text or item.source_text
                item.status = "error"
                item.error = str(e)
            return batch.items

    @staticmethod
    def _to_json_str(obj: any) -> str:
        import json
        return json.dumps(obj, ensure_ascii=False, indent=2)
