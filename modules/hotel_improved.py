import os
import io
import re
import random
import contextlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

# ========== 配置 ==========
API_KEY = "-"  # 替换为真实密钥
API_URL = "https://serpapi.com/search"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.path.join(PROJECT_ROOT, "data", "licensed_hotels_and_guesthouses.csv")

# 香港全部地区（用于 AI Mode 解析）
ALL_HK_REGIONS = [
    "中西区", "中环", "上环", "金钟", "半山", "西环", "坚尼地城",
    "湾仔", "铜锣湾", "跑马地", "天后",
    "东区", "北角", "鲗鱼涌", "太古", "筲箕湾", "柴湾",
    "南区", "香港仔", "鸭脷洲", "黄竹坑", "薄扶林", "赤柱",
    "油尖旺", "尖沙咀", "油麻地", "旺角", "太子",
    "深水埗", "长沙湾", "荔枝角", "石硖尾",
    "九龙城", "九龙塘", "土瓜湾", "红磡", "启德",
    "黄大仙", "新蒲岗", "慈云山",
    "观塘", "牛头角", "蓝田", "将军澳",
    "葵青", "葵涌", "青衣",
    "荃湾",
    "屯门",
    "元朗", "天水围",
    "北区", "上水", "粉岭",
    "大埔",
    "沙田", "马鞍山", "大围",
    "西贡", "清水湾", "西贡市中心",
    "离岛", "大屿山", "梅窝", "东涌", "长洲", "南丫岛", "坪洲"
]

# 偏好关键词（用于排序）
PREF_KEYWORDS = ["安静", "环保", "经济", "便宜", "豪华", "舒适", "方便", "干净", "卫生", "服务好", "有早餐", "评分高", "高评分", "高星", "五星"]

# ========== 1. 加载本地 CSV ==========
def load_local_hotels(csv_path: str) -> pd.DataFrame:
    encodings = ['utf-8', 'gbk', 'big5', 'latin1']
    for enc in encodings:
        try:
            df = pd.read_csv(csv_path, encoding=enc)
            print(f"✅ 成功加载本地酒店数据，使用编码：{enc}")
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"❌ 读取文件出错：{e}")
            raise
    raise FileNotFoundError(f"❌ 无法读取本地文件，请检查文件路径：{csv_path}")


_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _try_parse_date(date_str: str) -> Optional[str]:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return None


def extract_dates_from_query(user_query: str) -> Tuple[Optional[str], Optional[str]]:
    """
    从文本中提取前两个 YYYY-MM-DD：
    - check_in：第一个日期
    - check_out：第二个日期
    """
    if not user_query:
        return None, None
    dates = _DATE_RE.findall(user_query)
    check_in = _try_parse_date(dates[0]) if len(dates) >= 1 else None
    check_out = _try_parse_date(dates[1]) if len(dates) >= 2 else None
    return check_in, check_out

# ========== 2. 用 Google AI Mode 解析用户需求 ==========
def parse_user_query(query: str) -> tuple:
    """
    先用简单规则提取地点和偏好，必要时调用 AI Mode 增强。
    返回 (地点, [偏好关键词])
    """
    # 先尝试从用户输入中直接匹配地点（快速）
    location = None
    for region in ALL_HK_REGIONS:
        if region in query:
            location = region
            break

    # 提取偏好关键词（从用户输入中）
    preferences = []
    for kw in PREF_KEYWORDS:
        if kw in query:
            preferences.append(kw)

    # 如果地点或偏好都不明确，调用 AI Mode 增强解析
    if location is None or not preferences:
        params = {
            "engine": "google_ai_mode",
            "q": f"香港酒店 {query}",
            "hl": "zh-CN",
            "gl": "hk",
            "api_key": API_KEY
        }
        try:
            resp = requests.get(API_URL, params=params)
            data = resp.json()
            text_blocks = data.get("text_blocks", [])
            combined_text = " ".join([block.get("snippet", "") for block in text_blocks])
            full_text = query + " " + combined_text

            if location is None:
                for region in ALL_HK_REGIONS:
                    if region in full_text:
                        location = region
                        break

            if not preferences:
                for kw in PREF_KEYWORDS:
                    if kw in full_text:
                        preferences.append(kw)
        except Exception as e:
            print(f"⚠️ AI Mode 调用失败：{e}，将使用简单规则解析")
    return location, preferences

