"""
Multi-Agent Translation Pipeline Orchestrator.
Coordinates Extractor, Analyzer Agent, Batch Chunker, Concurrent Translator Workers,
Reviewer Agent, Assembler Agent, and Persistent Cache Manager.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .models import GlossaryItem, PipelineEvent, TranslationItem
from .tag_protector import TagProtector
from .extractor import UniversalExtractor
from .chunker import SmartBatcher, TranslationBatch
from .llm_client import UniversalLLMClient
from .cache_manager import TranslationCacheManager
from .agents.analyzer_agent import AnalyzerAgent
from .agents.translator_agent import TranslatorAgent
from .agents.reviewer_agent import ReviewerAgent
from .agents.assembler_agent import AssemblerAgent


class MultiAgentTranslatorPipeline:
    """Master pipeline executing multi-agent extraction and translation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        concurrency: int = 5,
        batch_size: int = 20,
        enable_reviewer: bool = True,
        enable_glossary: bool = True,
        enable_tag_protection: bool = True,
        cache_dir: Optional[str] = None,
    ):
        self.llm_client = UniversalLLMClient(api_key=api_key, base_url=base_url, model_name=model_name)
        self.concurrency = max(1, concurrency)
        self.batch_size = max(1, batch_size)
        self.enable_reviewer = enable_reviewer
        self.enable_glossary = enable_glossary
        self.enable_tag_protection = enable_tag_protection
        self.cache_manager = TranslationCacheManager(cache_dir=cache_dir)

        # Initialize Sub-Agents
        self.analyzer_agent = AnalyzerAgent(self.llm_client)
        self.translator_agent = TranslatorAgent(self.llm_client)
        self.reviewer_agent = ReviewerAgent(self.llm_client)
        self.assembler_agent = AssemblerAgent()

    async def run(
        self,
        file_path_or_text: Union[str, Path],
        is_file: bool = True,
        target_lang: str = "zh-CN",
        source_lang: str = "auto",
        custom_glossary: Optional[List[GlossaryItem]] = None,
        output_file: Optional[Union[str, Path]] = None,
        event_callback: Optional[Callable[[PipelineEvent], Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes complete multi-agent extraction, translation, review, and assembly.
        """
        start_time = time.time()

        async def emit(phase: str, progress: float, msg: str, data: Optional[Dict] = None):
            if event_callback:
                evt = PipelineEvent(
                    phase=phase,
                    progress=progress,
                    total_items=len(items) if "items" in locals() else 0,
                    completed_items=completed_count if "completed_count" in locals() else 0,
                    message=msg,
                    data=data,
                )
                if asyncio.iscoroutinefunction(event_callback):
                    await event_callback(evt)
                else:
                    event_callback(evt)

        # =========================================================================
        # Phase 1: Text Extraction & Tag Protection
        # =========================================================================
        await emit("extract", 5.0, "Extracting text and applying game tag protection...")

        if is_file:
            path_obj = Path(file_path_or_text)
            project_id = path_obj.name
            items, format_type, file_context = UniversalExtractor.extract_from_file(
                path_obj, mask_tags=self.enable_tag_protection
            )
        else:
            project_id = f"text_{hash(file_path_or_text)}"
            items, format_type, file_context = UniversalExtractor.extract_from_text(
                str(file_path_or_text), mask_tags=self.enable_tag_protection
            )

        total_items = len(items)
        if total_items == 0:
            await emit("complete", 100.0, "No translatable text found.")
            return {"items": [], "glossary": [], "output": "", "format": format_type}

        # Check existing checkpoint for resumption
        cached_items = self.cache_manager.load_checkpoint(project_id)
        if cached_items and len(cached_items) == total_items:
            # Rehydrate status from checkpoint
            for i, c_item in enumerate(cached_items):
                if c_item.translated_text:
                    items[i].translated_text = c_item.translated_text
                    items[i].status = c_item.status

        # =========================================================================
        # Phase 2: Analyzer Sub-Agent (Glossary & World Lore)
        # =========================================================================
        glossary: List[GlossaryItem] = list(custom_glossary or [])
        style_guide = ""

        if self.enable_glossary:
            await emit("analyze", 15.0, "Sub-Agent 1 (Analyzer): Scanning text & extracting character/lore glossary...")
            analysis = await self.analyzer_agent.analyze_and_extract_glossary(
                items=items,
                target_lang=target_lang,
                source_lang=source_lang,
            )
            auto_glossary = analysis.get("glossary", [])
            style_guide = analysis.get("style_guide", "")

            # Merge auto glossary with custom glossary (custom has priority)
            existing_sources = {g.source.lower() for g in glossary}
            for auto_g in auto_glossary:
                if auto_g.source.lower() not in existing_sources:
                    glossary.append(auto_g)

            await emit(
                "analyze",
                20.0,
                f"Analyzer Agent identified domain: {analysis.get('genre')} with {len(glossary)} glossary terms.",
                {"glossary": [g.model_dump() for g in glossary]},
            )

        # =========================================================================
        # Phase 3: Smart Chunking & Dispatching
        # =========================================================================
        await emit("chunk", 25.0, "Splitting into context-aware batches for parallel workers...")
        batches = SmartBatcher.create_batches(items, batch_size=self.batch_size)
        total_batches = len(batches)

        # =========================================================================
        # Phase 4: Parallel Translation Sub-Agents Pool
        # =========================================================================
        await emit("translate", 30.0, f"Spawning {self.concurrency} parallel translation sub-agents...")

        semaphore = asyncio.Semaphore(self.concurrency)
        completed_batches = 0
        completed_count = sum(1 for it in items if it.status in ("translated", "reviewed"))

        async def worker_task(batch: TranslationBatch):
            nonlocal completed_batches, completed_count
            async with semaphore:
                # Check if batch is already completed from cache
                needed_translation = False
                for it in batch.items:
                    if not it.translated_text:
                        # Check global memory cache
                        cached = self.cache_manager.get_cached_translation(it.source_text, target_lang, it.speaker)
                        if cached:
                            it.translated_text = cached
                            it.status = "cached"
                            completed_count += 1
                        else:
                            needed_translation = True

                if needed_translation:
                    translated_items = await self.translator_agent.translate_batch(
                        batch=batch,
                        target_lang=target_lang,
                        source_lang=source_lang,
                        glossary=glossary,
                        style_guide=style_guide,
                    )
                    for item in translated_items:
                        if item.translated_text:
                            self.cache_manager.cache_translation(item.source_text, target_lang, item.translated_text, item.speaker)
                            completed_count += 1

                completed_batches += 1
                prog = 30.0 + (completed_batches / total_batches) * 50.0  # 30% -> 80%
                await emit(
                    "translate",
                    prog,
                    f"Translated batch {completed_batches}/{total_batches} ({completed_count}/{total_items} lines)",
                    {"batch_index": batch.batch_index, "items": [it.model_dump() for it in batch.items]},
                )

                # Save checkpoint after each batch
                self.cache_manager.save_checkpoint(project_id, items)

        tasks = [worker_task(b) for b in batches]
        await asyncio.gather(*tasks)

        # =========================================================================
        # Phase 5: Reviewer & Polish Sub-Agent
        # =========================================================================
        if self.enable_reviewer:
            await emit("review", 85.0, "Sub-Agent 3 (Reviewer): Verifying tag integrity and term consistency...")
            for it in items:
                self.reviewer_agent.review_and_repair_tags(it)
                self.reviewer_agent.enforce_glossary_terms(it, glossary)

        # =========================================================================
        # Phase 6: Document Assembler & Export
        # =========================================================================
        await emit("assemble", 95.0, f"Reconstructing final output format ({format_type})...")
        final_output = self.assembler_agent.assemble_results(
            items=items,
            format_type=format_type,
            file_context=file_context,
            output_path=output_file,
        )

        elapsed = time.time() - start_time
        await emit(
            "complete",
            100.0,
            f"Translation finished successfully in {elapsed:.1f}s ({total_items} items, {len(glossary)} terms).",
            {"output": final_output if isinstance(final_output, str) and len(final_output) < 50000 else "Output generated"},
        )

        return {
            "project_id": project_id,
            "total_items": total_items,
            "format": format_type,
            "glossary": [g.model_dump() for g in glossary],
            "items": [it.model_dump() for it in items],
            "output": final_output,
            "elapsed_seconds": round(elapsed, 2),
        }
