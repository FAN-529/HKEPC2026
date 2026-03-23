import requests
import pandas as pd
import re
import random
from typing import Dict, List, Tuple

# ========== 配置 ==========
API_KEY = "c1155c4c176d686cf2bf5695cf88597b7d2758dd6867103683a037cc465ec8be"          # 替换为真实密钥
API_URL = "https://serpapi.com/search"

# ========== 用户输入 ==========
print("🏨 香港高评分酒店查询（评分 ≥ 4.3）")
location = input("请输入地点或区域（如：尖沙咀、中环、铜锣湾）：").strip()
check_in = input("入住日期（YYYY-MM-DD，例如 2026-04-01）：").strip()
check_out = input("退房日期（YYYY-MM-DD，例如 2026-04-03）：").strip()

# 确保日期格式为 YYYY-MM-DD
from datetime import datetime
try:
    check_in = datetime.strptime(check_in, "%Y-%m-%d").strftime("%Y-%m-%d")
    check_out = datetime.strptime(check_out, "%Y-%m-%d").strftime("%Y-%m-%d")
except ValueError:
    print("日期格式错误，请使用 YYYY-MM-DD 格式。")
    exit()

# ========== 调用 API ==========
params = {
    "engine": "google_hotels",
    "q": f"{location} 香港",            # 搜索关键词（可加上“酒店”）
    "hl": "zh-CN",                      # 语言
    "gl": "hk",                         # 地区
    "currency": "HKD",                  # 货币（重要：之前写成了ccy）
    "check_in_date": check_in,
    "check_out_date": check_out,
    "adults": 1,
    "api_key": API_KEY
}

print("\n正在搜索酒店，请稍候...")
try:
    response = requests.get(API_URL, params=params)
    data = response.json()
    if "error" in data:
        print(f"❌ API 错误: {data['error']}")
        exit()
except Exception as e:
    print(f"❌ API 请求失败：{e}")
    exit()

# ========== 解析结果 ==========
hotels = []

# 处理 properties（普通结果）
if "properties" in data:
    for prop in data["properties"]:
        # 只保留有评分且评分 >= 4.3 的酒店
        if "overall_rating" not in prop or prop["overall_rating"] is None:
            continue
        rating = prop["overall_rating"]
        if rating < 4.3:
            continue

        name = prop.get("name", "未知名称")
        description = prop.get("description", "")
        # 地址：从 nearby_places 提取地标，或使用 GPS
        if "nearby_places" in prop and prop["nearby_places"]:
            address = "附近地标：" + ", ".join([p.get("name", "") for p in prop["nearby_places"][:3]])
        else:
            gps = prop.get("gps_coordinates", {})
            address = f"GPS: {gps.get('latitude')}, {gps.get('longitude')}" if gps else "地址信息未提供"
        # 价格：rate_per_night 中可能有 lowest 字段
        price_info = prop.get("rate_per_night", {})
        price = price_info.get("lowest", "暂无")
        hotel_class = prop.get("extracted_hotel_class", 0)
        eco_certified = prop.get("eco_certified", False)

        hotels.append({
            "名称": name,
            "地址": address,
            "评分": rating,
            "评论数": prop.get("reviews", 0),
            "价格(HKD)": price,
            "星级": hotel_class,
            "环保认证": "是" if eco_certified else "否",
            "描述": description
        })

# 处理 ads（赞助酒店）
if "ads" in data:
    for ad in data["ads"]:
        if "overall_rating" not in ad or ad["overall_rating"] is None:
            continue
        rating = ad["overall_rating"]
        if rating < 4.3:
            continue

        name = ad.get("name", "未知名称")
        gps = ad.get("gps_coordinates", {})
        address = f"GPS: {gps.get('latitude')}, {gps.get('longitude')}" if gps else "地址信息未提供"
        price = ad.get("price", "暂无")
        hotel_class = ad.get("hotel_class", 0)

        hotels.append({
            "名称": name,
            "地址": address,
            "评分": rating,
            "评论数": ad.get("reviews", 0),
            "价格(HKD)": price,
            "星级": hotel_class,
            "环保认证": "否",
            "描述": ""
        })

# ========== 输出结果 ==========
if not hotels:
    print(f"\n在 {location} 附近未找到评分 ≥ 4.3 的酒店。")
else:
    # 按评分从高到低排序
    hotels_sorted = sorted(hotels, key=lambda x: x["评分"], reverse=True)

    print(f"\n找到 {len(hotels_sorted)} 家评分 ≥ 4.3 的酒店：\n")
    for idx, h in enumerate(hotels_sorted, 1):
        print(f"{idx}. 🏨 {h['名称']}")
        print(f"   评分：{h['评分']} ⭐ ({h['评论数']} 条评论)")
        print(f"   价格：{h['价格(HKD)']} / 晚")
        print(f"   地址：{h['地址']}")
        if h['星级']:
            print(f"   星级：{h['星级']} 星")
        if h['环保认证'] == "是":
            print(f"   🌱 环保认证酒店：已获得环保认证")
        if h['描述']:
            print(f"   简介：{h['描述'][:100]}...")
        print("-" * 50)

    # 可持续小贴士
    print("\n💡 可持续住宿小贴士：")
    print("   • 选择评分高且评论数多的酒店，服务更可靠。")
    print("   • 优先选择有环保认证的酒店，支持绿色旅游。")
    print("   • 考虑步行或公共交通可达的酒店，减少出行碳排放。")
    print("   • 入住期间重复使用毛巾、减少一次性用品消耗。")