# ========== 3. 调用 Google Hotels API 获取酒店列表（带评分和价格） ==========
def search_hotels_by_api(location: str, check_in: str, check_out: str) -> list:
    """
    使用 Google Hotels API 搜索酒店，返回包含名称、评分、价格、酒店类别的列表。
    """
    if not location:
        print("⚠️ 未识别到明确地点，无法使用 Hotels API 搜索。")
        return []

    params = {
        "engine": "google_hotels",
        "q": f"{location} 香港",
        "hl": "zh-CN",
        "gl": "hk",
        "currency": "HKD",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "adults": 1,
        "api_key": API_KEY
    }

    print("\n正在通过 Google Hotels API 搜索...")
    try:
        resp = requests.get(API_URL, params=params)
        data = resp.json()
        if "error" in data:
            print(f"❌ API 错误: {data['error']}")
            return []
    except Exception as e:
        print(f"❌ API 请求失败：{e}")
        return []

    hotels = []
    # 处理 properties
    for prop in data.get("properties", []):
        if "overall_rating" not in prop or prop["overall_rating"] is None:
            continue
        rating = prop["overall_rating"]
        # 保留所有有评分的酒店（后续可根据偏好筛选）
        name = prop.get("name", "")
        price_info = prop.get("rate_per_night", {})
        price = price_info.get("lowest", "暂无")
        hotel_class = prop.get("extracted_hotel_class", 0)
        hotels.append({
            "name": name,
            "rating": rating,
            "reviews": prop.get("reviews", 0),
            "price": price,
            "hotel_class": hotel_class,
            "eco_certified": prop.get("eco_certified", False)
        })
    # 处理 ads（赞助酒店）
    for ad in data.get("ads", []):
        if "overall_rating" not in ad or ad["overall_rating"] is None:
            continue
        rating = ad["overall_rating"]
        name = ad.get("name", "")
        price = ad.get("price", "暂无")
        hotel_class = ad.get("hotel_class", 0)
        hotels.append({
            "name": name,
            "rating": rating,
            "reviews": ad.get("reviews", 0),
            "price": price,
            "hotel_class": hotel_class,
            "eco_certified": False
        })

    return hotels

# ========== 4. 从本地 CSV 中匹配详细信息 ==========
def enrich_with_local_info(hotels_from_api: list, local_df: pd.DataFrame) -> list:
    """
    用酒店名称在本地 CSV 中匹配，补充地址、电话、邮箱。
    匹配策略：优先匹配中文名称，次选英文名称。
    """
    for h in hotels_from_api:
        name = h["name"]
        # 在本地 CSV 中查找
        # 先尝试匹配场所名称（中文）
        mask = local_df['場所名稱'].str.contains(name, na=False, case=False)
        if mask.any():
            row = local_df[mask].iloc[0]
            h["address"] = row['場所地址'] if pd.notna(row['場所地址']) else row['Premises Address']
            h["phone"] = row['Premises Phone No.'] if pd.notna(row['Premises Phone No.']) else "暂无"
            h["email"] = row['Premises Email Address'] if pd.notna(row['Premises Email Address']) else "暂无"
        else:
            # 再尝试匹配英文名称
            mask = local_df['Premises Name'].str.contains(name, na=False, case=False)
            if mask.any():
                row = local_df[mask].iloc[0]
                h["address"] = row['場所地址'] if pd.notna(row['場所地址']) else row['Premises Address']
                h["phone"] = row['Premises Phone No.'] if pd.notna(row['Premises Phone No.']) else "暂无"
                h["email"] = row['Premises Email Address'] if pd.notna(row['Premises Email Address']) else "暂无"
            else:
                # 没匹配到，用 API 中的信息（可能不完整）
                h["address"] = "（未在本地数据中找到详细地址）"
                h["phone"] = "暂无"
                h["email"] = "暂无"
    return hotels_from_api

# ========== 5. 根据偏好排序 ==========
def sort_hotels_by_preference(hotels: list, preferences: list) -> list:
    """
    根据偏好排序：便宜 -> 按价格升序（将价格转为数值）；评分高 -> 按评分降序。
    """
    if not hotels:
        return hotels

    if any(kw in preferences for kw in ["便宜", "经济"]):
        # 提取价格数值
        for h in hotels:
            price_str = h["price"]
            # 提取数字（例如 "HKD 500" 或 "$500" 或 "500"）
            num = re.search(r'(\d+(?:,\d+)?(?:\.\d+)?)', price_str)
            h["price_num"] = float(num.group(1).replace(',', '')) if num else float('inf')
        hotels_sorted = sorted(hotels, key=lambda x: x.get("price_num", float('inf')))
    elif any(kw in preferences for kw in ["评分高", "高评分"]):
        hotels_sorted = sorted(hotels, key=lambda x: x.get("rating", 0), reverse=True)
    else:
        # 默认按评分降序
        hotels_sorted = sorted(hotels, key=lambda x: x.get("rating", 0), reverse=True)
    return hotels_sorted

