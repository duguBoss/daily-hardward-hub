"""AI model interaction for article generation."""
from __future__ import annotations
import json
import re
import time
from typing import Any

import requests
from .config import GEMINI_MODEL, GEMINI_MAX_RETRIES
from .utils import log

def call_gemini(
    session: requests.Session,
    api_key: str,
    detail: dict[str, Any],
    image_urls: list[str],
) -> dict[str, Any]:
    """Call Gemini to generate a hardware article with professional narrative."""
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )

    prompt = f"""
You are an expert hardware media editor and product analyst.
Transform this open-source hardware project into a premium WeChat sharing article.

Output JSON only:
- title: 18-28 chars, high-click, factual, professional Simplified Chinese.
- summary: 60-120 chars, sharp 1-2 sentence core value prop in Simplified Chinese.
- wxhtml: A fluid, engaging narrative (1000-1500 chars).

Writer Requirements:
1. Narrative over list: Do not use rigid bullet points for everything. Build a story.
2. Technical Depth: Highlight key components, wiring logic, or design choices.
3. Image Integration: Use provided image URLs in <img> tags strategically within the text.
4. Structure: 
   - Catchy opening about the problem it solves.
   - Deep dive into the project's 'soul' (core mechanism).
   - Implementation roadmap (how to build it).
   - Practical optimization and pitfalls.
   - Audience advice.
5. NO Markdown: Only clean HTML.
6. NO clickable links: Print URLs as plain text only.

Source Project: {detail['title']}
Source URL: {detail['url']}
Available Images: {json.dumps(image_urls, ensure_ascii=False)}
Content Reference: {detail['text'][:15000]}
""".strip()

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.75,
            "responseMimeType": "application/json",
        },
    }

    data: dict[str, Any] | None = None
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        resp = session.post(endpoint, headers={"Content-Type": "application/json"}, json=payload, timeout=180)
        if resp.status_code < 400:
            data = resp.json()
            break
        
        should_retry = resp.status_code == 429 or 500 <= resp.status_code <= 599
        if not should_retry or attempt == GEMINI_MAX_RETRIES:
            resp.raise_for_status()
        
        delay = min(60, int(resp.headers.get("Retry-After", "0")) or (2 ** attempt))
        log(f"warn: Gemini status={resp.status_code}, retrying in {delay}s ({attempt}/{GEMINI_MAX_RETRIES})")
        time.sleep(delay)

    if not data:
        raise RuntimeError("AI generation failed.")

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty text.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise RuntimeError("Invalid JSON response from AI.")
