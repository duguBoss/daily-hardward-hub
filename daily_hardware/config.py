"""Configuration constants."""
from __future__ import annotations
import os
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
ASSETS_DIR = ROOT_DIR / "assets" / "today"
POST_JSON = OUTPUT_DIR / "post.json"
SEEN_FILE = DATA_DIR / "seen_urls.json"

# Header Image
HEADER_IMG = os.getenv("HEADER_IMG", "https://mmbiz.qpic.cn/mmbiz_gif/xm1dT1jCe8lIO3P2oFVtd1x040PKGCRPN033gUTrHQQz0Licdqug5X1QgUPQBRCicoTqdYMrpgk7etibXLkK9rwcg/0?wx_fmt=gif&from=appmsg")

# AI settings
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "5"))

# Network
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
TIMEOUT = 40
