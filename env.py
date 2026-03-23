import requests
from fuzzywuzzy import process
import os
from openai import OpenAI

# -------------------------- 配置参数 --------------------------
client = OpenAI(api_key="sk-e3196140b13443c79b1e5e2c0393376b", base_url="https://api.deepseek.com")

RECYCLE_FEATURE_URL = "https://portal.csdi.gov.hk/server/rest/services/common/epd_rcd_1630899452408_9505/FeatureServer/0/query"
AIR_QUALITY_URL = "https://portal.csdi.gov.hk/server/rest/services/common/epd_rcd_1629267205214_40635/FeatureServer/0/query"

AREA_DISTRICT_MAP = {
    "葵青": "Kwai_Tsing", "葵青": "Kwai_Tsing",
    "屯门": "Tuen_Mun", "屯門": "Tuen_Mun",
    "沙田": "Sha_Tin", "沙田": "Sha_Tin",
    "元朗": "Yuen_Long", "元朗": "Yuen_Long",
    "中西区": "Central_and_Western", "中环": "Central_and_Western",
    "湾仔": "Wan_Chai", "灣仔": "Wan_Chai",
    "东区": "Eastern", "東區": "Eastern",
    "南区": "Southern", "南區": "Southern",
    "油尖旺": "Yau_Tsim_Mong", "尖沙咀": "Yau_Tsim_Mong", "旺角": "Yau_Tsim_Mong",
    "九龙城": "Kowloon_City", "九龍城": "Kowloon_City",
    "观塘": "Kwun_Tong", "觀塘": "Kwun_Tong",
    "黄大仙": "Wong_Tai_Sin", "黃大仙": "Wong_Tai_Sin",
    "深水埗": "Sham_Shui_Po",
    "荃湾": "Tsuen_Wan", "荃灣": "Tsuen_Wan",
    "北区": "North", "北區": "North",
    "大埔": "Tai_Po", "大埔": "Tai_Po",
    "西贡": "Sai_Kung", "西貢": "Sai_Kung",
    "离岛": "Islands", "離島": "Islands"
}
HK_AREAS = list(AREA_DISTRICT_MAP.keys())

