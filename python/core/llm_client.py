"""
Universal LLM Client for Multi-Agent Translation.
Supports OpenAI-compatible APIs (DeepSeek, SiliconFlow, OpenAI, Ollama, Moonshot, etc.)
with automatic exponential backoff retry and robust JSON block parsing.
"""

import json
import re
import asyncio
from typing import Any, Dict, List, Optional
import httpx
from openai import AsyncOpenAI


class UniversalLLMClient:
    """Async OpenAI-compatible LLM Client with built-in retry and JSON extraction."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        timeout: float = 90.0,
        max_retries: int = 4,
    ):
        self.api_key = api_key or "sk-dummy"
        self.base_url = base_url or "https://api.deepseek.com/v1"
        self.model_name = model_name or "deepseek-chat"
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

        # Initialize AsyncOpenAI client
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            http_client=httpx.AsyncClient(timeout=self.timeout, limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)),
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        json_mode: bool = False,
    ) -> str:
        """Calls chat completion with retry and backoff."""
        temp = self.temperature if temperature is None else temperature
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": temp,
                }
                if json_mode:
                    # Request json object if provider supports it
                    try:
                        kwargs["response_format"] = {"type": "json_object"}
                    except Exception:
                        pass

                response = await self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                return content.strip()

            except Exception as e:
                last_exception = e
                # Wait before retrying (exponential backoff)
                wait_time = min(2 ** attempt + 0.5, 15)
                if attempt < self.max_retries:
                    await asyncio.sleep(wait_time)

        raise RuntimeError(f"LLM API request failed after {self.max_retries} attempts: {last_exception}")

    @staticmethod
    def parse_json(raw_text: str) -> Any:
        """
        Extracts and parses JSON object or array from LLM response text,
        safely stripping markdown fences ```json ... ``` and trailing commas.
        """
        if not raw_text or not isinstance(raw_text, str):
            return {}

        text = raw_text.strip()

        # 1. Try direct parsing
        try:
            return json.loads(text)
        except Exception:
            pass

        # 2. Extract from markdown code fence ```json ... ``` or ``` ... ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                return json.loads(candidate)
            except Exception:
                text = candidate

        # 3. Locate outermost JSON structure [ ... ] or { ... }
        match_obj = re.search(r"(\{[\s\S]*\})", text)
        match_arr = re.search(r"(\[[\s\S]*\])", text)

        candidates = []
        if match_obj:
            candidates.append(match_obj.group(1))
        if match_arr:
            candidates.append(match_arr.group(1))

        for cand in candidates:
            # Clean trailing commas
            cleaned = re.sub(r",\s*([\]}])", r"\1", cand)
            try:
                return json.loads(cleaned)
            except Exception:
                pass

        # 4. Fallback line-by-line dictionary parsing
        result_dict = {}
        for line in text.splitlines():
            kv = re.match(r'^\s*"?([^":]+)"?\s*:\s*"(.*)"\s*,?\s*$', line)
            if kv:
                result_dict[kv.group(1).strip()] = kv.group(2).strip()
        if result_dict:
            return result_dict

        raise ValueError(f"Could not parse valid JSON from text: {raw_text[:200]}...")
