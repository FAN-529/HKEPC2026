import os
import sys

# 彻底修复 Anaconda 的 SSL 证书问题
def _fix_ssl():
    for v in ["SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"]:
        if v in os.environ:
            del os.environ[v]
_fix_ssl()

import json
import re
from typing import Any, Dict, Optional

# 让本目录下的各模块可以被正常导入
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODULES_PATH = os.path.join(PROJECT_ROOT, "modules")
if MODULES_PATH not in sys.path:
    sys.path.insert(0, MODULES_PATH)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from openai import OpenAI

# 确保 Windows 控制台能正确显示中文
if sys.platform == "win32":
    # 避免重复包装 sys.stdout 造成句柄关闭（多个模块 import 同进程时容易触发）
    try:
        import io

        if (getattr(sys.stdout, "encoding", "") or "").lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:
        pass


# ========== 火山方舟配置（用于意图路由） ==========
ARK_API_KEY = os.getenv("ARK_API_KEY", "5e78a452-0a30-414f-8c73-f196a30172fa")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.getenv("ARK_MODEL", "doubao-seed-1-6-flash-250828")


INTENTS = {
    "hospital_ae": "急症室/急诊等候时间（医院管理局）",
    "clinic_quota": "家庭医学诊所筹额（最近四周平均筹额）",
    "food_licence": "食物业牌照查询（CSDI ArcGIS）",
    "hotel_search": "高评分酒店查询（SerpAPI Google Hotels）",
    "recycle_air": "回收点 + 附近空气质量（CSDI + DeepSeek）",
    "unknown": "无法判断",
}


def _get_ark_client() -> OpenAI:
    if not ARK_API_KEY:
        raise RuntimeError("未设置 ARK_API_KEY，无法使用 LLM 意图路由。")
    return OpenAI(base_url=ARK_BASE_URL, api_key=ARK_API_KEY)


def _call_llm(prompt: str) -> str:
    client = _get_ark_client()
    # 兼容不同 SDK 响应字段
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

    comp = client.chat.completions.create(model=ARK_MODEL, messages=[{"role": "user", "content": prompt}])
    return comp.choices[0].message.content or ""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    if "{" not in text or "}" not in text:
        return None
    start = text.find("{")
    end = text.rfind("}") + 1
    json_str = text[start:end]
    try:
        return json.loads(json_str)
    except Exception:
        return None


def rule_based_intent(user_query: str) -> str:
    q = (user_query or "").lower()
    # 规则优先级从“明确强信号”到“弱信号”
    if any(k in q for k in ["急症室", "aed", "a&e", "急诊", "急診", "emergency", "waiting time", "wait time", "hospital"]):
        return "hospital_ae"
    if any(k in q for k in ["家庭医学", "家庭醫學", "诊所", "診所", "籌額", "筹额", "clinic", "quota"]):
        return "clinic_quota"
    if any(k in q for k in ["牌照", "食物", "烘製", "烧味", "燒味", "bakery", "cold store", "牌照查询", "牌照查詢", "licence", "license", "food", "siu mei", "shop", "restaurant"]):
        return "food_licence"
    if any(k in q for k in ["酒店", "旅馆", "旅館", "住宿", "入住", "退房", "check_in", "check_out", "hotel", "room", "booking", "accommodation"]):
        return "hotel_search"
    if any(k in q for k in ["回收", "垃圾", "回收点", "回收點", "空气质量", "空氣質素", "air quality", "sustainable", "recycle", "recycling", "trash", "waste"]):
        return "recycle_air"
    return "unknown"


def classify_intent(user_query: str) -> Dict[str, Any]:
    """
    先用 LLM 生成固定 JSON，再做轻量校验。
    若 LLM 不可用/输出异常，则回退到规则法。
    """
    # 先规则快速试一下（提高稳定性）
    rule_intent = rule_based_intent(user_query)

    prompt = f"""
你是一个“香港生活助手”的意图路由器。请判断用户问题属于以下意图之一，并只返回 JSON：

可选 intent（附带功能说明，支持简繁体与英文）：
- hospital_ae （急症室/急診等候時間、醫院/A&E wait time）
- clinic_quota （家庭醫學/家庭医学诊所筹额、診所/Clinic quotas）
- food_licence （食物業/食物业牌照查询、燒味/烧味店、餐廳/Food licences or shops, e.g. siu mei shops）
- hotel_search （高評分/高评分酒店查询、入住/Hotels search booking）
- recycle_air （回收點/回收点 + 附近空氣質素/空气质量、垃圾/Recycling spots & air quality）
- unknown （完全不相关的问题）

JSON 格式（必须严格符合）：
{{
  "intent": "可选的 intent 值",
  "entities": {{
    "language_hint": "SC/TC/EN或null",
    "hospital_name": "医院名称关键字或null",
    "clinic_name": "诊所名称关键字或null",
    "food_type_code": "牌照类型代码或null",
    "district": "地区关键字或null",
    "shop_name": "店铺名称关键字或null",
    "location": "酒店地点关键字或null",
    "check_in": "YYYY-MM-DD或null",
    "check_out": "YYYY-MM-DD或null",
    "area": "香港地区关键字或null"
  }}
}}

用户问题：{json.dumps(user_query, ensure_ascii=False)}
"""

    try:
        if not ARK_API_KEY:
            raise RuntimeError("no ark api key")
        text = _call_llm(prompt.strip())
        parsed = _extract_json(text)
        if not parsed:
            raise ValueError("LLM JSON 解析失败")

        intent = parsed.get("intent")
        if intent not in INTENTS:
            intent = rule_intent

        entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
        parsed["intent"] = intent
        parsed["entities"] = entities
        return parsed
    except Exception:
        return {"intent": rule_intent, "entities": {}}


