"""Ollama integration for local LLM-powered structured extraction.

Requires a running Ollama instance (default: http://localhost:11434).
Set OLLAMA_URL env var to customize.
"""

import json
import logging
import os
from typing import Optional

import httpx

from ...core.router import smart_fetch
from ...core.schema import FetchResult

logger = logging.getLogger("agentfetch.ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


async def ollama_extract(
    url: str, schema: dict, model: Optional[str] = None
) -> FetchResult:
    """Fetch a URL and extract structured data using a local Ollama model.

    Args:
        url: The webpage to extract data from.
        schema: A dict mapping field names to descriptions.
        model: Ollama model name (default: llama3.2).

    Returns:
        FetchResult with content set to the extracted JSON.
    """
    page = await smart_fetch(url)
    model_name = model or OLLAMA_MODEL

    prompt = f"""Extract structured data from the following content according to this schema.
Return ONLY valid JSON matching the schema, no other text.

Schema:
{json.dumps(schema, indent=2)}

Content:
{page.content[:10000]}"""

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            data = resp.json()
            page.content = data.get("response", page.content)
            page.confidence = 0.7
    except Exception as e:
        logger.error("Ollama extraction failed: %s", e)
        page.error = f"Ollama extraction failed: {e}"
        page.confidence = 0.0

    return page


async def ollama_analyze(content: str, instruction: str) -> str:
    """Send content to Ollama for analysis with a custom instruction.

    Args:
        content: The text content to analyze.
        instruction: What to do with the content (e.g., 'Summarize this in 3 bullets').

    Returns:
        The model's response text.
    """
    prompt = f"{instruction}\n\n{content[:15000]}"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            data = resp.json()
            return data.get("response", "")
    except Exception as e:
        logger.error("Ollama analysis failed: %s", e)
        return f"Error: {e}"
