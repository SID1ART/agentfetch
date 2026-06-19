import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional

import httpx

from .schema import ResearchConfig, ResearchResult, ResearchSource, ScrapeConfig
from .router import smart_fetch
from .searchengine import parallel_search, generate_query_variations

logger = logging.getLogger("agentfetch.researcher")


async def _call_llm(
    prompt: str,
    system_prompt: str = "",
    output_schema: Optional[dict] = None,
) -> str:
    ollama_url = os.environ.get("OLLAMA_URL", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if ollama_url:
        try:
            model = os.environ.get("OLLAMA_MODEL", "llama3.2")
            body = {
                "model": model,
                "prompt": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
                "stream": False,
            }
            if output_schema:
                body["format"] = "json"
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/generate",
                    json=body,
                )
                data = resp.json()
                return data.get("response", "").strip()
        except Exception as e:
            logger.warning("Ollama LLM call failed: %s", e)

    if anthropic_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_key)
            messages = []
            if system_prompt:
                messages.append({"role": "user", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            msg = client.messages.create(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
                max_tokens=4000,
                messages=messages,
            )
            return msg.content[0].text.strip()
        except Exception as e:
            logger.warning("Anthropic LLM call failed: %s", e)

    return ""


async def _decompose_query(prompt: str) -> list[str]:
    system = "You are a research query decomposer. Break the user's research question into 3-5 specific, searchable web queries. Return one query per line, no numbering, no extra text."
    result = await _call_llm(prompt, system_prompt=system)
    if result:
        queries = [q.strip().strip('"').strip("'") for q in result.split("\n") if q.strip()]
        if len(queries) >= 2:
            return queries[:5]
    fallback = generate_query_variations(prompt)
    return fallback[:5]


def _format_citation(source: ResearchSource, fmt: str, idx: int) -> str:
    title = source.title or ""
    url = source.url
    if fmt == "numbered":
        return f"[{idx}]"
    if fmt == "mla":
        domain = url.split("/")[2] if "://" in url else url
        return f'"{title}." {domain}.'
    if fmt == "apa":
        domain = url.split("/")[2] if "://" in url else url
        return f"({title}, {domain})"
    if fmt == "chicago":
        domain = url.split("/")[2] if "://" in url else url
        return f'"{title}," {domain}.'
    return f"[{idx}]"


async def smart_research(
    input: str,
    config: Optional[ResearchConfig] = None,
) -> ResearchResult:
    start = time.time()
    request_id = str(uuid.uuid4())[:8]
    cfg = config or ResearchConfig(prompt=input)

    result = ResearchResult(
        request_id=request_id,
        query=input,
        status="running",
    )

    sub_queries = await _decompose_query(input)
    logger.info("Research [%s]: decomposed into %d sub-queries", request_id, len(sub_queries))

    sources_per_query = max(1, cfg.max_sources // len(sub_queries))
    all_fetch_results = []
    seen_urls: set[str] = set()

    for sq in sub_queries:
        try:
            engine_results, engines_used, engine_errors = await parallel_search(
                query=sq,
                max_results=sources_per_query,
            )
        except Exception as e:
            logger.warning("Research [%s]: search failed for '%s': %s", request_id, sq, e)
            continue

        fetch_tasks = []
        for er in engine_results:
            dedup_key = er.url.rstrip("/").lower()
            if dedup_key not in seen_urls:
                seen_urls.add(dedup_key)
                fetch_tasks.append(er)

        for er in fetch_tasks[:sources_per_query]:
            try:
                fr = await smart_fetch(er.url, config=ScrapeConfig(max_content_length=15000))
                all_fetch_results.append(fr)
            except Exception as e:
                logger.debug("Research [%s]: fetch failed for %s: %s", request_id, er.url, e)

    if cfg.depth == "deep":
        for iteration in range(cfg.max_iterations):
            if not all_fetch_results:
                break
            context = "\n\n".join(
                f"Source: {r.title or r.url}\n{r.content[:2000]}" for r in all_fetch_results[-5:]
            )
            gap_prompt = (
                f"Original question: {input}\n\n"
                f"Information gathered so far:\n{context}\n\n"
                f"What important information is still missing? Generate 1-2 specific search queries to fill the gaps. "
                f"Return one query per line, no numbering."
            )
            follow_ups = await _call_llm(gap_prompt)
            if not follow_ups:
                break
            fq_list = [q.strip().strip('"').strip("'") for q in follow_ups.split("\n") if q.strip()][:2]
            if not fq_list:
                break
            logger.info("Research [%s]: deep iteration %d, follow-ups: %s", request_id, iteration + 1, fq_list)
            for fq in fq_list:
                try:
                    engine_results, _, _ = await parallel_search(query=fq, max_results=3)
                except Exception:
                    continue
                for er in engine_results[:3]:
                    dedup_key = er.url.rstrip("/").lower()
                    if dedup_key not in seen_urls:
                        seen_urls.add(dedup_key)
                        try:
                            fr = await smart_fetch(er.url, config=ScrapeConfig(max_content_length=15000))
                            all_fetch_results.append(fr)
                        except Exception:
                            pass

    sources: list[ResearchSource] = []
    for i, fr in enumerate(all_fetch_results):
        rs = ResearchSource(
            url=fr.url,
            title=fr.title,
            content=fr.content[:5000],
            relevance_score=fr.confidence,
        )
        rs.citation = _format_citation(rs, cfg.citation_format, i + 1)
        sources.append(rs)

    model_used = "ollama" if os.environ.get("OLLAMA_URL") else "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "none"

    if all_fetch_results:
        context = "\n\n".join(
            f"[{i + 1}] {s.title or s.url}\n{s.content[:2000]}"
            for i, s in enumerate(sources[:cfg.max_sources])
        )
        citation_instruction = {
            "numbered": "Use [1], [2], etc. to cite sources.",
            "mla": "Use MLA in-text citations like (Author. Title).",
            "apa": "Use APA in-text citations like (Author, Year).",
            "chicago": "Use Chicago footnotes like (Author, Title).",
        }.get(cfg.citation_format, "Use [1], [2], etc. to cite sources.")

        if cfg.output_schema:
            schema_instruction = (
                f"\n\nAlso return a JSON object matching this schema:\n{json.dumps(cfg.output_schema, indent=2)}\n"
                f"Wrap the JSON in ```json ... ``` markers. The markdown report should come first."
            )
        else:
            schema_instruction = ""

        system = (
            "You are a research analyst. Write a comprehensive, well-structured report "
            "based on the provided sources. Use markdown with headings, bullet points, and paragraphs. "
            f"{citation_instruction}"
        )
        user_prompt = (
            f"Research question: {input}\n\n"
            f"Sources:\n{context}\n\n"
            f"Write a detailed report that answers the question. Use citations to reference sources."
            f"{schema_instruction}"
        )

        answer = await _call_llm(user_prompt, system_prompt=system, output_schema=cfg.output_schema)
        result.answer = answer or "No answer could be generated from the gathered sources."

        if cfg.output_schema and answer:
            import re
            json_match = re.search(r"```json\s*(.*?)\s*```", answer, re.DOTALL)
            if json_match:
                try:
                    result.structured_output = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
    else:
        result.answer = "No sources could be gathered for this research question."

    result.sources = sources
    result.total_sources = len(sources)
    result.model_used = model_used
    result.response_time = round(time.time() - start, 2)
    result.status = "complete"
    return result