# ========== 6. 输出结果 ==========
def _get_hotel_labels(lang_code: str) -> Dict[str, str]:
    lang = (lang_code or "").upper().strip() or "SC"
    labels = {
        "SC": {
            "loc": "地点", "pref": "偏好", "found": "找到", "sorted": "已按偏好排序",
            "addr": "地址", "phone": "电话", "email": "邮箱", "rating": "评分",
            "reviews": "条评论", "price": "价格", "star": "星级", "eco": "环保认证", "yes": "是",
            "tips_title": "可持续住宿小贴士",
            "traffic_mtr": "该区域地铁、巴士发达，建议使用公共交通。",
            "traffic_ferry": "前往离岛需乘船，建议提前查询航班时间。",
            "local_title": "本地酒店列表（无房价/评分）",
            "local_note": "缺少入住/退房日期时，本页面仅展示本地数据（不调用第三方酒店 API）。",
            "h_name": "酒店", "night": "晚", "eco_tip": "优先选择已知有环保实践的酒店，并减少一次性用品。",
            "quiet_tip": "选择高楼层或远离主干道的房间，可能更安静。",
            "econ_tip": "选择经济型住宿，减少资源消耗。",
            "tip_eco_msg": "推荐理由：您偏好环保酒店，入住时可主动减少一次性用品消耗。",
            "transport_title": "交通提示"
        },
        "TC": {
            "loc": "地點", "pref": "偏好", "found": "搵到", "sorted": "已按偏好排序",
            "addr": "地址", "phone": "電話", "email": "電郵", "rating": "評分",
            "reviews": "條評論", "price": "價格", "star": "星級", "eco": "環保認證", "yes": "是",
            "tips_title": "可持續住宿小貼士",
            "traffic_mtr": "呢個區域地鐵、巴士好發達，建議使用公共交通工具。",
            "traffic_ferry": "去離島要搭船，建議提早查定船期。",
            "local_title": "本地酒店列表（無房價/評分）",
            "local_note": "缺少入住/退房日期時，本頁面僅展示本地數據（不調用第三方酒店 API）。",
            "h_name": "酒店", "night": "晚", "eco_tip": "優先選擇已知有環保實踐嘅酒店，並減少一次性用品。",
            "quiet_tip": "選擇高樓層或者避開大馬路嘅客房，可能會安靜啲。",
            "econ_tip": "選擇經濟型住宿，減少資源消耗。",
            "tip_eco_msg": "推薦理由：您偏好環保酒店，入住時可以主動減少一次性用品消耗。",
            "transport_title": "交通提示"
        },
        "EN": {
            "loc": "Location", "pref": "Preferences", "found": "Found", "sorted": "sorted by preference",
            "addr": "Address", "phone": "Phone", "email": "Email", "rating": "Rating",
            "reviews": "reviews", "price": "Price", "star": "Star", "eco": "Eco-certified", "yes": "Yes",
            "tips_title": "Sustainable Accommodation Tips",
            "traffic_mtr": "Public transport is highly developed in this area; using MTR or buses is recommended.",
            "traffic_ferry": "Ferry service is required for outlying islands; please check schedules in advance.",
            "local_title": "Local hotel list (no price)",
            "local_note": "When check-in/out dates are missing, only local data is shown (no external API calls).",
            "h_name": "Hotel", "night": "night", "eco_tip": "Prioritize hotels known for sustainable practices and reduce single-use items.",
            "quiet_tip": "Choosing higher floors or rooms away from main roads may be quieter.",
            "econ_tip": "Choosing economy accommodation helps reduce resource consumption.",
            "tip_eco_msg": "Reason: You prefer eco-friendly hotels; please consider reducing single-use items during your stay.",
            "transport_title": "Transport Tips"
        }
    }
    return labels.get(lang, labels["SC"])

