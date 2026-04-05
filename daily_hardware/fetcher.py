"""Project fetchers for Instructables and Oshwhub."""
from __future__ import annotations
import re
from typing import Any

import requests
from .models import Candidate
from .filters import build_instructables_candidate_text, is_hardware_project
from .utils import log, normalize_url, html_to_text, markdown_to_text, extract_markdown_image_urls
from .config import USER_AGENT, TIMEOUT

def request_json(session: requests.Session, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    """Helper for making JSON requests."""
    headers = kwargs.pop("headers", {})
    merged_headers = {"User-Agent": USER_AGENT, **headers}
    resp = session.request(method, url, headers=merged_headers, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp.json()

def extract_oshwhub_page_image_urls(page_html: str) -> list[str]:
    """Extract hardware-related images from project page HTML."""
    raw = re.findall(
        r"""https?://[^"'\s>]+?\.(?:jpg|jpeg|png|webp|gif)|//[^"'\s>]+?\.(?:jpg|jpeg|png|webp|gif)""",
        page_html,
        flags=re.I,
    )
    normalized: list[str] = []
    for item in raw:
        u = normalize_url(item, "oshwhub")
        if not u:
            continue
        lu = u.lower()
        # Filter out UI/avatar noise
        if "avatar" in lu or "default" in lu:
            continue
        if any(substring in lu for substring in ["image.lceda.cn/oshwhub/", "image.lceda.cn/pullimage/", "image-pro.lceda.cn/pullimages/"]):
            normalized.append(u)
    return list(dict.fromkeys(normalized))

def fetch_instructables_candidates(session: requests.Session) -> list[Candidate]:
    """Fetch recent projects from Instructables."""
    html = session.get("https://www.instructables.com/projects/", headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT).text
    proxy_match = re.search(r'"typesenseProxy":"([^"]+)"', html)
    key_match = re.search(r'"typesenseApiKey":"([^"]+)"', html)
    if not proxy_match or not key_match:
        raise RuntimeError("instructables: Typesense config not found.")

    api_key = key_match.group(1)
    endpoint = f"https://www.instructables.com{proxy_match.group(1)}/collections/projects/documents/search"

    results: list[Candidate] = []
    seen_urls: set[str] = set()
    for page in (1, 2):
        params = {
            "q": "*",
            "query_by": "title,stepBody,screenName",
            "page": page,
            "sort_by": "publishDate:desc",
            "include_fields": "title,urlString,coverImageUrl,screenName",
            "filter_by": "status:=PUBLISHED && indexTags:!=external",
            "per_page": 50,
        }
        payload = request_json(session, "GET", endpoint, params=params, headers={"x-typesense-api-key": api_key})
        for hit in payload.get("hits", []):
            doc = hit.get("document", {})
            slug = doc.get("urlString")
            title = (doc.get("title") or "").strip()
            if not slug or not title:
                continue
            if not is_hardware_project(title, build_instructables_candidate_text(doc)):
                continue
            url = f"https://www.instructables.com/{slug}/"
            if url not in seen_urls:
                seen_urls.add(url)
                results.append(Candidate("instructables", slug, title, url, {"slug": slug}))
    return results

def fetch_oshwhub_candidates(session: requests.Session) -> list[Candidate]:
    """Fetch projects from Oshwhub API endpoints."""
    raw_items: list[dict[str, Any]] = []
    for ep in [
        "https://oshwhub.com/api/project?page=1&pageSize=80",
        "https://oshwhub.com/api/common/recommendations?pageSize=40",
    ]:
        try:
            payload = request_json(session, "GET", ep)
            result = payload.get("result")
            if isinstance(result, dict) and isinstance(result.get("lists"), list):
                raw_items.extend(result["lists"])
            elif isinstance(result, list):
                raw_items.extend(result)
        except Exception as e:
            log(f"warn: oshwhub fetch {ep} failed: {e}")

    results: list[Candidate] = []
    seen_urls: set[str] = set()
    for item in raw_items:
        uuid = item.get("uuid")
        path = item.get("path")
        title = (item.get("name") or "").strip()
        if not uuid or not path or not title:
            continue
        summary_text = "\n".join(
            str(item.get(key) or "") for key in ("name", "title", "description", "introduction", "summary")
        )
        if not is_hardware_project(title, summary_text):
            continue
        url = normalize_url(f"/{str(path).lstrip('/')}", "oshwhub")
        if url and url not in seen_urls:
            seen_urls.add(url)
            results.append(Candidate("oshwhub", uuid, title, url, {"uuid": uuid, "path": path}))
    return results

def get_project_details(session: requests.Session, candidate: Candidate) -> dict[str, Any]:
    """Fetch detailed content for a given project."""
    if candidate.source == "instructables":
        payload = request_json(session, "GET", "https://www.instructables.com/json-api/showInstructableModel", params={"urlString": candidate.extra["slug"]})
        text_parts = [str(payload.get("title") or candidate.title)]
        image_urls = []
        cover_image = payload.get("coverImage") or {}
        if isinstance(cover_image, dict) and cover_image.get("downloadUrl"):
            image_urls.append(normalize_url(cover_image.get("downloadUrl")))
        for step in payload.get("steps", []):
            if step.get("title"): text_parts.append(step["title"])
            if step.get("body"): text_parts.append(html_to_text(step["body"]))
            for f in step.get("files", []):
                if f.get("downloadUrl"): image_urls.append(normalize_url(f["downloadUrl"]))
        return {
            "source": "instructables",
            "title": payload.get("title") or candidate.title,
            "url": normalize_url(payload.get("showUrl") or f"/{candidate.extra['slug']}/", "instructables") or candidate.url,
            "text": "\n".join([p for p in text_parts if p]).strip(),
            "images": list(dict.fromkeys([u for u in image_urls if u])),
        }
    else:
        payload = request_json(session, "GET", f"https://oshwhub.com/api/project/{candidate.extra['uuid']}")
        res = payload.get("result", {})
        title = (res.get("name") or candidate.title).strip()
        intro = res.get("introduction") or ""
        content_md = res.get("content") or ""
        url = candidate.url
        images = []
        for k in ("thumb", "cover"):
            u = normalize_url(res.get(k), "oshwhub")
            if u: images.append(u)
        images.extend([normalize_url(u, "oshwhub") for u in extract_markdown_image_urls(content_md) if normalize_url(u, "oshwhub")])
        try:
            page_html = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT).text
            images.extend(extract_oshwhub_page_image_urls(page_html))
        except: pass
        return {
            "source": "oshwhub",
            "title": title,
            "url": url,
            "text": f"{title}\n{intro}\n{markdown_to_text(content_md)}".strip(),
            "images": list(dict.fromkeys([u for u in images if u])),
        }