# -------------------------- 核心功能函数 --------------------------
def get_deepseek_response(prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
    """调用DeepSeek API获取响应"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"调用DeepSeek API失败：{e}")
        return ""

def parse_user_query(query: str) -> str:
    """使用DeepSeek API提取用户查询中的目标区域"""
    prompt = f"从以下文本中提取香港的地区名称：'{query}'。只返回地区名称，不要包含其他任何文字。可选的地区包括：{', '.join(HK_AREAS)}"
    area = get_deepseek_response(prompt)
    
    """进行模糊匹配以确保返回的是有效区域"""
    if area:
        best_match = process.extractOne(area, HK_AREAS)
        if best_match and best_match[1] > 80:
            return best_match[0]
            
    """如果API调用失败或无法识别，回退到旧方法"""
    best_match = process.extractOne(query, HK_AREAS)
    if best_match and best_match[1] > 60:
        return best_match[0]
    for area_key in HK_AREAS:
        if area_key in query:
            return area_key
    return ""

def fetch_recycle_points(area: str) -> list:
    """获取指定区域的回收点数据"""
    district_id = AREA_DISTRICT_MAP.get(area)
    where_clause = f"district_id = '{district_id}'" if district_id else (
        f"address_sc LIKE '%25{area}%25' OR address_tc LIKE '%25{area}%25' OR address_en LIKE '%25{area}%25'"
    )

    params = {
        "where": where_clause,
        "outFields": "address_sc,address_tc,address_en",
        "f": "json",
        "returnGeometry": True,
        "resultRecordCount": 20
    }

    try:
        response = requests.get(RECYCLE_FEATURE_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        points = []
        for feature in data.get("features", []):
            attrs = feature["attributes"]
            geometry = feature.get("geometry", {})
            point = {
                "简体地址": attrs.get("address_sc") or "无",
                "繁体地址": attrs.get("address_tc") or "无",
                "英文地址": attrs.get("address_en") or "无",
                "y": geometry.get("y"),
                "x": geometry.get("x")
            }
            points.append(point)
        return points
    except Exception as e:
        print(f"回收点数据获取失败：{str(e)}")
        return []

def fetch_nearby_air_quality(rec_y: float, rec_x: float, max_dist: float = 20000) -> list:
    """获取回收点附近的空气质量监测站"""
    params = {
        "where": "1=1",
        "outFields": "NAME_TC,NAME_EN,ADDRESS_TC,ADDRESS_EN,NSEARCH05_TC,NSEARCH05_EN",
        "f": "json",
        "returnGeometry": True,
        "resultRecordCount": 100
    }
    try:
        resp = requests.get(AIR_QUALITY_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        stations = []
        for feat in data.get("features", []):
            attrs = feat["attributes"]
            geom = feat.get("geometry", {})
            stn_y, stn_x = geom.get("y"), geom.get("x")
            if stn_y is None or stn_x is None:
                continue
            dist = ((rec_y - stn_y)**2 + (rec_x - stn_x)**2)**0.5
            if dist <= max_dist:
                stations.append({
                    "繁体站点": attrs.get("NAME_TC") or "无",
                    "英文站点": attrs.get("NAME_EN") or "无",
                    "繁体地址": attrs.get("ADDRESS_TC") or "无",
                    "英文地址": attrs.get("ADDRESS_EN") or "无",
                    "繁体网站": attrs.get("NSEARCH05_TC") or "无",
                    "英文网站": attrs.get("NSEARCH05_EN") or "无",
                    "距离": round(dist, 2)
                })
        stations.sort(key=lambda x: x["距离"])
        return stations[:3]
    except Exception as e:
        print(f"空气质量数据获取失败：{str(e)}")
        return []

def display_results(points: list, area: str):
    """使用DeepSeek API生成并展示更自然的回复"""
    if not points:
        prompt = f"请告诉用户在香港的「{area}」区域未找到相关的回收点信息。"
        response = get_deepseek_response(prompt)
        print(f"\n智能助手：{response}")
        return

    details = f"在「{area}」找到了 {len(points)} 个回收点。\n"
    for i, p in enumerate(points, 1):
        details += f"\n回收点 {i}:\n"
        details += f"- 简体地址: {p['简体地址']}\n"
        details += f"- 繁体地址: {p['繁体地址']}\n"
        details += f"- 英文地址: {p['英文地址']}\n"
        
        if p['y'] and p['x']:
            air_data = fetch_nearby_air_quality(p['y'], p['x'], max_dist=20000)
            if air_data:
                details += f"  附近有 {len(air_data)} 个空气质量监测站:\n"
                for j, ap in enumerate(air_data, 1):
                    details += f"  - 监测站 {j}:\n"
                    details += f"    - 名称: {ap['繁体站点']} / {ap['英文站点']}\n"
                    details += f"    - 地址: {ap['繁体地址']}\n"
                    details += f"    - 距离: {ap['距离']}米\n"
            else:
                details += "  附近暂无空气质量监测数据。\n"
        else:
            details += "  无法获取位置信息，暂不展示空气质量数据。\n"

    system_prompt = "你是一个香港生活助手，你需要根据我提供的数据，以友好、清晰、有条理的方式回复用户。请使用中文（简体）。"
    prompt = f"这是我为你找到的信息，请整理并回复给用户：\n\n{details}"
    
    response = get_deepseek_response(prompt, system_prompt)
    print(f"\n智能助手：\n{response}")

# -------------------------- 交互主入口 --------------------------
def main():
    print("香港可持续发展设施查询系统 (智能版)")
    print("输入查询（如：「我想去屯門的垃圾回收处」），输入「退出」结束。\n")
    
    while True:
        user_input = input("你：")
        if user_input.lower() in ["退出", "exit", "quit"]:
            print("感谢使用！")
            break
        
        area = parse_user_query(user_input)
        if not area:
            prompt = "请告诉用户未能识别出有效的香港地区名称，并引导用户输入更明确的地点，例如'我想找铜锣湾的回收点'。"
            response = get_deepseek_response(prompt)
            print(f"智能助手：{response}")
            continue
        
        print(f"正在查询「{area}」的回收点及周边空气质量信息...")
        points = fetch_recycle_points(area)
        display_results(points, area)

if __name__ == "__main__":
    main()