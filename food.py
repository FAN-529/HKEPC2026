import os
import json
import requests
import sys
from typing import Dict, List

from openai import OpenAI

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── 火山方舟配置 ──
ARK_API_KEY = "5e78a452-0a30-414f-8c73-f196a30172fa"
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.getenv("ARK_MODEL", "doubao-seed-1-6-flash-250828")

# ── CSDI ArcGIS REST API ──
FOOD_LICENCE_API = (
    "https://portal.csdi.gov.hk/server/rest/services/common/"
    "fehd_rcd_1630036111498_75446/FeatureServer/0/query"
)

# ── 牌照类型代码 ──
TYPE_CODES = {
    "CL": {"tc": "綜合食物店牌照", "en": "Composite Food Shop Licence"},
    "FB": {"tc": "烘製麵包餅食店牌照", "en": "Bakery Licence"},
    "FC": {"tc": "凍房牌照", "en": "Cold Store Licence"},
    "FE": {"tc": "工廠食堂牌照", "en": "Factory Canteen Licence"},
    "FF": {"tc": "食物製造廠牌照", "en": "Food Factory Licence"},
    "FP": {"tc": "新鮮糧食店牌照", "en": "Fresh Provision Shop Licence"},
    "FG": {"tc": "冰凍甜點製造廠牌照", "en": "Frozen Confection Factory Licence"},
    "FM": {"tc": "奶品廠牌照", "en": "Milk Factory Licence"},
    "FS": {"tc": "燒味及鹵味店牌照", "en": "Siu Mei and Lo Mei Shop Licence"},
}

# ── 地区代码 ──
DIST_CODES = {
    "11": {"tc": "東區", "en": "Eastern"},
    "12": {"tc": "灣仔區", "en": "Wan Chai"},
    "15": {"tc": "南區", "en": "Southern"},
    "17": {"tc": "離島區", "en": "Islands"},
    "18": {"tc": "中西區", "en": "Central/Western"},
    "51": {"tc": "觀塘區", "en": "Kwun Tong"},
    "52": {"tc": "九龍城區", "en": "Kowloon City"},
    "53": {"tc": "黃大仙區", "en": "Wong Tai Sin"},
    "61": {"tc": "油尖區", "en": "Yau Tsim"},
    "62": {"tc": "旺角區", "en": "Mong Kok"},
    "63": {"tc": "深水埗區", "en": "Sham Shui Po"},
    "91": {"tc": "葵青區", "en": "Kwai Tsing"},
    "92": {"tc": "荃灣區", "en": "Tsuen Wan"},
    "93": {"tc": "屯門區", "en": "Tuen Mun"},
    "94": {"tc": "元朗區", "en": "Yuen Long"},
    "95": {"tc": "大埔區", "en": "Tai Po"},
    "96": {"tc": "北區", "en": "North"},
    "97": {"tc": "沙田區", "en": "Sha Tin"},
    "98": {"tc": "西貢區", "en": "Sai Kung"},
}


# ────────────────── 工具函数 ──────────────────

def _get_ark_client() -> OpenAI:
    return OpenAI(base_url=ARK_BASE_URL, api_key=ARK_API_KEY)


