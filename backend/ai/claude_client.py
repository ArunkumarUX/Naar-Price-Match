from __future__ import annotations

import json
import logging
import re
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


def claude_available() -> bool:
    return bool(settings.ANTHROPIC_API_KEY) and settings.USE_CLAUDE


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


async def claude_json(
    system: str,
    user: str,
    *,
    max_tokens: int = 4096,
    temperature: float = 0,
) -> Any:
    if not claude_available():
        raise RuntimeError("Claude API not configured — set ANTHROPIC_API_KEY")

    from anthropic import AsyncAnthropic
    import httpx

    http_client = httpx.AsyncClient(trust_env=False, timeout=120.0)
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, http_client=http_client)
    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    parts = [block.text for block in response.content if hasattr(block, "text")]
    raw = "\n".join(parts).strip()
    if not raw:
        raise ValueError("Empty Claude response")
    return _extract_json(raw)
