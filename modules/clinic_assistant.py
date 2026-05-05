import os
import json
import requests
import sys
import re
import io
import contextlib
from typing import Dict

from openai import OpenAI

if sys.platform == 'win32':
    # 多个模块被同进程 import 时，避免重复包装 sys.stdout 造成句柄关闭。
    try:
        import io
        if (getattr(sys.stdout, "encoding", "") or "").lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# ── 火山方舟配置 ──
ARK_API_KEY = "5e78a452-0a30-414f-8c73-f196a30172fa"
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.getenv("ARK_MODEL", "doubao-seed-1-6-flash-250828")

# ── 医管局家庭医学诊所筹额 API（SC / TC / EN）──
QUOTA_API_TEMPLATE = "https://www.ha.org.hk/pas_gopc/pas_gopc_avg_quota_pdf/g0_9uo7a_p-{lang}.json"

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


# ────────────────── 工具函数 ──────────────────

def _get_ark_client() -> OpenAI:
    if not ARK_API_KEY:
        raise RuntimeError("未设置 ARK_API_KEY，请先在环境变量中配置。")
    return OpenAI(base_url=ARK_BASE_URL, api_key=ARK_API_KEY)


def _call_llm(prompt: str) -> str:
    """调用豆包模型，返回文本。"""
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


def _parse_js_object(file_path: str) -> dict:
    """解析类 JS 对象格式的文件（键名无双引号）。"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    fixed = re.sub(r'^(\s*)(\w+)(\s*:)', r'\1"\2"\3', content, flags=re.MULTILINE)
    return json.loads(fixed)


# ────────────────── 数据加载 ──────────────────

def load_clinic_data(file_path: str) -> list:
    """从 data2.txt 加载诊所列表。"""
    try:
        data = _parse_js_object(file_path)
        clinics = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            clinics.append({
                "en": props.get("CLINIC_EN"),
                "sc": props.get("CLINIC_SC"),
                "tc": props.get("CLINIC_TC"),
            })
        return clinics
    except Exception as e:
        print(f"加载诊所数据失败: {e}")
        return []


# ────────────────── AI 识别 ──────────────────

def identify_clinic_and_language(user_query: str, clinics: list) -> Dict:
    """让豆包从诊所列表中识别用户想查询的诊所，并判断用户语言。"""
    clinic_list_str = "\n".join(
        f"- {c['sc']} (EN: {c['en']}, TC: {c['tc']})" for c in clinics
    )

    prompt = f"""你是一个香港家庭医学诊所查询助手。根据用户的问题，你需要确定：
1. 用户询问的是哪家诊所（必须从列表中选择最匹配的一项）。
2. 用户使用的语言：EN（英文）、SC（简体中文）、TC（繁体中文）。

诊所列表：
{clinic_list_str}

用户问题："{user_query}"

