"""
Local Agent Helper Utility for Antigravity & Sub-Agents.
Provides offline extraction, tag masking, batch generation, and assembly
so Antigravity sub-agents can translate directly using the IDE's built-in model session.
"""

import sys
import json
from pathlib import Path
from typing import Optional
import typer

# 将 stdout/stderr 重配置为 UTF-8：Windows 默认代码页(GBK)无法编码遮罩占位符
# (⟦TAG_n⟧, U+27E6) 等字符，否则 print(json.dumps(..., ensure_ascii=False)) 会抛
# UnicodeEncodeError，导致 extract / inspect / assemble 全部失败。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8")

from core.extractor import UniversalExtractor
from core.tag_protector import TagProtector
from core.chunker import SmartBatcher
from core.models import TranslationItem
from core.agents.assembler_agent import AssemblerAgent

app = typer.Typer(help="Antigravity Sub-Agent Localization Helper")


@app.command(name="extract")
def extract(
    input_file: str = typer.Argument(..., help="Path to input game script or document"),
    output_json: Optional[str] = typer.Option(None, "--output", "-o", help="Path to output intermediate JSON"),
    batch_size: int = typer.Option(25, "--batch-size", "-b", help="Number of items per batch"),
):
    """
    Extracts text from file, masks game tags/variables, and creates batches for sub-agents.
    """
    path = Path(input_file)
    if not path.exists():
        print(json.dumps({"status": "error", "message": f"File not found: {input_file}"}))
        raise typer.Exit(1)

    items, format_type, context = UniversalExtractor.extract_from_file(path, mask_tags=True)
    batches = SmartBatcher.create_batches(items, batch_size=batch_size)
    speakers = list({it.speaker for it in items if it.speaker})

    result = {
        "status": "success",
        "file_name": path.name,
        "format": format_type,
        "total_items": len(items),
        "total_batches": len(batches),
        "speakers": speakers,
        "batches": [
            {
                "batch_index": b.batch_index,
                "preceding_context": b.preceding_context,
                "speakers": b.speakers,
                "items": [
                    {
                        "id": it.id,
                        "speaker": it.speaker,
                        "text": it.masked_text or it.source_text,
                        "source_text": it.source_text,
                        "tag_map": it.tag_map,
                        "raw_metadata": it.raw_metadata,
                    }
                    for it in b.items
                ],
            }
            for b in batches
        ],
    }

    out_content = json.dumps(result, ensure_ascii=False, indent=2)
    if output_json:
        out_path = Path(output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_content, encoding="utf-8")
        print(json.dumps({"status": "success", "saved_to": str(out_path), "total_items": len(items), "total_batches": len(batches)}))
    else:
        print(out_content)


@app.command(name="inspect")
def inspect(
    input_file: str = typer.Argument(..., help="Path to input game script or document"),
):
    """
    Lightweight inspection: reports format, item count, speakers and tag/variable
    distribution without dumping the full extracted text.
    """
    path = Path(input_file)
    if not path.exists():
        print(json.dumps({"status": "error", "message": f"File not found: {input_file}"}))
        raise typer.Exit(1)

    items, format_type, context = UniversalExtractor.extract_from_file(path, mask_tags=True)

    tag_counts: dict = {}
    for it in items:
        for placeholder in it.tag_map:
            tag_counts[placeholder] = tag_counts.get(placeholder, 0) + 1

    result = {
        "status": "success",
        "file_name": path.name,
        "format": format_type,
        "total_items": len(items),
        "speakers": sorted({it.speaker for it in items if it.speaker}),
        "tag_counts": tag_counts,
        "sample_preview": [
            {
                "id": it.id,
                "speaker": it.speaker,
                "text_preview": (it.masked_text or it.source_text or "")[:120],
            }
            for it in items[:3]
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command(name="assemble")
def assemble(
    original_file: str = typer.Argument(..., help="Path to original source file"),
    translations_json: str = typer.Argument(..., help="Path to JSON containing translated items (array of {id, text, [tag_map]})"),
    output_file: str = typer.Argument(..., help="Path to output reconstructed file"),
):
    """
    Unmasks tags and reconstructs the translated file in its original format.
    """
    orig_path = Path(original_file)
    trans_path = Path(translations_json)

    if not orig_path.exists() or not trans_path.exists():
        print(json.dumps({"status": "error", "message": "File not found"}))
        raise typer.Exit(1)

    items, format_type, context = UniversalExtractor.extract_from_file(orig_path, mask_tags=True)
    item_map = {str(it.id): it for it in items}

    trans_data = json.loads(trans_path.read_text(encoding="utf-8"))
    
    # Handle list of items or dictionary
    if isinstance(trans_data, dict) and "items" in trans_data:
        raw_list = trans_data["items"]
    elif isinstance(trans_data, dict) and "batches" in trans_data:
        raw_list = [it for b in trans_data["batches"] for it in b.get("items", [])]
    elif isinstance(trans_data, list):
        raw_list = trans_data
    elif isinstance(trans_data, dict):
        raw_list = [{"id": k, "text": v} for k, v in trans_data.items()]
    else:
        raw_list = []

    for entry in raw_list:
        if isinstance(entry, dict) and "id" in entry:
            str_id = str(entry["id"])
            if str_id in item_map:
                translated_text = entry.get("text") or entry.get("translated_text") or entry.get("trans") or ""
                item_map[str_id].translated_text = translated_text

    # Reconstruct and assemble output file
    AssemblerAgent.assemble_results(
        items=items,
        format_type=format_type,
        file_context=context,
        output_path=output_file,
    )

    print(json.dumps({
        "status": "success",
        "output_file": output_file,
        "total_items_assembled": len(items),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