def display_hotels(hotels: list, location: str, preferences: list, force_lang: Optional[str] = None):
    L = _get_hotel_labels(force_lang)
    if not hotels:
        print(f"\n😞 {L['found']} 0 {'hotels' if force_lang=='EN' else '家酒店'} @ '{location}'.")
        return

    print(f"\n📍 {L['loc']}：{location if location else '---'}")
    print(f"🎯 {L['pref']}：{preferences if preferences else '---'}")
    
    found_text = f"**🏨 {L['found']} {len(hotels)} {'hotels' if force_lang=='EN' else '家酒店'}（{L['sorted']}）：**"
    print(found_text + "\n")

    for idx, h in enumerate(hotels[:10], 1):   # 只显示前10个
        print(f"{idx}. 🏨 {h['name']}")
        print(f"   {L['addr']}：{h['address']}")
        print(f"   {L['phone']}：{h['phone']}")
        print(f"   {L['email']}：{h['email']}")
        print(f"   ⭐ {L['rating']}：{h['rating']}/5.0 ({h['reviews']} {L['reviews']})")
        print(f"   💰 {L['price']}：{h['price']} / {L['night']}")
        if h.get('hotel_class'):
            print(f"   {L['star']}：{h['hotel_class']} {'Star' if force_lang=='EN' else L['star']}")
        if h.get('eco_certified'):
            print(f"   🌱 {L['eco']}：{L['yes']}")
        
        # 偏好提示
        if "环保" in preferences or "Eco" in preferences:
            print(f"   🌱 {L['tip_eco_msg']}")
        elif "安静" in preferences or "Quiet" in preferences:
            print(f"   🌱 {L['quiet_tip']}")
        elif any(k in preferences for k in ["经济", "便宜", "Economic", "Cheap"]):
            print(f"   🌱 {L['econ_tip']}")

        # 区域交通提示
        if location in ["尖沙咀", "中环", "湾仔", "铜锣湾", "Tsim Sha Tsui", "Central", "Wan Chai", "Causeway Bay"]:
            print(f"   🚇 {L['transport_title']}：{L['traffic_mtr']}")
        elif location in ["离岛", "大屿山", "长洲", "南丫岛", "Islands", "Lantau", "Cheung Chau", "Lamma Island"]:
            print(f"   ⛴️ {L['transport_title']}：{L['traffic_ferry']}")
        print("")

    print(f"\n💡 {L['tips_title']}：")
    if force_lang == "EN":
        print("   • Choose hotels with eco-certification (check official websites)")
        print("   • Prioritize walking, cycling, or public transport to the hotel")
        print("   • Reuse towels and reduce laundry to save water")
        print("   • Bring your own toiletries to reduce single-use plastic waste")
    elif force_lang == "TC":
        print("   • 選擇有環保認證嘅酒店（可以喺官網查下）")
        print("   • 優先行路、踩單車或者搭公共交通工具去酒店")
        print("   • 重複使用毛巾、減少洗衫次數，節約水資源")
        print("   • 自備洗漱用品，減少一次性塑膠垃圾")
    else:
        print("   • 选择有环保认证的酒店（可在官网查询）")
        print("   • 优先步行、骑行或使用公共交通前往酒店")
        print("   • 重复使用毛巾、减少洗衣次数，节约水资源")
        print("   • 自带洗漱用品，减少一次性塑料垃圾")


def display_local_hotels(local_df: pd.DataFrame, location: str, preferences: List[str], force_lang: Optional[str] = None):
    L = _get_hotel_labels(force_lang)
    if local_df is None or local_df.empty:
        print(f"\n😞 {L['found']} 0 {'hotels' if force_lang=='EN' else '家酒店'} @ '{location}'.")
        return

    print(f"\n📍 {L['local_title']}")
    print(f"   {L['loc']}：{location if location else '---'}")
    print(f"   {L['pref']}：{preferences if preferences else '---'}")
    print(f"\n   说明：{L['local_note']}")
    print("\n")

    # 限制输出数量
    top_n = min(10, len(local_df))
    for i in range(top_n):
        row = local_df.iloc[i]
        lang = (force_lang or "").upper()
        if lang == "EN":
            name = row.get("Premises Name", None) or "Unknown"
            address = row.get("Premises Address", None) or "Address not provided"
        else:
            name = row.get("場所名稱", None) or row.get("Premises Name", "未知名称")
            address = row.get("場所地址", None) or row.get("Premises Address", "地址信息未提供")

        phone = row.get("Premises Phone No.", None) or "暂无"
        email = row.get("Premises Email Address", None) or "暂无"

        print(f"{i+1}. {L['h_name']}：{name}")
        print(f"   {L['addr']}：{address}")
        print(f"   {L['phone']}：{phone}")
        print(f"   {L['email']}：{email}")

        if "环保" in preferences or "Eco" in preferences:
            print(f"   🌱 {L['eco_tip']}")
        elif "安静" in preferences or "Quiet" in preferences:
            print(f"   🌱 {L['quiet_tip']}")
        elif any(k in preferences for k in ["经济", "便宜", "Economic", "Cheap"]):
            print(f"   🌱 {L['econ_tip']}")
        print("")

