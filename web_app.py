import os
import sys

# 彻底修复 Anaconda 的 SSL 证书问题
def _fix_ssl():
    for v in ["SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"]:
        if v in os.environ:
            del os.environ[v]
_fix_ssl()

import threading
import webbrowser
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request


# 让本目录下的 main.py / 各模块可以被正常导入
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 添加 modules 目录到 path
MODULES_PATH = os.path.join(PROJECT_ROOT, "modules")
if MODULES_PATH not in sys.path:
    sys.path.insert(0, MODULES_PATH)

import main  # noqa: E402
from modules import hospital_ai_assistant  # noqa: E402
from modules import clinic_assistant  # noqa: E402
from modules import food  # noqa: E402
from modules import hotel_improved  # noqa: E402
from modules import env as recycle_module  # noqa: E402


app = Flask(__name__, template_folder="templates", static_folder="static")

handlers = {
    "hospital_ae": hospital_ai_assistant.handle_query,
    "clinic_quota": clinic_assistant.handle_query,
    "food_licence": food.handle_query,
    "hotel_search": hotel_improved.handle_query,
    "recycle_air": recycle_module.handle_query,
}


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/query")
def api_query():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    sys_lang = payload.get("sys_lang")
    if not query:
        return jsonify({"error": "missing query"}), 400

    classified = main.classify_intent(query)
    intent = classified.get("intent", "unknown")
    entities = classified.get("entities", {}) or {}

    handler = handlers.get(intent)
    if not handler or intent == "unknown":
        result = main.unknown_help(sys_lang)
        return jsonify({"intent": intent, "entities": entities, "result": result})

    try:
        # Pass force_lang to support language switching
        result = handler(query, force_lang=sys_lang)
    except Exception as e:
        result = f"模块执行失败（intent={intent}）：{e}"

    return jsonify({"intent": intent, "entities": entities, "result": _safe_str(result)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    
    # 在 1.25 秒后自动打开浏览器，确保 Flask 已经启动
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.25, lambda: webbrowser.open(url)).start()
    
    app.run(host="0.0.0.0", port=port, debug=debug)
