#!/usr/bin/env python3
import json
import mimetypes
import os
import random
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets" / "today"
POST_JSON = OUTPUT_DIR / "post.json"
SEEN_FILE = DATA_DIR / "seen_urls.json"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "5"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


@dataclass
class Candidate:
    source: str
    unique_id: str
    title: str
    url: str
    extra: dict[str, Any]


def log(msg: str) -> None:
    print(f"[daily-hardware-hub] {msg}", flush=True)


def normalize_url(url: Any, site_hint: str | None = None) -> str | None:
    if isinstance(url, dict):
        url = url.get("src") or url.get("url") or url.get("downloadUrl")
    if not isinstance(url, str):
        return None
    if not url:
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x).strip() for x in data if str(x).strip()}
    except Exception as exc:
        log(f"warn: failed to parse seen urls file: {exc}")
    return set()


def save_seen_urls(urls: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(
        json.dumps(sorted(urls), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clean_generated_outputs() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    if ASSETS_DIR.exists():
        shutil.rmtree(ASSETS_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def request_json(
    session: requests.Session, method: str, url: str, **kwargs: Any
) -> dict[str, Any]:
    headers = kwargs.pop("headers", {})
    merged_headers = {"User-Agent": USER_AGENT, **headers}
    resp = session.request(method, url, headers=merged_headers, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp.json()


def fetch_instructables_candidates(session: requests.Session) -> list[Candidate]:
    html = session.get(
        "https://www.instructables.com/projects/",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    ).text
    proxy_match = re.search(r'"typesenseProxy":"([^"]+)"', html)
    key_match = re.search(r'"typesenseApiKey":"([^"]+)"', html)
    if not proxy_match or not key_match:
        raise RuntimeError("Cannot find Instructables Typesense config from projects page.")

    proxy = proxy_match.group(1)
    api_key = key_match.group(1)
    endpoint = f"https://www.instructables.com{proxy}/collections/projects/documents/search"

    results: list[Candidate] = []
    seen_urls: set[str] = set()
    for page in (1, 2):
        params = {
            "q": "*",
            "query_by": "title,stepBody,screenName",
            "page": page,
            "sort_by": "publishDate:desc",
            "include_fields": (
                "title,urlString,coverImageUrl,screenName,favorites,views,"
                "primaryClassification,featureFlag,prizeLevel,IMadeItCount"
            ),
            "filter_by": "status:=PUBLISHED && indexTags:!=external",
            "per_page": 60,
        }
        payload = request_json(
            session,
            "GET",
            endpoint,
            params=params,
            headers={"x-typesense-api-key": api_key},
        )
        for hit in payload.get("hits", []):
            doc = hit.get("document", {})
            url_string = doc.get("urlString")
            title = (doc.get("title") or "").strip()
            if not url_string or not title:
                continue
            project_url = f"https://www.instructables.com/{url_string}/"
            if project_url in seen_urls:
                continue
            seen_urls.add(project_url)
            results.append(
                Candidate(
                    source="instructables",
                    unique_id=url_string,
                    title=title,
                    url=project_url,
                    extra={"url_string": url_string},
                )
            )
    return results


def fetch_oshwhub_candidates(session: requests.Session) -> list[Candidate]:
    raw_items: list[dict[str, Any]] = []
    for ep in (
        "https://oshwhub.com/api/project?page=1&pageSize=80",
        "https://oshwhub.com/api/common/recommendations?pageSize=40",
        "https://oshwhub.com/api/common/guessYouLike?pageSize=40",
    ):
        payload = request_json(session, "GET", ep)
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("lists"), list):
            raw_items.extend(result["lists"])
        elif isinstance(result, list):
            raw_items.extend(result)

    results: list[Candidate] = []
    seen_urls: set[str] = set()
    for item in raw_items:
        project_uuid = item.get("uuid")
        path = item.get("path")
        title = (item.get("name") or "").strip()
        if not project_uuid or not path or not title:
            continue
        project_url = normalize_url("/" + str(path).lstrip("/"), "oshwhub")
        if not project_url:
            continue
        if project_url in seen_urls:
            continue
        seen_urls.add(project_url)
        results.append(
            Candidate(
                source="oshwhub",
                unique_id=project_uuid,
                title=title,
                url=project_url,
                extra={"uuid": project_uuid, "path": path},
            )
        )
    return results


def choose_candidate(candidates: list[Candidate], seen_urls: set[str]) -> Candidate:
    unseen = [c for c in candidates if c.url not in seen_urls]
    if not unseen:
        raise RuntimeError("No unseen projects available in current candidate pool.")

    # Alternate preferred source by date, fallback to any unseen candidate.
    day_no = datetime.now(timezone.utc).toordinal()
    preferred = "instructables" if day_no % 2 == 0 else "oshwhub"
    preferred_pool = [c for c in unseen if c.source == preferred]
    pool = preferred_pool if preferred_pool else unseen

    seed = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(seed)
    return rng.choice(pool)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return " ".join(soup.get_text("\n", strip=True).split())


def markdown_to_text(md: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", " ", md)
    text = re.sub(r"\[[^\]]+\]\(([^)]+)\)", " ", text)
    text = re.sub(r"[#>*`_~-]+", " ", text)
    return " ".join(text.split())


def extract_markdown_image_urls(md: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md or "")


def get_instructables_details(
    session: requests.Session, candidate: Candidate
) -> dict[str, Any]:
    payload = request_json(
        session,
        "GET",
        "https://www.instructables.com/json-api/showInstructableModel",
        params={"urlString": candidate.extra["url_string"]},
    )

    title = payload.get("title") or candidate.title
    show_url = payload.get("showUrl") or f"/{candidate.extra['url_string']}/"
    source_url = normalize_url(show_url, "instructables") or candidate.url

    text_parts: list[str] = [str(title)]
    image_urls: list[str] = []

    cover_image = payload.get("coverImage") or {}
    if isinstance(cover_image, dict):
        u = normalize_url(cover_image.get("downloadUrl"))
        if u:
            image_urls.append(u)

    for step in payload.get("steps", []):
        step_title = (step.get("title") or "").strip()
        step_body_html = step.get("body") or ""
        if step_title:
            text_parts.append(step_title)
        if step_body_html:
            text_parts.append(html_to_text(step_body_html))

        for file_item in step.get("files", []):
            u = normalize_url(file_item.get("downloadUrl"))
            if u:
                image_urls.append(u)

    # De-duplicate while preserving order.
    dedup_images = list(dict.fromkeys(image_urls))
    content_text = "\n".join([p for p in text_parts if p]).strip()

    return {
        "source": "instructables",
        "title": title,
        "source_url": source_url,
        "content_text": content_text,
        "image_urls": dedup_images,
    }


def get_oshwhub_details(session: requests.Session, candidate: Candidate) -> dict[str, Any]:
    payload = request_json(
        session, "GET", f"https://oshwhub.com/api/project/{candidate.extra['uuid']}"
    )
    result = payload.get("result") or {}

    title = (result.get("name") or candidate.title).strip()
    path = result.get("path") or candidate.extra.get("path")
    source_url = normalize_url("/" + str(path).lstrip("/"), "oshwhub") or candidate.url

    intro = result.get("introduction") or ""
    content_md = result.get("content") or ""
    content_text = "\n".join(
        [x for x in [title, str(intro).strip(), markdown_to_text(str(content_md))] if x]
    ).strip()

    image_urls: list[str] = []
    for key in ("thumb", "cover"):
        u = normalize_url(result.get(key), "oshwhub")
        if u:
            image_urls.append(u)

    for u in extract_markdown_image_urls(str(content_md)):
        nu = normalize_url(u, "oshwhub")
        if nu:
            image_urls.append(nu)

    dedup_images = list(dict.fromkeys(image_urls))
    return {
        "source": "oshwhub",
        "title": title,
        "source_url": source_url,
        "content_text": content_text,
        "image_urls": dedup_images,
    }


def guess_extension(url: str, content_type: str | None) -> str:
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


def to_github_raw_url(rel_path: Path) -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "").strip() or "main"
    path = rel_path.as_posix().lstrip("/")
    if repo:
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    return path


def download_images(
    session: requests.Session, image_urls: list[str], limit: int = 12
) -> list[str]:
    if not image_urls:
        return []

    saved_urls: list[str] = []
    for idx, url in enumerate(image_urls[:limit], start=1):
        try:
            resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=40, stream=True)
            if resp.status_code != 200:
                log(f"warn: skip image {url} status={resp.status_code}")
                continue
            ext = guess_extension(url, resp.headers.get("content-type"))
            filename = f"cover_{idx:02d}{ext}"
            local_path = ASSETS_DIR / filename
            with local_path.open("wb") as fw:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fw.write(chunk)
            rel = local_path.relative_to(ROOT)
            saved_urls.append(to_github_raw_url(rel))
        except Exception as exc:
            log(f"warn: download failed for image {url}: {exc}")
    return saved_urls


def call_gemini(
    session: requests.Session,
    api_key: str,
    source_title: str,
    source_url: str,
    content_text: str,
    github_image_urls: list[str],
) -> dict[str, Any]:
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )

    prompt = f"""
You are an expert hardware editor.
Transform an open-source project into a WeChat-ready sharing article.

Return JSON only, with exactly these fields:
- title: Chinese title, 20-30 Chinese characters, high CTR style but truthful.
- summary: Chinese summary, 80-140 Chinese characters.
- wxhtml: WeChat-compatible HTML fragment (body content only, no script, no markdown).

Hard requirements:
1) Include the original project URL as a clickable link in the article.
2) Use the provided GitHub image URLs in <img> tags; mobile-friendly layout.
3) Suggested structure: value hook -> 3-5 highlights -> reproducible steps -> audience fit -> source link.
4) Do not output markdown, comments, or extra fields.
5) Output language for title and summary must be Simplified Chinese.

Source title: {source_title}
Source URL: {source_url}
Available image URLs: {json.dumps(github_image_urls, ensure_ascii=False)}
Extracted source text: {content_text[:15000]}
""".strip()

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.8,
            "responseMimeType": "application/json",
        },
    }
    data: dict[str, Any] | None = None
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        resp = session.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        if resp.status_code < 400:
            data = resp.json()
            break

        should_retry = resp.status_code == 429 or 500 <= resp.status_code <= 599
        if not should_retry or attempt == GEMINI_MAX_RETRIES:
            resp.raise_for_status()

        retry_after = resp.headers.get("Retry-After", "").strip()
        if retry_after.isdigit():
            delay = min(60, int(retry_after))
        else:
            delay = min(60, 2 ** attempt)
        log(
            f"warn: Gemini request failed status={resp.status_code}, "
            f"retrying in {delay}s (attempt {attempt}/{GEMINI_MAX_RETRIES})"
        )
        time.sleep(delay)

    if data is None:
        raise RuntimeError("Gemini request failed after retries.")

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = ""
    for p in parts:
        text += p.get("text", "")
    text = text.strip()
    if not text:
        raise RuntimeError("Gemini returned empty content.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some models may still return fenced text; fallback extraction.
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise RuntimeError("Gemini response is not valid JSON.")
        return json.loads(match.group(0))


def ensure_wxhtml(
    wxhtml: str,
    source_url: str,
    source_title: str,
    github_images: list[str],
) -> str:
    body = (wxhtml or "").strip()
    if not body:
        body = (
            f"<section><h2>{escape(source_title)}</h2>"
            f"<p>This article is adapted from an open-source hardware project.</p></section>"
        )

    if source_url not in body:
        body += (
            f"<p style='margin-top:16px;color:#666;font-size:14px;'>"
            f"Source project URL: <a href='{escape(source_url)}'>{escape(source_url)}</a></p>"
        )

    missing_images = [u for u in github_images if u not in body]
    for u in missing_images:
        body += (
            "<figure style='margin:16px 0;'>"
            f"<img src='{escape(u)}' style='width:100%;height:auto;border-radius:10px;'/>"
            "</figure>"
        )

    return (
        "<section style='font-size:16px;line-height:1.75;color:#222;'>"
        f"{body}"
        "</section>"
    )


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable.")

    clean_generated_outputs()
    seen_urls = load_seen_urls()
    log(f"loaded seen urls: {len(seen_urls)}")

    session = requests.Session()

    instructables = fetch_instructables_candidates(session)
    oshwhub = fetch_oshwhub_candidates(session)
    all_candidates = instructables + oshwhub
    if not all_candidates:
        raise RuntimeError("No candidates fetched from sources.")
    log(f"fetched candidates: instructables={len(instructables)} oshwhub={len(oshwhub)}")

    selected = choose_candidate(all_candidates, seen_urls)
    log(f"selected: {selected.source} - {selected.title} - {selected.url}")

    if selected.source == "instructables":
        detail = get_instructables_details(session, selected)
    else:
        detail = get_oshwhub_details(session, selected)

    image_urls = detail.get("image_urls", [])
    log(f"source images found: {len(image_urls)}")
    github_images = download_images(session, image_urls, limit=12)
    if not github_images:
        raise RuntimeError("No image downloaded from selected project.")
    log(f"images downloaded: {len(github_images)}")

    gemini_result = call_gemini(
        session=session,
        api_key=api_key,
        source_title=detail["title"],
        source_url=detail["source_url"],
        content_text=detail["content_text"],
        github_image_urls=github_images,
    )

    title = str(gemini_result.get("title", "")).strip()
    summary = str(gemini_result.get("summary", "")).strip()
    wxhtml_raw = str(gemini_result.get("wxhtml", "")).strip()

    if not title:
        title = f"{detail['title']} - Open Source Hardware Breakdown"
    if not summary:
        summary = (
            f"Adapted from a {detail['source']} open-source project with highlights, "
            "reproducible steps, and the original source link."
        )
    wxhtml = ensure_wxhtml(wxhtml_raw, detail["source_url"], title, github_images)

    post_data = {
        "title": title,
        "covers": github_images,
        "wxhtml": wxhtml,
        "summary": summary,
    }

    POST_JSON.write_text(
        json.dumps(post_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"written: {POST_JSON}")

    seen_urls.add(selected.url)
    save_seen_urls(seen_urls)
    log(f"seen urls updated: {len(seen_urls)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"error: {exc}")
        raise