# ========== 主程序 ==========
def main():
    print("🤖 香港可持续酒店助手")
    print("（基于 Google Hotels API + 本地政府数据）")
    user_input = input("\n请描述您想住的酒店（例如：尖沙咀附近安静、评分高的酒店）：").strip()
    if not user_input:
        print("❌ 请输入有效需求。")
        return

    # 1. 解析用户输入（得到地点和偏好）
    location, preferences = parse_user_query(user_input)

    # 2. 如果地点为空，则无法继续（也可以提示用户）
    if not location:
        print("❌ 未能识别出地点，请尝试输入更具体的区域名称（如尖沙咀、中环）。")
        return

    # 3. 让用户输入入住和退房日期（后续可优化为 AI 识别日期）
    print("\n请输入入住和退房日期（用于获取实时房价）：")
    check_in = input("入住日期（YYYY-MM-DD，例如 2026-04-01）：").strip()
    check_out = input("退房日期（YYYY-MM-DD，例如 2026-04-03）：").strip()
    from datetime import datetime
    try:
        check_in = datetime.strptime(check_in, "%Y-%m-%d").strftime("%Y-%m-%d")
        check_out = datetime.strptime(check_out, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        print("日期格式错误，请使用 YYYY-MM-DD 格式。")
        return

    # 4. 调用 Google Hotels API 获取酒店列表（带评分、价格）
    hotels_api = search_hotels_by_api(location, check_in, check_out)
    if not hotels_api:
        print("❌ 未从 Google Hotels API 获取到酒店数据。")
        return

    # 5. 加载本地 CSV 并匹配详细信息
    local_df = load_local_hotels(CSV_PATH)
    hotels_enriched = enrich_with_local_info(hotels_api, local_df)

    # 6. 根据偏好排序
    hotels_sorted = sort_hotels_by_preference(hotels_enriched, preferences)

    # 7. 显示结果
    display_hotels(hotels_sorted, location, preferences)

if __name__ == "__main__":
    main()


# -------------------------- 网页/路由可调用主入口 --------------------------
def handle_query(user_query: str, force_lang: str = None) -> str:
    """
    统一给主程序/网页路由调用的入口。
    返回值：用于展示的字符串（内部会捕获 print 输出）。
    """
    try:
        if not user_query or not user_query.strip():
            return "请描述你想找的酒店区域与需求（可附带入住/退房日期：YYYY-MM-DD）。"

        location, preferences = parse_user_query(user_query)
        if not location:
            return "请告诉我你想查的酒店地点/区域（例如：尖沙咀、中环、铜锣湾）。"

        check_in, check_out = extract_dates_from_query(user_query)

        # 1) 如果日期齐全：走原来的“API + 本地 enrich”流程
        if check_in and check_out:
            hotels_api = search_hotels_by_api(location, check_in, check_out)
            if not hotels_api:
                return f"未找到可用的酒店数据：{location}。"

            local_df = load_local_hotels(CSV_PATH)
            hotels_enriched = enrich_with_local_info(hotels_api, local_df)
            hotels_sorted = sort_hotels_by_preference(hotels_enriched, preferences)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                display_hotels(hotels_sorted, location, preferences, force_lang=force_lang)
            return buf.getvalue().strip()

        # 2) 如果缺少日期：仅展示本地酒店（不调用 Hotels API）
        local_df = load_local_hotels(CSV_PATH)

        # 先用繁体/中文地址字段过滤；找不到再用英文地址字段过滤
        mask_cn = local_df.get("場所地址", pd.Series([], dtype=str)).astype(str).str.contains(location, na=False)
        filtered = local_df[mask_cn] if mask_cn is not None else local_df
        if filtered.empty:
            mask_en = local_df.get("Premises Address", pd.Series([], dtype=str)).astype(str).str.contains(location, na=False)
            filtered = local_df[mask_en] if mask_en is not None else local_df

        filtered = filtered.head(10).copy()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            display_local_hotels(filtered, location, preferences, force_lang=force_lang)
        return buf.getvalue().strip()

    except Exception as e:
        return f"酒店查询失败：{e}"
