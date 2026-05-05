import requests
try:
    from fuzzywuzzy import process  # type: ignore
except Exception:
    process = None
import os
import io
import contextlib
from openai import OpenAI

# -------------------------- 环境修复 --------------------------
if "SSL_CERT_FILE" in os.environ:
    del os.environ["SSL_CERT_FILE"]

# -------------------------- 配置参数 --------------------------
_client = None

def get_deepseek_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key="sk-e3196140b13443c79b1e5e2c0393376b", base_url="https://api.deepseek.com")
    return _client

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
        client = get_deepseek_client()
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

    # 如果 fuzzywuzzy 可用，用模糊匹配保证落在可选地区集合内
    if area and process:
        best_match = process.extractOne(area, HK_AREAS)
        if best_match and best_match[1] > 80:
            return best_match[0]

    # 如果 fuzzywuzzy 不可用，则直接在文本中做包含判断
    if area and not process:
        for area_key in HK_AREAS:
            if area_key in area:
                return area_key

    # 如果 API 调用失败或无法识别，回退到旧方法：要么 fuzzywuzzy，要么纯包含匹配
    if process:
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

def display_results(points: list, area: str, force_lang: str = None):
    """使用DeepSeek API生成并展示更自然的回复"""
    if not points:
        lang_str = "简体中文"
        if force_lang == "EN":
            lang_str = "English"
        elif force_lang == "TC":
            lang_str = "繁体中文（粤语口语）"
        prompt = f"请使用{lang_str}告诉用户在香港的「{area}」区域未找到相关的回收点信息。"
        response = get_deepseek_response(prompt)
        bot_prefix = "AI Assistant: " if force_lang == "EN" else "智能助手："
        print(f"\n{bot_prefix}{response}")
        return

    top_points = points[:5]
    if len(points) > 5:
        details = f"在「{area}」找到了 {len(points)} 个回收点，为你展示前 5 个：\n"
    else:
        details = f"在「{area}」找到了 {len(points)} 个回收点。\n"

    for i, p in enumerate(top_points, 1):
        details += f"\n回收点 {i}:\n"
        if force_lang == "EN":
            details += f"- 地址: {p['英文地址']}\n"
        elif force_lang == "TC":
            details += f"- 地址: {p['繁体地址']}\n"
        else:
            details += f"- 地址: {p['简体地址']}\n"
        
        if p['y'] and p['x']:
            air_data = fetch_nearby_air_quality(p['y'], p['x'], max_dist=20000)
            if air_data:
                details += f"  附近的空气质量监测站:\n"
                for j, ap in enumerate(air_data[:1], 1): # Top 1 only
                    if force_lang == "EN":
                        details += f"    - 名称: {ap['英文站点']} (距离: {ap['距离']}米)\n"
                    else:
                        details += f"    - 名称: {ap['繁体站点']} (距离: {ap['距离']}米)\n"
            else:
                details += "  附近暂无空气质量监测数据。\n"
        else:
            details += "  无法获取位置信息，暂不展示空气质量数据。\n"

    lang_map = {"SC": "简体中文", "TC": "繁体中文（粤语口语）", "EN": "English"}
    lang_str = lang_map.get(force_lang, "简体中文")
    system_prompt = f"你是一个香港生活助手，你需要根据我提供的数据，以友好、清晰、有条理的方式回复用户。请使用 {lang_str}。不要使用 markdown 分隔符（如 ---）。回复的第一行请加粗作为标题。"
    prompt = f"这是我为你找到的信息，请整理并回复给用户：\n\n{details}"
    bot_prefix = "AI Assistant:\n" if force_lang == "EN" else "智能助手：\n"
    response = get_deepseek_response(prompt, system_prompt)
    print(f"\n{bot_prefix}{response}")

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


# -------------------------- 可调用主入口 --------------------------
def handle_query(user_query: str, force_lang: str = None) -> str:
    """
    统一给主程序调用的入口。
    返回值：用于展示的字符串（内部会捕获各函数的 print 输出）。
    """
    area = parse_user_query(user_query)
    if not area:
        lang_str = "简体中文"
        if force_lang == "EN":
            lang_str = "English"
        elif force_lang == "TC":
            lang_str = "繁体中文（粤语口语）"
        prompt = f"请使用{lang_str}告诉用户未能识别出有效的香港地区名称，并引导用户输入更明确的地点，例如'我想找铜锣湾的回收点'。"
        response = get_deepseek_response(prompt)
        bot_prefix = "AI Assistant: " if force_lang == "EN" else "智能助手： "
        return f"{bot_prefix}{response}".strip()

    points = fetch_recycle_points(area)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        msg = f"正在查询「{area}」的回收点及周边空气质量信息..."
        if force_lang == "EN":
            msg = f"Querying recycling points and nearby air quality for '{area}'..."
        elif force_lang == "TC":
            msg = f"正在查詢「{area}」嘅回收點及周邊空氣質素資訊..."
        print(msg)
        display_results(points, area, force_lang)
    return buf.getvalue().strip()