仅以 JSON 格式回答：
{{
    "clinic_sc": "诊所简体中文名称",
    "clinic_tc": "诊所繁体中文名称",
    "clinic_en": "诊所英文名称",
    "language": "EN/SC/TC"
}}
如果无法确定诊所，将 clinic_sc/clinic_tc/clinic_en 设为 null。
"""

    try:
        text = _call_llm(prompt.strip())
        if "{" in text and "}" in text:
            json_str = text[text.find("{"):text.rfind("}") + 1]
            return json.loads(json_str)
    except Exception as e:
        print(f"AI 识别失败: {e}")
    return {"clinic_sc": None, "clinic_tc": None, "clinic_en": None, "language": "SC"}


# ────────────────── 查询筹额 ──────────────────

def get_clinic_quota(clinic_name: str, language: str = "SC"):
    """从医管局 API 查询指定诊所的最近四周平均筹额。"""
    lang = language.lower()
    if lang not in ("sc", "tc", "en"):
        lang = "sc"

    url = QUOTA_API_TEMPLATE.format(lang=lang)

    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
        all_data: list = resp.json()
    except Exception as e:
        print(f"获取数据失败: {e}")
        return

    # 按 Clinic 字段匹配
    matched = [r for r in all_data if r.get("Clinic") == clinic_name]
    if not matched:
        print(f"未在 API 中找到诊所: {clinic_name}")
        return

    record = matched[0]
    period = record.get("Period", {})

    # 多语言标签
    labels = {
        "SC": {
            "title": "**家庭医学诊所 ─ 最近四周平均筹额**",
            "clinic": "诊所名称",
            "district": "地区",
            "period": "统计期间",
            "session": "诊症时段",
            "na": "不适用",
        },
        "TC": {
            "title": "**家庭醫學診所 ─ 最近四星期平均籌額**",
            "clinic": "診所名稱",
            "district": "地區",
            "period": "統計期間",
            "session": "診症時段",
            "na": "不適用",
        },
        "EN": {
            "title": "**Family Medicine Clinic - Average Quota (Past 4 Weeks)**",
            "clinic": "Clinic",
            "district": "District",
            "period": "Period",
            "session": "Consultation Sessions",
            "na": "N/A",
        },
    }
    L = labels.get(language, labels["SC"])

    days_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    days_label = {
        "SC": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
        "TC": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
        "EN": days_en,
    }
    d_labels = days_label.get(language, days_label["SC"])

    from_str = period.get("from", "")
    to_str = period.get("to", "")
    period_display = f"{from_str[:4]}/{from_str[4:6]}/{from_str[6:]} - {to_str[:4]}/{to_str[4:6]}/{to_str[6:]}" if from_str else ""

    print(f"  {L['title']}")
    print(f"{L['clinic']}  : {clinic_name}")
    print(f"{L['district']}: {record.get('District', '')}")
    print(f"{L['period']}: {period_display}")
    print(f"{L['session']}: {record.get('Doctor Consultation Sessions', '')}")
    for day_en, day_label in zip(days_en, d_labels):
        val = record.get(day_en, L["na"])
        print(f"  {day_label:<6}: {val}")


# ────────────────── 主程序 ──────────────────

def main():
    if not ARK_API_KEY:
        print("错误：请先设置 ARK_API_KEY。")
        return

    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "data2.txt")
    clinics = load_clinic_data(data_path)
    if not clinics:
        print("未找到诊所数据。")
        return

    print("--------------------------------"*2)
    while True:
        try:
            query = input("\n请输入您的问题 (输入 'exit' 退出): ")
            if query.strip().lower() == "exit":
                break

            result = identify_clinic_and_language(query, clinics)
            lang = result.get("language", "SC")

            if lang == "EN":
                name = result.get("clinic_en")
            elif lang == "TC":
                name = result.get("clinic_tc")
            else:
                name = result.get("clinic_sc")

            if name:
                print(f"识别结果：诊所 -> {name}, 语言 -> {lang}")
                get_clinic_quota(name, lang)
            else:
                print("抱歉，我无法识别您提到的诊所。")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"发生错误: {e}")


if __name__ == "__main__":
    main()


# -------------------------- 可调用主入口 --------------------------
def handle_query(user_query: str, force_lang: str = None) -> str:
    """
    统一给主程序调用的入口。
    返回值：用于展示的字符串（内部会捕获各函数的 print 输出）。
    """
    if not ARK_API_KEY:
        return "错误：请先设置 ARK_API_KEY。"

    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "data2.txt")
    clinics = load_clinic_data(data_path)
    if not clinics:
        return "未找到诊所数据。"

    result = identify_clinic_and_language(user_query, clinics)
    lang = force_lang or result.get("language", "SC")

    if lang == "EN":
        name = result.get("clinic_en")
    elif lang == "TC":
        name = result.get("clinic_tc")
    else:
        name = result.get("clinic_sc")

    if not name:
        return "抱歉，我无法识别您提到的诊所。"

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        get_clinic_quota(name, lang)
    return buf.getvalue().strip()
