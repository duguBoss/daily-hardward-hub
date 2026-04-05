"""Image download and local asset management."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

import requests
from .config import USER_AGENT, ASSETS_DIR, ROOT_DIR, TIMEOUT
from .utils import log, guess_extension

def to_github_raw_url(rel_path: Path) -> str:
    """Generate GitHub raw URL for a given relative path."""
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "").strip() or "main"
    path = rel_path.as_posix().lstrip("/")
    if repo:
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    return path

def download_images(
    session: requests.Session, image_urls: list[str], limit: int = 15
) -> list[str]:
    """Download images from source and return GitHub-ready URLs."""
    if not image_urls:
        return []
        
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    saved_urls: list[str] = []
    
    for idx, url in enumerate(image_urls[:limit], start=1):
        try:
            resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True)
            if resp.status_code != 200:
                log(f"warn: skip image {url} status={resp.status_code}")
                continue
            
            ext = guess_extension(url, resp.headers.get("content-type"))
            filename = f"hw_cover_{idx:02d}{ext}"
            local_path = ASSETS_DIR / filename
            
            with local_path.open("wb") as fw:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fw.write(chunk)
            
            rel = local_path.relative_to(ROOT_DIR)
            saved_urls.append(to_github_raw_url(rel))
        except Exception as exc:
            log(f"warn: image download failed for {url}: {exc}")
            
    return saved_urls
