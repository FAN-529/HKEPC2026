import os
import json
import requests
import sys
import re
import io
import contextlib
from typing import Dict, Optional

from openai import OpenAI

# 确保 Windows 控制台能正确显示中文字符（避免重复包装导致 stdout 关闭）
if sys.platform == 'win32':
    try:
        import io
        if (getattr(sys.stdout, "encoding", "") or "").lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass


ARK_API_KEY = "5e78a452-0a30-414f-8c73-f196a30172fa"
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

ARK_MODEL = os.getenv("ARK_MODEL", "doubao-seed-1-6-flash-250828")


def _get_ark_client() -> OpenAI:
    if not ARK_API_KEY:
        raise RuntimeError(
            "未设置环境变量 ARK_API_KEY。请在系统或当前终端中配置后再运行。"
        )
    return OpenAI(base_url=ARK_BASE_URL, api_key=ARK_API_KEY)


def _extract_responses_text(response) -> str:
    """从 responses.create 的返回对象中取出文本（兼容不同 SDK 字段）。"""
    t = getattr(response, "output_text", None)
    if t:
        return t
    try:
        out = getattr(response, "output", None)
        if out:
            for block in out:
                for part in getattr(block, "content", []) or []:
                    ptype = getattr(part, "type", None) or (
                        part.get("type") if isinstance(part, dict) else None
                    )
                    if ptype in ("output_text", "text"):
                        tx = getattr(part, "text", None)
                        if tx is None and isinstance(part, dict):
                            tx = part.get("text")
                        if tx:
                            return tx
    except Exception:
        pass
    return str(response)

