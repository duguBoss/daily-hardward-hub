"""Premium HTML rendering for WeChat hardware articles."""
from __future__ import annotations
import re
from html import escape
from typing import Any

from bs4 import BeautifulSoup
from .config import HEADER_IMG

def ensure_wxhtml(
    wxhtml: str,
    title: str,
    summary: str,
    detail: dict[str, Any],
) -> str:
    """Refine generated HTML with a premium tech-focused theme."""
    body = (wxhtml or "").strip()
    if not body:
        body = (
            f"<h2 style='font-size:18px;font-weight:600;color:#0f172a;margin:28px 0 12px 0;border-bottom:1px solid #e2e8f0;padding-bottom:6px;'>{escape(detail['title'])} 硬件赏析</h2>"
            "<p style='margin:0 0 16px;color:#334155;font-size:16px;line-height:1.7;'>这是一款值得硬件发烧友深度研究的项目，兼具实用性与工程美学。</p>"
        )

    # Clean residual script/html tags from AI output
    body = re.sub(r"<script[\s\S]*?</script>", "", body, flags=re.I)
    body = re.sub(r"</?(html|head|body)[^>]*>", "", body, flags=re.I)

    # Ensure minimum content padding if too short
    text_len = len(BeautifulSoup(body, "html.parser").get_text(" ", strip=True))
    if text_len < 800:
        body += (
            "<h2 style='font-size:18px;font-weight:600;color:#0f172a;margin:28px 0 12px 0;border-bottom:1px solid #e2e8f0;padding-bottom:6px;'>🛠 建议复现方案</h2>"
            "<p style='margin:0 0 16px;color:#334155;font-size:16px;line-height:1.7;'>建议按以下优先级体验和研究：<br><strong style='color:#0369a1;'>1. 极速验证：</strong> 优先复现核心逻辑板，用最小场景验证功能闭环。<br><strong style='color:#0369a1;'>2. 模块迁移：</strong> 观察其电路设计中的抗干扰及电源优化，直接迁移到你自己的项目。<br><strong style='color:#0369a1;'>3. 结构打样：</strong> 结合 3D 打印或 CNC 结构件建议，体验完整的工业设计落地感。</p>"
        )

    website_block = (
        f"<section style='margin-top:32px;padding:20px;background-color:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;'>"
        f"<p style='margin:0 0 12px 0;font-size:16px;color:#0f172a;font-weight:600;'>🌍 项目源码直达：</p>"
        f"<p style='margin:0;color:#0284c7;font-size:14px;word-break:break-all;line-height:1.5;'>{escape(detail['url'])}</p>"
        f"<p style='margin:12px 0 0;color:#64748b;font-size:12px;'>温馨提示：微信内无法直接点击，请复制链接后在浏览器中打开。</p>"
        f"</section>"
    )
    
    # Intelligence summary block
    summary_block = (
        "<section style='margin:28px 0;padding:16px 20px;background-color:#f1f5f9;border-radius:8px;border-left:5px solid #0369a1;'>"
        "<p style='margin:0;color:#1e293b;font-size:15px;line-height:1.7;font-weight:500;'>"
        f"<span style='color:#0369a1;font-weight:600;margin-right:8px;'>核心点评：</span>"
        f"{escape(summary)}</p>"
        "</section>"
    )

    # Wrap the entire article cleanly without boxy constraints
    return (
        "<section style=\"font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif;font-size:16px;color:#1e293b;line-height:1.8;background-color:#fff;text-align:justify;word-wrap:break-word;\">"
        # Header Graphic
        f"<section style=\"width:100%;margin-bottom:32px;\">"
        f"<img src=\"{HEADER_IMG}\" style=\"width:100%;display:block;border-radius:12px;\" alt=\"Header Image\"/>"
        "</section>"
        
        # Meta info
        "<section style=\"margin-bottom:24px;\">"
        f"<h1 style=\"color:#0f172a;font-size:24px;font-weight:700;line-height:1.4;margin:0 0 16px 0;letter-spacing:-0.5px;\">{escape(title)}</h1>"
        f"<section style=\"display:flex;gap:8px;align-items:center;\">"
        f"<span style=\"display:inline-block;padding:2px 10px;background-color:#dbeafe;color:#1e3a8a;font-size:12px;font-weight:600;border-radius:4px;letter-spacing:0.5px;\">HARDWARE</span>"
        f"<span style=\"display:inline-block;padding:2px 10px;background-color:#f1f5f9;color:#475569;font-size:12px;font-weight:500;border-radius:4px;\">开源周刊</span>"
        "</section>"
        "</section>"
        
        f"{summary_block}"
        f"{body}"
        f"{website_block}"
        
        # Footer
        "<section style='margin-top:40px;text-align:center;padding:24px 0;border-top:1px solid #f1f5f9;'>"
        "<p style='margin:0;color:#94a3b8;font-size:12px;'>聚焦开源硬件与工程美学 · 每天一个好项目</p>"
        "</section>"
        "</section>"
    )