def unknown_help(force_lang: str = None) -> str:
    if force_lang == "EN":
        return "\n".join([
            "I couldn't identify the feature you want to use. You can provide more keywords:",
            "",
            "1. A&E wait time: e.g. 'What is the current A&E waiting time at Queen Mary Hospital?'",
            "2. Clinic quotas: e.g. 'What's the average quota for Hung Hom Clinic in the last 4 weeks?'",
            "3. Food licences: e.g. 'What siu mei shops are there in Kwun Tong?'",
            "4. Hotels: e.g. 'Tsim Sha Tsui hotels, check-in 2026-04-01, check-out 2026-04-03, rating >= 4.3'",
            "5. Recycling spots: e.g. 'I want to find a recycling spot in Tuen Mun'",
        ])
    elif force_lang == "TC":
        return "\n".join([
            "我仲未確定你想查邊種功能。你可以補充多啲資訊（盡量包含關鍵詞）：",
            "",
            "1. 急症室等候時間：例如「瑪麗醫院嘅急症室而家要等幾耐？」",
            "2. 診所籌額：例如「紅磡家庭醫學診所最近四周平均籌額係幾多？」",
            "3. 食物业牌照：例如「觀塘有咩燒味店？」",
            "4. 高評分酒店：例如「尖沙咀酒店，入住2026-04-01，退房2026-04-03，評分≥4.3」",
            "5. 回收點+空氣質素：例如「我想去屯門搵垃圾回收點」",
        ])
    else:
        return "\n".join([
            "我还没法确定你想查的是哪一种功能。你可以补充更多信息（尽量包含关键词）：",
            "",
            "1. 急症室等候时间：例如“玛丽医院的急症室现在等候多久？”",
            "2. 诊所筹额：例如“红磡家庭医学诊所最近四周平均筹额是多少？”",
            "3. 食物业牌照：例如“观塘有哪些烧味店？”",
            "4. 高评分酒店：例如“尖沙咀酒店，入住2026-04-01，退房2026-04-03，评分≥4.3”",
            "5. 回收点+空气质量：例如“我想去屯门找垃圾回收点”",
        ])


def main() -> None:
    import hospital_ai_assistant
    import clinic_assistant
    import food
    import hotel_improved
    import env as recycle_module

    handlers = {
        "hospital_ae": hospital_ai_assistant.handle_query,
        "clinic_quota": clinic_assistant.handle_query,
        "food_licence": food.handle_query,
        "hotel_search": hotel_improved.handle_query,
        "recycle_air": recycle_module.handle_query,
    }

    print("香港多功能 AI 助手（统一意图路由版）")
    print("支持：急症室等候时间、诊所筹额、食物业牌照、酒店推荐、回收点+空气质量。")
    print("请输入问题（输入 `exit`/`退出` 退出）。")

    while True:
        try:
            user_query = input("\n你：").strip()
            if not user_query:
                continue
            if user_query.lower() in {"exit", "quit", "退出"}:
                print("感谢使用！")
                break

            classified = classify_intent(user_query)
            intent = classified.get("intent", "unknown")

            handler = handlers.get(intent)
            if not handler or intent == "unknown":
                print(unknown_help())
                continue

            try:
                module_name = INTENTS.get(intent, intent)
                print(f"\n[意图识别] {intent} - {module_name}")
                result_text = handler(user_query)
                if result_text is None:
                    result_text = ""
                result_text = result_text if isinstance(result_text, str) else str(result_text)
                print(result_text.strip() or "(该功能未返回结果)")
            except Exception as e:
                print(f"模块执行失败（intent={intent}）：{e}")
                print("你可以稍后再试，或把问题再说得更具体一些（例如：医院/诊所/地区/酒店入住退房日期/回收点所在区域）。")

        except KeyboardInterrupt:
            print("\n已退出。")
            break


if __name__ == "__main__":
    main()

