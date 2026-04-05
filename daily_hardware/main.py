"""Main entry point for Daily Hardware Hub."""
from __future__ import annotations
import json
import os
import random
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

import requests

from .config import DATA_DIR, OUTPUT_DIR, ASSETS_DIR, POST_JSON, GEMINI_MODEL
from .filters import is_hardware_project
from .utils import log, load_seen_urls, save_seen_urls
from .models import Candidate
from .fetcher import fetch_instructables_candidates, fetch_oshwhub_candidates, get_project_details
from .images import download_images
from .ai import call_gemini
from .renderer import ensure_wxhtml

def clean_generated_outputs() -> None:
    """Wipe generated folders."""
    for d in (OUTPUT_DIR, ASSETS_DIR):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

def choose_candidate(candidates: list[Candidate], seen_urls: set[str]) -> Candidate:
    """Smart selection: alternate sources by date and ensure freshness."""
    unseen = [c for c in candidates if c.url not in seen_urls and is_hardware_project(c.title)]
    if not unseen:
        raise RuntimeError("No fresh hardware project found in candidate pool.")

    # Source alternation logic by ordinal day number
    day_no = datetime.now(timezone.utc).toordinal()
    preferred = "instructables" if day_no % 2 == 0 else "oshwhub"
    
    pool = [c for c in unseen if c.source == preferred] or unseen
    
    # Stable random choice per day
    seed = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(seed)
    return rng.choice(pool)

def main() -> int:
    """Orchestrate the content generation workflow."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        log("error: missing GEMINI_API_KEY environment variable.")
        return 1

    log(f"starting daily-hardware-hub workflow (model: {GEMINI_MODEL})")
    clean_generated_outputs()
    
    seen_urls = load_seen_urls()
    log(f"loaded {len(seen_urls)} seen URLs.")

    session = requests.Session()
    
    # Discovery phase
    candidates = []
    try:
        candidates.extend(fetch_instructables_candidates(session))
        candidates.extend(fetch_oshwhub_candidates(session))
    except Exception as e:
        log(f"warn: candidate discovery failed partly: {e}")
    
    if not candidates:
        log("error: no project candidates discovered from any source.")
        return 1
    
    log(f"discovered {len(candidates)} total candidates.")
    
    # Selection phase
    selected = choose_candidate(candidates, seen_urls)
    log(f"selected project: {selected.source} - {selected.title} - {selected.url}")
    
    # Extraction phase
    details = get_project_details(session, selected)
    log(f"fetched detailed content: {len(details['text'])} chars.")
    if not is_hardware_project(details.get("title", ""), details.get("text", "")):
        raise RuntimeError(f"Selected project is not a hardware/tech build: {selected.title}")
    
    # Asset phase
    github_image_urls = download_images(session, details["images"], limit=15)
    if not github_image_urls:
        log("error: failed to download any project images.")
        return 1
    log(f"downloaded {len(github_image_urls)} assets.")
    
    # Generation phase
    log("calling AI for premium article generation...")
    ai_result = call_gemini(session, gemini_key, details, github_image_urls)
    
    title = str(ai_result.get("title", "")).strip() or f"{selected.title} 开源项目解析"
    summary = str(ai_result.get("summary", "")).strip() or f"{selected.title}：一款精妙的开源硬件作品。"
    wxhtml_raw = str(ai_result.get("wxhtml", "")).strip()
    
    # Refinement phase
    wxhtml = ensure_wxhtml(wxhtml_raw, title, summary, details)
    
    # Output phase
    covers = list(dict.fromkeys(github_image_urls + [details["url"]]))
    post_data = {
        "title": title,
        "covers": covers,
        "wxhtml": wxhtml,
        "summary": summary,
        "source_url": details["url"],
    }
    
    POST_JSON.write_text(json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"workflow completed. output saved to {POST_JSON}")
    
    # Persist phase
    seen_urls.add(selected.url)
    save_seen_urls(seen_urls)
    log(f"persisted {len(seen_urls)} total seen items.")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"CRITICAL: {exc}")
        sys.exit(1)