def _call_llm(prompt: str) -> str:
    client = _get_ark_client()
    if hasattr(client, "responses"):
        resp = client.responses.create(
            model=ARK_MODEL,
            input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        )
        text = getattr(resp, "output_text", None)
        if text:
            return text
        try:
            for block in (getattr(resp, "output", None) or []):
                for part in (getattr(block, "content", []) or []):
                    t = getattr(part, "text", None)
                    if t:
                        return t
        except Exception:
            pass
        return str(resp)
    else:
        comp = client.chat.completions.create(
            model=ARK_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return comp.choices[0].message.content or ""


# ────────────────── AI 解析用户意图 ──────────────────

def parse_user_query(query: str) -> Dict:
    """让 AI 从用户问题中提取：牌照类型、地区、店铺名称、语言。"""
    type_list = "\n".join(f"  {k} = {v['tc']} ({v['en']})" for k, v in TYPE_CODES.items())
    dist_list = "\n".join(f"  {v['tc']} ({v['en']})" for v in DIST_CODES.values())

    prompt = f"""你是一个香港食物业牌照查询助手。根据用户的问题，提取以下信息：

1. type_code — 用户想查的牌照类型代码（从下面的列表中选一个，若用户未指定则为 null）
{type_list}

2. district — 用户想查的地区（繁体中文名称，从下面的列表中选一个，若用户未指定则为 null）
{dist_list}

3. shop_name — 用户想查的具体店铺名称关键词（若用户未提及则为 null）

4. language — 用户使用的语言：EN（英文）或 TC（中文，包括简体和繁体都归为 TC）

用户问题："{query}"

仅以 JSON 格式回答：
{{
    "type_code": "代码或null",
    "district": "地区繁体名称或null",
    "shop_name": "店铺名称或null",
    "language": "EN或TC"
}}"""

    try:
        text = _call_llm(prompt.strip())
        if "{" in text and "}" in text:
            json_str = text[text.find("{"):text.rfind("}") + 1]
            result = json.loads(json_str)
            if result.get("type_code") == "null":
                result["type_code"] = None
            if result.get("district") == "null":
                result["district"] = None
            if result.get("shop_name") == "null":
                result["shop_name"] = None
            return result
    except Exception as e:
        print(f"AI 解析失败: {e}")
    return {"type_code": None, "district": None, "shop_name": None, "language": "TC"}


# ────────────────── API 查询 ──────────────────

def query_food_licences(
    type_code: str = None,
    district: str = None,
    shop_name: str = None,
    max_results: int = 10,
) -> List[dict]:
    """调用 CSDI ArcGIS REST API 查询食物业牌照。"""
    conditions = []
    if type_code:
        conditions.append(f"NSEARCH02_TC='{type_code}'")
    if district:
        conditions.append(f"SEARCH01_TC='{district}'")
    if shop_name:
        conditions.append(f"NSEARCH03_TC LIKE '%{shop_name}%'")

    where = " AND ".join(conditions) if conditions else "1=1"

    params = {
        "f": "json",
        "where": where,
        "outFields": (
            "NAME_TC,NAME_EN,ADDRESS_TC,ADDRESS_EN,"
            "SEARCH01_TC,SEARCH01_EN,"
            "SEARCH02_TC,"
            "NSEARCH02_TC,NSEARCH03_TC,NSEARCH03_EN,"
            "NSEARCH04_TC,NSEARCH05_TC,"
            "LATITUDE,LONGITUDE"
        ),
        "returnGeometry": "false",
        "resultRecordCount": max_results,
    }

    try:
        resp = requests.get(FOOD_LICENCE_API, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for feat in data.get("features", []):
            a = feat["attributes"]
            results.append({
                "licence_type_tc": a.get("NAME_TC"),
                "licence_type_en": a.get("NAME_EN"),
                "district_tc": a.get("SEARCH01_TC"),
                "district_en": a.get("SEARCH01_EN"),
                "licence_no": a.get("SEARCH02_TC"),
                "type_code": a.get("NSEARCH02_TC"),
                "shop_tc": a.get("NSEARCH03_TC"),
                "shop_en": a.get("NSEARCH03_EN"),
                "info": a.get("NSEARCH04_TC"),
                "expiry": a.get("NSEARCH05_TC"),
                "address_tc": a.get("ADDRESS_TC"),
                "address_en": a.get("ADDRESS_EN"),
                "lat": a.get("LATITUDE"),
                "lng": a.get("LONGITUDE"),
            })
        return results
    except Exception as e:
        print(f"API 查询失败: {e}")
        return []


def count_food_licences(type_code: str = None, district: str = None) -> int:
    """返回符合条件的牌照总数。"""
    conditions = []
    if type_code:
        conditions.append(f"NSEARCH02_TC='{type_code}'")
    if district:
        conditions.append(f"SEARCH01_TC='{district}'")
    where = " AND ".join(conditions) if conditions else "1=1"

    params = {"f": "json", "where": where, "returnCountOnly": "true"}
    try:
        resp = requests.get(FOOD_LICENCE_API, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("count", 0)
    except Exception:
        return -1


# ────────────────── 显示结果 ──────────────────

def display_results(results: List[dict], total: int, language: str, query_desc: str):
    """格式化输出查询结果。"""
    if language == "EN":
        print(f"\n{'='*60}")
        print(f"  Food Premises Licence Query Results")
        print(f"{'='*60}")
        print(f"Query     : {query_desc}")
        print(f"Total     : {total} licence(s) found")
        print(f"Showing   : Top {len(results)}")
        print(f"{'-'*60}")
        for i, r in enumerate(results, 1):
            print(f"\n  [{i}] {r['shop_en'] or 'N/A'}")
            print(f"      Type    : {r['licence_type_en']}")
            print(f"      District: {r['district_en']}")
            print(f"      Address : {r['address_en']}")
            print(f"      Licence#: {r['licence_no']}")
            print(f"      Expiry  : {r['expiry']}")
            if r['info']:
                print(f"      Note    : {r['info']}")
    else:
        print(f"\n{'='*60}")
        print(f"  食物業處所牌照查詢結果")
        print(f"{'='*60}")
        print(f"查詢條件 : {query_desc}")
        print(f"符合總數 : {total} 項")
        print(f"顯示前   : {len(results)} 項")
        print(f"{'-'*60}")
        for i, r in enumerate(results, 1):
            print(f"\n  [{i}] {r['shop_tc'] or '未提供'}")
            print(f"      類型  : {r['licence_type_tc']}")
            print(f"      地區  : {r['district_tc']}")
            print(f"      地址  : {r['address_tc']}")
            print(f"      牌照號: {r['licence_no']}")
            print(f"      届滿日: {r['expiry']}")
            if r['info']:
                info_desc = {
                    "#I": "獲准出售活家禽(不包括活水禽及活鵪鶉)",
                    "#J": "供應午餐飯盒的持牌食物製造廠",
                }.get(r['info'], r['info'])
                print(f"      批注  : {info_desc}")

    print(f"\n{'='*60}\n")


# ────────────────── 主程序 ──────────────────

def main():
    print("香港食物業處所牌照查詢助手")
    print("可按 牌照類型、地區、店鋪名稱 進行查詢")
    print("示例：")
    print("  - 中西区有哪些烧味店？")
    print("  - 观塘有什么新鲜粮食店？")
    print("  - 帮我找百佳的牌照")
    print("  - Show me bakeries in Wan Chai")

    while True:
        try:
            query = input("\n请输入您的问题 (输入 'exit' 退出): ")
            if query.strip().lower() in ("exit", "quit", "退出"):
                break

            print("正在分析您的问题...")
            parsed = parse_user_query(query)

            type_code = parsed.get("type_code")
            district = parsed.get("district")
            shop_name = parsed.get("shop_name")
            language = parsed.get("language", "TC")

            # 构建查询描述
            desc_parts = []
            if district:
                desc_parts.append(f"地區={district}" if language == "TC" else f"District={district}")
            if type_code and type_code in TYPE_CODES:
                t = TYPE_CODES[type_code]
                desc_parts.append(t['tc'] if language == "TC" else t['en'])
            if shop_name:
                desc_parts.append(f"店名含「{shop_name}」" if language == "TC" else f"Shop contains '{shop_name}'")
            query_desc = " + ".join(desc_parts) if desc_parts else ("全部" if language == "TC" else "All")

            print(f"识别结果：类型={type_code or '不限'}, 地区={district or '不限'}, "
                  f"店名={shop_name or '不限'}, 语言={language}")

            total = count_food_licences(type_code, district)
            results = query_food_licences(type_code, district, shop_name, max_results=10)

            if results:
                display_results(results, total, language, query_desc)
            else:
                if language == "EN":
                    print("No matching food licences found.")
                else:
                    print("未找到符合條件的食物業處所牌照。")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"发生错误: {e}")


if __name__ == "__main__":
    main()
