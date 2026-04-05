"""Candidate filtering for hardware-focused projects."""
from __future__ import annotations

from .utils import html_to_text


POSITIVE_KEYWORDS = (
    "arduino", "esp32", "esp8266", "raspberry pi", "robot", "robotics", "pcb",
    "electronics", "electronic", "iot", "home assistant", "sensor", "microcontroller",
    "3d print", "3d printer", "3d printed", "cnc", "laser cut", "firmware", "open source hardware",
    "maker", "hardware", "embedded", "automation", "smart home", "relay", "battery",
    "bluetooth", "wifi", "lora", "drone", "fpga", "stm32", "mcu", "keyboard", "display",
    "solder", "焊接", "电路", "电子", "硬件", "开源硬件", "单片机", "传感器", "物联网", "智能家居", "继电器",
    "机器人", "机械臂", "3d打印", "3d 打印", "打印机", "激光切割", "数控", "固件", "嵌入式", "自动化",
)

NEGATIVE_KEYWORDS = (
    "recipe", "food", "cake", "cookie", "bread", "pizza", "pasta", "sandwich", "salad",
    "dessert", "chocolate", "cook", "cooking", "baking", "kitchen", "drink", "coffee", "tea",
    "crochet", "knit", "knitting", "sewing", "embroidery", "soap", "candle", "jewelry",
    "bracelet", "earring", "necklace", "fashion", "makeup", "hairstyle", "origami",
    "食谱", "美食", "烘焙", "蛋糕", "面包", "甜点", "饼干", "料理", "做饭", "咖啡", "茶饮", "厨房",
    "编织", "钩针", "毛线", "缝纫", "刺绣", "首饰", "手链", "耳环", "项链", "蜡烛", "肥皂",
)


def _normalize_text(value: str) -> str:
    return " ".join((value or "").lower().replace("-", " ").replace("_", " ").split())


def is_hardware_project(title: str, text: str = "") -> bool:
    haystack = _normalize_text(f"{title}\n{text}")
    if not haystack:
        return False

    if any(keyword in haystack for keyword in NEGATIVE_KEYWORDS):
        return False

    return any(keyword in haystack for keyword in POSITIVE_KEYWORDS)


def build_instructables_candidate_text(document: dict) -> str:
    parts = [
        str(document.get("title") or ""),
        str(document.get("screenName") or ""),
        html_to_text(str(document.get("stepBody") or "")),
    ]
    return "\n".join(part for part in parts if part).strip()
