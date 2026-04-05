"""Utility functions."""
from __future__ import annotations
import json
import re
import mimetypes
import sys
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .config import SEEN_FILE, DATA_DIR

def log(msg: str) -> None:
    """Print to stdout with flushing."""
    print(f"[daily-hardware-hub] {msg}", flush=True)

def normalize_url(url: Any, site_hint: str | None = None) -> str | None:
    """Normalize and fix various URL issues."""
    if isinstance(url, dict):
        url = url.get("src") or url.get("url") or url.get("downloadUrl")
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        if site_hint == "oshwhub":
            return "https://oshwhub.com" + url
        if site_hint == "instructables":
            return "https://www.instructables.com" + url
    return url

def load_seen_urls() -> set[str]:
    """Load seen project URLs from file."""
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x).strip() for x in data if str(x).strip()}
    except Exception as exc:
        log(f"warn: failed to parse seen urls: {exc}")
    return set()

def save_seen_urls(urls: set[str]) -> None:
    """Save seen project URLs to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(
        json.dumps(sorted(urls), ensure_ascii=False, indent=2), encoding="utf-8"
    )

def html_to_text(html: str) -> str:
    """Convert HTML content to plain text."""
    soup = BeautifulSoup(html, "html.parser")
    return " ".join(soup.get_text("\n", strip=True).split())

def markdown_to_text(md: str) -> str:
    """Convert Markdown content to plain text."""
    text = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", " ", md)
    text = re.sub(r"\[[^\]]+\]\(([^)]+)\)", " ", text)
    text = re.sub(r"[#>*`_~-]+", " ", text)
    return " ".join(text.split())

def extract_markdown_image_urls(md: str) -> list[str]:
    """Extract image URLs from markdown content."""
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md or "")

def guess_extension(url: str, content_type: str | None) -> str:
    """Guess file extension from URL and content type."""
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"}:
        return ext
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            if guessed == ".jpe":
                return ".jpg"
            return guessed
    return ".jpg"
