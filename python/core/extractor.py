"""
Multi-Format Text Extractor for Game Localization & Documents.
Supports Mtool JSON, Translator++ (CSV/XLSX), Ren'Py (.rpy), Subtitles (SRT/VTT/ASS),
PO/POT, PDF, Word (.docx), Markdown, HTML, and Raw Text.
"""

import os
import re
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import TranslationItem
from .tag_protector import TagProtector


class UniversalExtractor:
    """Extracts translatable items from various file types and raw strings."""

    @classmethod
    def extract_from_file(cls, file_path: Union[str, Path], mask_tags: bool = True) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """
        Extracts items from file.
        Returns:
            (items: List[TranslationItem], format_type: str, file_context: Dict[str, Any])
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        content_bytes = path.read_bytes()

        # Detect format
        if ext == ".json":
            return cls._extract_json(path.read_text(encoding="utf-8", errors="replace"), mask_tags)
        elif ext in (".csv", ".tsv"):
            delimiter = "\t" if ext == ".tsv" else ","
            return cls._extract_csv(path.read_text(encoding="utf-8", errors="replace"), delimiter, mask_tags)
        elif ext == ".xlsx":
            return cls._extract_xlsx(path, mask_tags)
        elif ext == ".rpy":
            return cls._extract_renpy(path.read_text(encoding="utf-8", errors="replace"), mask_tags)
        elif ext in (".srt", ".vtt", ".ass"):
            return cls._extract_subtitles(path.read_text(encoding="utf-8", errors="replace"), ext, mask_tags)
        elif ext in (".po", ".pot"):
            return cls._extract_po(path.read_text(encoding="utf-8", errors="replace"), mask_tags)
        elif ext == ".pdf":
            return cls._extract_pdf(path, mask_tags)
        elif ext == ".docx":
            return cls._extract_docx(path, mask_tags)
        elif ext in (".md", ".markdown"):
            return cls._extract_markdown(path.read_text(encoding="utf-8", errors="replace"), mask_tags)
        elif ext in (".html", ".htm"):
            return cls._extract_html(path.read_text(encoding="utf-8", errors="replace"), mask_tags)
        else:
            # Default TXT / Plain Text
            return cls._extract_plain_text(path.read_text(encoding="utf-8", errors="replace"), mask_tags)

    @classmethod
    def extract_from_text(cls, text: str, mask_tags: bool = True) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Extracts items from plain text string."""
        return cls._extract_plain_text(text, mask_tags)

    # -------------------------------------------------------------
    # Format-specific Extractors
    # -------------------------------------------------------------

    @classmethod
    def _extract_json(cls, raw_json: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles Mtool JSON & key-value translation dictionaries."""
        data = json.loads(raw_json)
        items: List[TranslationItem] = []

        # 1. Flat dictionary: {"key1": "text1", "key2": "text2"}
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    item = cls._build_item(str(k), v, mask_tags=mask_tags, raw_meta={"type": "flat_dict", "key": k})
                    items.append(item)
                elif isinstance(v, dict):
                    # Mtool style: {"key": {"src": "text", "trans": ""}} or {"text": "...", "name": "..."}
                    src_text = v.get("src") or v.get("message") or v.get("text") or v.get("original") or ""
                    speaker = v.get("name") or v.get("speaker")
                    if isinstance(src_text, str) and src_text.strip():
                        item = cls._build_item(str(k), src_text, speaker=speaker, mask_tags=mask_tags, raw_meta={"type": "nested_dict", "key": k, "orig_dict": v})
                        items.append(item)
        # 2. List of objects or strings
        elif isinstance(data, list):
            for idx, entry in enumerate(data):
                if isinstance(entry, str):
                    item = cls._build_item(str(idx), entry, mask_tags=mask_tags, raw_meta={"type": "list_str", "index": idx})
                    items.append(item)
                elif isinstance(entry, dict):
                    src_text = entry.get("src") or entry.get("message") or entry.get("text") or entry.get("original") or entry.get("source") or ""
                    speaker = entry.get("name") or entry.get("speaker") or entry.get("character")
                    item_id = str(entry.get("id", idx))
                    if isinstance(src_text, str) and src_text.strip():
                        item = cls._build_item(item_id, src_text, speaker=speaker, mask_tags=mask_tags, raw_meta={"type": "list_dict", "index": idx, "orig_dict": entry})
                        items.append(item)

        return items, "json", {"raw_data": data}

    @classmethod
    def _extract_csv(cls, raw_text: str, delimiter: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles CSV / TSV spreadsheets."""
        reader = csv.reader(raw_text.splitlines(), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            return [], "csv", {"delimiter": delimiter, "rows": []}

        header = rows[0]
        header_lower = [h.strip().lower() for h in header]

        # Detect columns
        id_col = next((i for i, h in enumerate(header_lower) if h in ("id", "index", "key", "line", "行号")), None)
        src_col = next((i for i, h in enumerate(header_lower) if h in ("source", "original", "src", "text", "原文", "文本", "japanese", "english")), None)
        tgt_col = next((i for i, h in enumerate(header_lower) if h in ("target", "translation", "trans", "tgt", "译文", "翻译", "chinese")), None)
        speaker_col = next((i for i, h in enumerate(header_lower) if h in ("speaker", "name", "character", "人名", "说话人")), None)

        if src_col is None:
            # Fallback: if 2 columns, col 0 is src or col 1 is src
            src_col = 0 if len(header) == 1 else 1

        items: List[TranslationItem] = []
        for r_idx, row in enumerate(rows[1:], start=1):
            if not row or len(row) <= src_col:
                continue
            src_text = row[src_col]
            if not src_text.strip():
                continue

            item_id = row[id_col] if (id_col is not None and len(row) > id_col) else str(r_idx)
            speaker = row[speaker_col] if (speaker_col is not None and len(row) > speaker_col) else None

            item = cls._build_item(item_id, src_text, speaker=speaker, mask_tags=mask_tags, raw_meta={
                "row_idx": r_idx,
                "full_row": row,
                "src_col": src_col,
                "tgt_col": tgt_col,
            })
            items.append(item)

        return items, "csv", {"delimiter": delimiter, "header": header, "rows": rows}

    @classmethod
    def _extract_xlsx(cls, file_path: Path, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles Excel (.xlsx) files (commonly exported by Translator++)."""
        import openpyxl

        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return [], "xlsx", {"file_path": str(file_path)}

        header = [str(cell) if cell is not None else "" for cell in rows[0]]
        header_lower = [h.strip().lower() for h in header]

        id_col = next((i for i, h in enumerate(header_lower) if h in ("id", "index", "key", "line", "行号")), None)
        src_col = next((i for i, h in enumerate(header_lower) if h in ("source", "original", "src", "text", "原文", "文本", "japanese", "english")), None)
        tgt_col = next((i for i, h in enumerate(header_lower) if h in ("target", "translation", "trans", "tgt", "译文", "翻译", "chinese")), None)
        speaker_col = next((i for i, h in enumerate(header_lower) if h in ("speaker", "name", "character", "人名", "说话人")), None)

        if src_col is None:
            src_col = 0 if len(header) == 1 else 1

        items: List[TranslationItem] = []
        for r_idx, row in enumerate(rows[1:], start=2):
            if not row or len(row) <= src_col:
                continue
            src_text = str(row[src_col]) if row[src_col] is not None else ""
            if not src_text.strip():
                continue

            item_id = str(row[id_col]) if (id_col is not None and len(row) > id_col and row[id_col] is not None) else str(r_idx)
            speaker = str(row[speaker_col]) if (speaker_col is not None and len(row) > speaker_col and row[speaker_col] is not None) else None

            item = cls._build_item(item_id, src_text, speaker=speaker, mask_tags=mask_tags, raw_meta={
                "row_idx": r_idx,
                "src_col": src_col,
                "tgt_col": tgt_col,
            })
            items.append(item)

        return items, "xlsx", {"file_path": str(file_path), "header": header}

    @classmethod
    def _extract_renpy(cls, script: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles Ren'Py (.rpy) script files."""
        items: List[TranslationItem] = []
        lines = script.splitlines()

        # Regex for dialogue: e "Hello" or "Hello" or narrator "..."
        # Regex for old/new translation strings: old "..." / new "..."
        dialogue_pattern = re.compile(r'^\s*(?:([a-zA-Z0-9_]+)\s+)?"((?:[^"\\]|\\.)*)"\s*$')
        old_pattern = re.compile(r'^\s*old\s+"((?:[^"\\]|\\.)*)"\s*$')

        for idx, line in enumerate(lines):
            # Check old string (Ren'Py translation block source)
            old_match = old_pattern.match(line)
            if old_match:
                text = old_match.group(1).replace(r'\"', '"')
                if text.strip():
                    item = cls._build_item(f"line_{idx+1}", text, mask_tags=mask_tags, raw_meta={"type": "old_string", "line_idx": idx, "orig_line": line})
                    items.append(item)
                continue

            # Ignore 'new "..."' since it's the target line to be replaced
            if re.match(r'^\s*new\s+"', line):
                continue

            # Check dialogue
            d_match = dialogue_pattern.match(line)
            if d_match:
                speaker = d_match.group(1)
                if speaker in ("voice", "jump", "scene", "show", "hide", "play", "stop", "translate"):
                    continue
                text = d_match.group(2).replace(r'\"', '"')
                if text.strip():
                    item = cls._build_item(f"line_{idx+1}", text, speaker=speaker, mask_tags=mask_tags, raw_meta={"type": "dialogue", "line_idx": idx, "orig_line": line})
                    items.append(item)
                continue

        return items, "renpy", {"lines": lines}

    @classmethod
    def _extract_subtitles(cls, raw_text: str, ext: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles SRT / VTT / ASS subtitles."""
        items: List[TranslationItem] = []
        lines = raw_text.splitlines()

        if ext == ".srt":
            # SRT blocks: Index \n Timecode \n Dialogue \n\n
            blocks = re.split(r"\n\s*\n", raw_text.strip())
            for b_idx, block in enumerate(blocks):
                b_lines = [l.strip() for l in block.splitlines() if l.strip()]
                if len(b_lines) >= 3:
                    sub_idx = b_lines[0]
                    timecode = b_lines[1]
                    text = "\n".join(b_lines[2:])
                    item = cls._build_item(sub_idx, text, mask_tags=mask_tags, raw_meta={"type": "srt", "index": sub_idx, "timecode": timecode})
                    items.append(item)
        elif ext == ".ass":
            # ASS dialogue lines: Dialogue: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            for idx, line in enumerate(lines):
                if line.startswith("Dialogue:"):
                    parts = line.split(",", 9)
                    if len(parts) >= 10:
                        speaker = parts[4].strip() or None
                        text = parts[9]
                        item = cls._build_item(f"ass_{idx+1}", text, speaker=speaker, mask_tags=mask_tags, raw_meta={"type": "ass", "line_idx": idx, "prefix": ",".join(parts[:9]) + ","})
                        items.append(item)
        else:
            # VTT / Generic fallback
            item_idx = 0
            for idx, line in enumerate(lines):
                if "-->" not in line and not line.isdigit() and line.strip() and not line.startswith("WEBVTT"):
                    item_idx += 1
                    item = cls._build_item(str(item_idx), line.strip(), mask_tags=mask_tags, raw_meta={"type": "vtt_line", "line_idx": idx})
                    items.append(item)

        return items, "subtitle", {"raw_lines": lines, "ext": ext}

    @classmethod
    def _extract_po(cls, raw_text: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles Gettext PO / POT files."""
        items: List[TranslationItem] = []
        # Pattern to match msgid "..." msgstr "..."
        pattern = re.compile(r'msgid\s+"((?:[^"\\]|\\.)*)"\s*\n\s*msgstr\s+"((?:[^"\\]|\\.)*)"', re.MULTILINE)
        matches = pattern.finditer(raw_text)

        for idx, match in enumerate(matches):
            src_text = match.group(1).replace(r'\"', '"').replace(r'\n', '\n')
            if src_text.strip():
                item = cls._build_item(f"po_{idx+1}", src_text, mask_tags=mask_tags, raw_meta={"type": "po", "index": idx, "span": match.span()})
                items.append(item)

        return items, "po", {"raw_text": raw_text}

    @classmethod
    def _extract_pdf(cls, file_path: Path, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles PDF files via PyMuPDF / fitz."""
        import fitz  # PyMuPDF

        items: List[TranslationItem] = []
        doc = fitz.open(file_path)
        page_texts: List[str] = []

        item_idx = 0
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            page_texts.append(text)
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for p in paragraphs:
                item_idx += 1
                item = cls._build_item(f"p{page_num+1}_{item_idx}", p, mask_tags=mask_tags, raw_meta={"page": page_num + 1, "type": "pdf"})
                items.append(item)

        return items, "pdf", {"total_pages": len(doc), "page_texts": page_texts}

    @classmethod
    def _extract_docx(cls, file_path: Path, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles Word .docx files."""
        import docx

        doc = docx.Document(file_path)
        items: List[TranslationItem] = []
        for idx, p in enumerate(doc.paragraphs):
            text = p.text.strip()
            if text:
                item = cls._build_item(f"para_{idx+1}", text, mask_tags=mask_tags, raw_meta={"para_idx": idx, "style": p.style.name if p.style else "Normal"})
                items.append(item)

        return items, "docx", {"file_path": str(file_path)}

    @classmethod
    def _extract_markdown(cls, raw_text: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles Markdown files, protecting code blocks & headings."""
        items: List[TranslationItem] = []
        # Split by empty lines to preserve paragraphs/lists/code blocks
        chunks = re.split(r"\n{2,}", raw_text)

        for idx, chunk in enumerate(chunks):
            chunk_trimmed = chunk.strip()
            if not chunk_trimmed:
                continue
            item = cls._build_item(f"md_{idx+1}", chunk_trimmed, mask_tags=mask_tags, raw_meta={"chunk_idx": idx, "type": "markdown"})
            items.append(item)

        return items, "markdown", {"raw_text": raw_text}

    @classmethod
    def _extract_html(cls, raw_html: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Handles HTML files via BeautifulSoup."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")
        items: List[TranslationItem] = []
        item_idx = 0

        for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "span", "div"]):
            # Only extract leaf text elements
            if el.string and el.string.strip():
                text = el.string.strip()
                item_idx += 1
                item = cls._build_item(f"html_{item_idx}", text, mask_tags=mask_tags, raw_meta={"tag_name": el.name})
                items.append(item)

        return items, "html", {"raw_html": raw_html}

    @classmethod
    def _extract_plain_text(cls, raw_text: str, mask_tags: bool) -> Tuple[List[TranslationItem], str, Dict[str, Any]]:
        """Default Plain Text extractor (splits by paragraphs or dialogue lines)."""
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        items: List[TranslationItem] = []

        for idx, line in enumerate(lines):
            # Check if line has speaker prefix like "Alice: Hello" or "【爱丽丝】你好"
            speaker = None
            text = line

            m_colon = re.match(r"^([^\s:：]{1,15})[:：]\s*(.*)$", line)
            m_bracket = re.match(r"^[【\[「]([^】\]」]{1,15})[】\]」]\s*(.*)$", line)

            if m_colon:
                speaker = m_colon.group(1)
                text = m_colon.group(2)
            elif m_bracket:
                speaker = m_bracket.group(1)
                text = m_bracket.group(2)

            item = cls._build_item(str(idx + 1), text, speaker=speaker, mask_tags=mask_tags, raw_meta={"line_idx": idx, "original_line": line})
            items.append(item)

        return items, "text", {"total_lines": len(lines)}

    @staticmethod
    def _build_item(
        item_id: str,
        source_text: str,
        speaker: Optional[str] = None,
        context: Optional[str] = None,
        mask_tags: bool = True,
        raw_meta: Optional[Dict[str, Any]] = None,
    ) -> TranslationItem:
        """Helper to create and optionally tag-mask a TranslationItem."""
        if mask_tags:
            masked, tag_map = TagProtector.mask_text(source_text)
        else:
            masked = source_text
            tag_map = {}

        return TranslationItem(
            id=item_id,
            source_text=source_text,
            speaker=speaker,
            context=context,
            masked_text=masked,
            tag_map=tag_map,
            raw_metadata=raw_meta or {},
        )