def load_hospital_data(file_path: str) -> list:
    """从 data.txt 加载医院数据"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # data.txt 的键没有双引号（JS 对象格式），需要给行首的键名加上双引号
            fixed_content = re.sub(r'^(\s*)(\w+)(\s*:)', r'\1"\2"\3', content, flags=re.MULTILINE)
            data = json.loads(fixed_content)
            
            hospitals = []
            for feature in data.get('features', []):
                props = feature.get('properties', {})
                hospitals.append({
                    "en": props.get("hospName_EN"),
                    "sc": props.get("hospName_SC"),
                    "tc": props.get("hospName_TC")
                })
            return hospitals
    except Exception as e:
        print(f"加载数据失败: {e}")
        return []

def get_ae_info(hospital_name: str, language: str = "SC"):
    """
    从香港医院管理局官方接口获取急症室等候时间。
    官方数据源: https://www.ha.org.hk/opendata/aed/aedwtdata2-sc.json
    """
    # 根据语言选择不同的数据源（SC, TC, EN）
    lang_suffix = language.lower()
    if lang_suffix not in ["sc", "tc", "en"]:
        lang_suffix = "sc"
    
    url = f"https://www.ha.org.hk/opendata/aed/aedwtdata2-{lang_suffix}.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # 发送请求
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # 显式设置编码并解析 JSON
        response.encoding = 'utf-8'
        data = response.json()
        
        update_time = data.get("updateTime", "未知时间")
        hospitals_data = data.get("waitTime", [])
        
        # 在列表中查找匹配的医院名称
        # 匹配逻辑：根据语言选择匹配字段
        target = next((h for h in hospitals_data if h.get("hospName") == hospital_name), None)
        
        if target:
            # 翻译标签
            labels = {
                "SC": {
                    "title": "**香港急症室实时等候时间**",
                    "hosp": "医院名称",
                    "update": "更新时间",
                    "t1": "第一类 (危殆)",
                    "t2": "第二类 (危急)",
                    "t3_50": "第三类 (紧急) 50%",
                    "t3_95": "第三类 (紧急) 95%",
                    "t45_50": "第四/五类 (非紧急) 50%",
                    "t45_95": "第四/五类 (非紧急) 95%"
                },
                "TC": {
                    "title": "**香港急症室實時等候時間**",
                    "hosp": "醫院名稱",
                    "update": "更新時間",
                    "t1": "第一類 (危殆)",
                    "t2": "第二類 (危急)",
                    "t3_50": "第三類 (緊急) 50%",
                    "t3_95": "第三類 (緊急) 95%",
                    "t45_50": "第四/五類 (非緊急) 50%",
                    "t45_95": "第四/五類 (非緊急) 95%"
                },
                "EN": {
                    "title": "**Hong Kong A&E Real-time Waiting Time**",
                    "hosp": "Hospital Name",
                    "update": "Update Time",
                    "t1": "Category 1 (Critical)",
                    "t2": "Category 2 (Emergency)",
                    "t3_50": "Category 3 (Urgent) 50%",
                    "t3_95": "Category 3 (Urgent) 95%",
                    "t45_50": "Category 4/5 (Semi-urgent/Non-urgent) 50%",
                    "t45_95": "Category 4/5 (Semi-urgent/Non-urgent) 95%"
                }
            }
            
            l = labels.get(language, labels["SC"])
            
            print(f"  {l['title']}")
            print(f"{l['hosp']}: {hospital_name}")
            print(f"{l['update']}: {update_time}")
            print(f"{l['t1']}      : {target.get('t1wt')}")
            print(f"{l['t2']}      : {target.get('t2wt')}")
            print(f"{l['t3_50']}  : {target.get('t3p50')}")
            print(f"{l['t3_95']}  : {target.get('t3p95')}")
            print(f"{l['t45_50']}: {target.get('t45p50')}")
            print(f"{l['t45_95']}: {target.get('t45p95')}")
        else:
            print(f"未找到医院: {hospital_name}")

    except Exception as e:
        print(f"获取数据失败: {e}")

def identify_hospital_and_language(user_query: str, hospitals: list) -> Dict:
    """使用火山方舟（豆包）识别医院名称和语言"""
    hospital_list_str = "\n".join([f"- {h['sc']} (EN: {h['en']}, TC: {h['tc']})" for h in hospitals])

    prompt = f"""
    你是一个香港医院咨询助手。根据用户的问题，你需要确定：
    1. 用户询问的是哪家医院（必须从提供的列表中选择最匹配的一项）。
    2. 用户使用的语言（EN, SC, 或 TC）。

    医院列表：
    {hospital_list_str}

    用户问题："{user_query}"

    请仅以 JSON 格式回答，格式如下：
    {{
        "hospital_sc": "医院简体中文名称",
        "hospital_tc": "医院繁体中文名称",
        "hospital_en": "医院英文名称",
        "language": "EN/SC/TC"
    }}
    如果无法确定医院，请将 hospital_sc, hospital_tc 和 hospital_en 设为 null。
    """

    try:
        client = _get_ark_client()
        text = ""
        if hasattr(client, "responses"):
            response = client.responses.create(
                model=ARK_MODEL,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt.strip()},
                        ],
                    }
                ],
            )
            text = _extract_responses_text(response)
        else:
            # 旧版 SDK 无 responses 时，使用 Chat Completions（方舟兼容）
            completion = client.chat.completions.create(
                model=ARK_MODEL,
                messages=[{"role": "user", "content": prompt.strip()}],
            )
            text = completion.choices[0].message.content or ""
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end]
            return json.loads(json_str)
        return {"hospital_sc": None, "hospital_en": None, "language": "SC"}
    except Exception as e:
        print(f"AI 识别失败: {e}")
        return {"hospital_sc": None, "hospital_en": None, "language": "SC"}

def main():
    if not ARK_API_KEY:
        print("错误：请先在环境变量中设置 ARK_API_KEY（火山引擎方舟 API Key）。")
        print("说明：https://www.volcengine.com/docs/82379/1399008")
        return

    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "data.txt")
    hospitals = load_hospital_data(data_path)
    
    if not hospitals:
        print("未找到医院数据。")
        return

    while True:
        try:
            query = input("\n请输入您的问题 (输入 'exit' 退出): ")
            if query.lower() == 'exit':
                break
            
            result = identify_hospital_and_language(query, hospitals)
            
            lang = result.get("language", "SC")
            
            # 根据识别出的语言选择匹配的医院名称
            if lang == "EN":
                hosp_name = result.get("hospital_en")
            elif lang == "TC":
                hosp_name = result.get("hospital_tc")
            else:
                hosp_name = result.get("hospital_sc")
            
            if hosp_name:
                print(f"识别结果：医院 -> {hosp_name}, 语言 -> {lang}")
                get_ae_info(hosp_name, lang)
            else:
                print("抱歉，我无法识别您提到的医院。")
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
        return "错误：请先在环境变量中设置 ARK_API_KEY（火山引擎方舟 API Key）。"

    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "data.txt")
    hospitals = load_hospital_data(data_path)
    if not hospitals:
        return "未找到医院数据。"

    result = identify_hospital_and_language(user_query, hospitals)
    lang = force_lang or result.get("language", "SC")

    if lang == "EN":
        hosp_name = result.get("hospital_en")
    elif lang == "TC":
        hosp_name = result.get("hospital_tc")
    else:
        hosp_name = result.get("hospital_sc")

    if not hosp_name:
        return "抱歉，我无法识别您提到的医院。"

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        get_ae_info(hosp_name, lang)
    return buf.getvalue().strip()
