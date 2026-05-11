import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

# ========== 配置 ==========
SERPAPI_API_KEY = os.getenv(
    "SERPAPI_API_KEY",
    "-",
)
API_URL = "https://serpapi.com/search"

DEFAULT_MIN_RATING = 4.3
DEFAULT_ADULTS = 1
DEFAULT_CURRENCY = "HKD"

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _try_parse_date(date_str: str) -> Optional[str]:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return None


def parse_location_and_dates(user_query: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    从自然语言中尽量提取 location / check_in / check_out。
    若缺失则返回 None。
    """
    q = (user_query or "").strip()
    if not q:
        return None, None, None

    dates = _DATE_RE.findall(q)
    check_in = _try_parse_date(dates[0]) if len(dates) >= 1 else None
    check_out = _try_parse_date(dates[1]) if len(dates) >= 2 else None

    # 1) 优先用“在X附近/在X”的模式
    m = re.search(r"在\s*([^，,。]+?)(?:附近|周边|的酒店|酒店|旅馆|住宿)", q)
    location = m.group(1).strip() if m else None

    # 2) 如果没命中，再用“X的酒店”模式
    if not location:
        m = re.search(r"([^，,。]+?)\s*的\s*(?:酒店|旅馆|住宿)", q)
        location = m.group(1).strip() if m else None

    # 3) 最后兜底：移除日期和一些关键词，剩余当作 location
    if not location:
        q_no_dates = _DATE_RE.sub("", q).strip()
        for kw in ["香港", "酒店", "旅馆", "住宿", "高评分", "评分", "入住", "退房", "check_in", "check_out", "≥", "4.3", "附近", "周边", "推荐", "帮我", "给我"]:
            q_no_dates = q_no_dates.replace(kw, "").strip()
        location = q_no_dates if q_no_dates else None

    return location, check_in, check_out


def search_hotels(
    location: str,
    check_in: str,
    check_out: str,
    min_rating: float = DEFAULT_MIN_RATING,
    adults: int = DEFAULT_ADULTS,
    currency: str = DEFAULT_CURRENCY,
    force_lang: str = None,
) -> List[Dict[str, Any]]:
    hl_map = {"SC": "zh-CN", "TC": "zh-HK", "EN": "en"}
    hl = hl_map.get(force_lang, "zh-CN")
    params = {
        "engine": "google_hotels",
        "q": f"{location} 香港",
        "hl": hl,
        "gl": "hk",
        "currency": currency,
        "check_in_date": check_in,
        "check_out_date": check_out,
        "adults": adults,
        "api_key": SERPAPI_API_KEY,
    }

    response = requests.get(API_URL, params=params, timeout=25)
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"API 错误: {data['error']}")

    hotels: List[Dict[str, Any]] = []

    # properties（普通结果）
    for prop in data.get("properties", []) or []:
        rating = prop.get("overall_rating")
        if rating is None or rating < min_rating:
            continue

        name = prop.get("name", "未知名称")
        description = prop.get("description", "")

        if prop.get("nearby_places"):
            address = "附近地标：" + ", ".join([p.get("name", "") for p in prop.get("nearby_places", [])[:3]])
        else:
            gps = prop.get("gps_coordinates", {}) or {}
            address = (
                f"GPS: {gps.get('latitude')}, {gps.get('longitude')}"
                if gps and (gps.get("latitude") or gps.get("longitude"))
                else "地址信息未提供"
            )

        price_info = prop.get("rate_per_night", {}) or {}
        price = price_info.get("lowest", "暂无")
        hotel_class = prop.get("extracted_hotel_class", 0)
        eco_certified = prop.get("eco_certified", False)

        hotels.append(
            {
                "名称": name,
                "地址": address,
                "评分": rating,
                "评论数": prop.get("reviews", 0),
                "价格(HKD)": price,
                "星级": hotel_class,
                "环保认证": "是" if eco_certified else "否",
                "描述": description,
            }
        )

    # ads（赞助酒店）
    for ad in data.get("ads", []) or []:
        rating = ad.get("overall_rating")
        if rating is None or rating < min_rating:
            continue

        name = ad.get("name", "未知名称")
        gps = ad.get("gps_coordinates", {}) or {}
        address = (
            f"GPS: {gps.get('latitude')}, {gps.get('longitude')}"
            if gps and (gps.get("latitude") or gps.get("longitude"))
            else "地址信息未提供"
        )

        hotels.append(
            {
                "名称": name,
                "地址": address,
                "评分": rating,
                "评论数": ad.get("reviews", 0),
                "价格(HKD)": ad.get("price", "暂无"),
                "星级": ad.get("hotel_class", 0),
                "环保认证": "否",
                "描述": "",
            }
        )

    return hotels


def format_hotels(hotels: List[Dict[str, Any]], location: str, min_rating: float = DEFAULT_MIN_RATING, force_lang: str = None) -> str:
    if force_lang == "EN":
        if not hotels:
            return f"No hotels found near {location} with rating >= {min_rating}."
        hotels_sorted = sorted(hotels, key=lambda x: x.get("评分", 0), reverse=True)
        lines: List[str] = []
        lines.append(f"**Found {len(hotels_sorted)} hotels with rating >= {min_rating}:**")
        lines.append("")
        for idx, h in enumerate(hotels_sorted, 1):
            lines.append(f"{idx}. Hotel: {h.get('名称', 'Unknown')}")
            lines.append(f"   Rating: {h.get('评分', 'N/A')} (Reviews: {h.get('评论数', 0)})")
            lines.append(f"   Price: {h.get('价格(HKD)', 'N/A')} / night")
            lines.append(f"   Address: {h.get('地址', 'Address not provided')}")
            if h.get("星级"): lines.append(f"   Class: {h.get('星级')} Star")
            if h.get("环保认证") == "是": lines.append("   Eco-certified: Yes")
            desc = h.get("描述") or ""
            if desc: lines.append(f"   Info: {desc[:100]}...")
            lines.append("")
        lines.append("\nSustainable accommodation tips:")
        lines.append("- Choose high-rated hotels for reliable service.")
        lines.append("- Prioritize eco-certified hotels to support green tourism.")
        lines.append("- Consider hotels accessible by walking or public transport.")
        lines.append("- Reuse towels and reduce disposable items during your stay.")
        return "\n".join(lines).strip()
    
    elif force_lang == "TC":
        if not hotels:
            return f"喺 {location} 附近搵唔到評分 >= {min_rating} 嘅酒店。"
        hotels_sorted = sorted(hotels, key=lambda x: x.get("评分", 0), reverse=True)
        lines: List[str] = []
        lines.append(f"**搵到 {len(hotels_sorted)} 間評分 >= {min_rating} 嘅酒店：**")
        lines.append("")
        for idx, h in enumerate(hotels_sorted, 1):
            lines.append(f"{idx}. 酒店：{h.get('名稱', h.get('名称', '未知'))}")
            lines.append(f"   評分：{h.get('评分', 'N/A')}（評論數：{h.get('评论数', 0)}）")
            lines.append(f"   價格：{h.get('价格(HKD)', '暫無')} / 晚")
            lines.append(f"   地址：{h.get('地址', '地址資訊未提供')}")
            if h.get("星级"): lines.append(f"   星級：{h.get('星级')} 星")
            if h.get("环保认证") == "是": lines.append("   環保認證酒店：已獲得環保認證")
            desc = h.get("描述") or ""
            if desc: lines.append(f"   簡介：{desc[:100]}...")
            lines.append("")
        lines.append("\n可持續住宿小貼士：")
        lines.append("• 選擇評分高且評論數多嘅酒店，服務更可靠。")
        lines.append("• 優先選擇有環保認證嘅酒店，支持綠色旅遊。")
        lines.append("• 考慮步行或者公共交通可達嘅酒店，減少出行碳排放。")
        lines.append("• 入住期間重複使用毛巾、減少一次性用品消耗。")
        return "\n".join(lines).strip()

    else:
        if not hotels:
            return f"在 {location} 附近未找到评分 >= {min_rating} 的酒店。"
        hotels_sorted = sorted(hotels, key=lambda x: x.get("评分", 0), reverse=True)
        lines: List[str] = []
        lines.append(f"**找到 {len(hotels_sorted)} 家评分 >= {min_rating} 的酒店：**")
        lines.append("")
        for idx, h in enumerate(hotels_sorted, 1):
            lines.append(f"{idx}. 酒店：{h.get('名称', '未知名称')}")
            lines.append(f"   评分：{h.get('评分', 'N/A')}（评论数：{h.get('评论数', 0)}）")
            lines.append(f"   价格：{h.get('价格(HKD)', '暂无')} / 晚")
            lines.append(f"   地址：{h.get('地址', '地址信息未提供')}")
            if h.get("星级"): lines.append(f"   星级：{h.get('星级')} 星")
            if h.get("环保认证") == "是": lines.append("   环保认证酒店：已获得环保认证")
            desc = h.get("描述") or ""
            if desc: lines.append(f"   简介：{desc[:100]}...")
            lines.append("-" * 50)
        lines.append("\n可持续住宿小贴士：")
        lines.append("• 选择评分高且评论数多的酒店，服务更可靠。")
        lines.append("• 优先选择有环保认证的酒店，支持绿色旅游。")
        lines.append("• 考虑步行或公共交通可达的酒店，减少出行碳排放。")
        lines.append("• 入住期间重复使用毛巾、减少一次性用品消耗。")
        return "\n".join(lines).strip()


def handle_query(user_query: str, force_lang: str = None) -> str:
    """
    统一给主程序调用的入口。
    返回值：用于展示的字符串。
    """
    location, check_in, check_out = parse_location_and_dates(user_query)

    if not location:
        return "请告诉我你想查的地点或区域（例如：尖沙咀、中环、铜锣湾），以及入住/退房日期（YYYY-MM-DD）。"
    if not check_in or not check_out:
        return f"请补充入住/退房日期（YYYY-MM-DD）。当前识别：位置={location}，入住={check_in or '缺失'}，退房={check_out or '缺失'}。"

    try:
        hotels = search_hotels(
            location=location,
            check_in=check_in,
            check_out=check_out,
            min_rating=DEFAULT_MIN_RATING,
            force_lang=force_lang,
        )
        return format_hotels(hotels, location=location, min_rating=DEFAULT_MIN_RATING, force_lang=force_lang)
    except Exception as e:
        return f"酒店查询失败：{e}"

