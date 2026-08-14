"""
Tag and Variable Protector for Game Localization & Rich Text.
Shields game engine control codes, variables, escape sequences, and markup
from being altered or translated by LLMs, ensuring 100% loss-less reconstruction.
"""

import re
from typing import Dict, List, Tuple


class TagProtector:
    """
    Detects and masks game engine tags, control codes, and variables.
    Provides robust unmasking with fault tolerance for LLM formatting anomalies.
    """

    # Comprehensive compiled regex pattern for game codes & placeholders
    PATTERNS = [
        # 1. RPG Maker / Wolf RPG codes: \c[1], \v[10], \n[1], \i[23], \|, \., \!, \^, \>, \<, \\
        r"\\[cCvVnNiIgG]\[\d+\]",
        r"\\[\|\.\!\^\>\<\\\{\}\$]",
        
        # 2. Ren'Py text tags: {w}, {p=1.0}, {fast}, {nw}, {size=+4}, {/size}, {b}, {/b}, {i}, {/i}, {color=#fff}, {/color}, {a=...}, {/a}
        r"\{[a-zA-Z0-9_=\+\-#\.\/\s:]+\}",
        
        # 3. Unity RichText / HTML tags: <color=#FF0000>, </color>, <b>, </b>, <size=12>, <sprite=1>, etc.
        r"<\/?[a-zA-Z0-9_\-]+(?:\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s>]+))*\s*\/?>",
        
        # 4. Variables and placeholders: {0}, {name}, %s, %d, %1$s, %{key}, $variable, ${var}
        r"\{[0-9]+\}",
        r"\{[a-zA-Z0-9_\.]+\}",
        r"%[0-9]*\$?[a-zA-Z]",
        r"%\{[a-zA-Z0-9_]+\}",
        r"\$\{[a-zA-Z0-9_]+\}",
        r"\$[a-zA-Z0-9_]+",
        
        # 5. ASS / SSA Subtitle override tags: {\an8}, {\pos(100,200)}, etc.
        r"\{(?:\\[a-zA-Z0-9_\(\),\-\.]+)+\}",
        
        # 6. Common game brackets and ruby: [ruby=xxx]yyy[/ruby], [wait], [shake], [name=...]
        r"\[\/?[a-zA-Z0-9_\-]+(?:=[^\]]+)?\]",
        
        # 7. Explicit escape sequences: \n, \r, \t (when represented literally in strings)
        r"(?<!\\)\\n",
        r"(?<!\\)\\r",
        r"(?<!\\)\\t",
    ]

    MASTER_REGEX = re.compile("|".join(PATTERNS))

    @classmethod
    def mask_text(cls, text: str, prefix: str = "⟦TAG_", suffix: str = "⟧") -> Tuple[str, Dict[str, str]]:
        """
        Replaces all detected tags with unique safe placeholders.
        Returns:
            (masked_text, tag_map: {placeholder: original_tag})
        """
        if not text or not isinstance(text, str):
            return text, {}

        tag_map: Dict[str, str] = {}
        tag_counter = 0

        def replacer(match: re.Match) -> str:
            nonlocal tag_counter
            original_tag = match.group(0)
            placeholder = f"{prefix}{tag_counter}{suffix}"
            tag_map[placeholder] = original_tag
            tag_counter += 1
            return placeholder

        masked_text = cls.MASTER_REGEX.sub(replacer, text)
        return masked_text, tag_map

    @classmethod
    def unmask_text(cls, text: str, tag_map: Dict[str, str], prefix: str = "⟦TAG_", suffix: str = "⟧") -> str:
        """
        Restores original tags from placeholders with fault-tolerant fuzzy matching.
        """
        if not text or not tag_map:
            return text

        restored = text

        # 1. Exact match replacement
        for placeholder, original in tag_map.items():
            restored = restored.replace(placeholder, original)

        # 2. Tolerant matching for variations (e.g. LLM added spaces, used brackets, or lowercase: [TAG_0], ⟦ TAG_0 ⟧, etc.)
        for placeholder, original in tag_map.items():
            # Extract index from standard placeholder
            match = re.search(r"(\d+)", placeholder)
            if not match:
                continue
            idx = match.group(1)

            # Look for common corrupted variants
            variants = [
                rf"⟦\s*TAG_{idx}\s*⟧",
                rf"\[\s*TAG_{idx}\s*\]",
                rf"__\s*TAG_{idx}\s*__",
                rf"TAG_{idx}",
            ]
            for var_pat in variants:
                if re.search(var_pat, restored, flags=re.IGNORECASE):
                    restored = re.sub(var_pat, original.replace("\\", "\\\\"), restored, flags=re.IGNORECASE)

        return restored

    @classmethod
    def verify_tags_integrity(cls, masked_translation: str, tag_map: Dict[str, str]) -> List[str]:
        """
        Checks if any placeholder is missing or corrupted in translation.
        Returns list of missing placeholder keys.
        """
        missing = []
        for placeholder in tag_map.keys():
            match = re.search(r"(\d+)", placeholder)
            if not match:
                continue
            idx = match.group(1)
            # Check if either exact placeholder or loose idx exists
            if placeholder not in masked_translation and f"TAG_{idx}" not in masked_translation:
                missing.append(placeholder)
        return missing
