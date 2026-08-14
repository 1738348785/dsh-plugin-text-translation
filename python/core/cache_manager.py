"""
Persistent Checkpoint and Cache Manager.
Enables instant zero-loss resume for large game scripts (10,000+ lines),
avoiding duplicate API calls and token waste.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

from .models import TranslationItem


class TranslationCacheManager:
    """Manages disk-based translation cache and project checkpoints."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir or Path(__file__).parent.parent / ".cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache: Dict[str, str] = {}
        self._load_global_cache()

    def _get_global_cache_file(self) -> Path:
        return self.cache_dir / "global_translations.json"

    def _get_project_checkpoint_file(self, project_id: str) -> Path:
        safe_id = re_clean = "".join(c if c.isalnum() or c in "._-" else "_" for c in project_id)
        return self.cache_dir / f"checkpoint_{safe_id}.json"

    def _load_global_cache(self):
        cache_file = self._get_global_cache_file()
        if cache_file.exists():
            try:
                self.memory_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                self.memory_cache = {}

    def _save_global_cache(self):
        cache_file = self._get_global_cache_file()
        try:
            cache_file.write_text(json.dumps(self.memory_cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def compute_key(source_text: str, target_lang: str, speaker: Optional[str] = None) -> str:
        raw = f"{speaker or ''}:::{target_lang}:::{source_text.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_cached_translation(self, source_text: str, target_lang: str, speaker: Optional[str] = None) -> Optional[str]:
        key = self.compute_key(source_text, target_lang, speaker)
        return self.memory_cache.get(key)

    def cache_translation(self, source_text: str, target_lang: str, translated_text: str, speaker: Optional[str] = None):
        if not source_text or not translated_text:
            return
        key = self.compute_key(source_text, target_lang, speaker)
        self.memory_cache[key] = translated_text
        self._save_global_cache()

    def save_checkpoint(self, project_id: str, items: List[TranslationItem], metadata: Optional[Dict] = None):
        """Saves current state of all translation items for a specific project/file."""
        ckpt_file = self._get_project_checkpoint_file(project_id)
        data = {
            "project_id": project_id,
            "metadata": metadata or {},
            "items": [item.model_dump() for item in items],
        }
        try:
            ckpt_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[CacheManager] Warning: failed to save checkpoint: {e}")

    def load_checkpoint(self, project_id: str) -> Optional[List[TranslationItem]]:
        """Loads items from existing checkpoint if available."""
        ckpt_file = self._get_project_checkpoint_file(project_id)
        if not ckpt_file.exists():
            return None
        try:
            data = json.loads(ckpt_file.read_text(encoding="utf-8"))
            return [TranslationItem(**item) for item in data.get("items", [])]
        except Exception:
            return None

    def clear_checkpoint(self, project_id: str):
        ckpt_file = self._get_project_checkpoint_file(project_id)
        if ckpt_file.exists():
            try:
                ckpt_file.unlink()
            except Exception:
                pass
