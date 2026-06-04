# ============================================================
# ai_service.py
# 目前：GPT 負責對話 + 分析（Ollama 停用）
# 之後換 Ollama：只需取消 analyze_to_dimensions_ollama 的註解
#              並在 analyze_to_dimensions 改呼叫它即可
# ============================================================

import os
import json
import re
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CHAT_MODEL = "gpt-4o-mini"      # 對話用
ANALYZE_MODEL = "gpt-4o-mini"   # 分析用（之後換成 Ollama）


# ============================================================
# 對話功能：GPT 回應使用者並自然銜接下一題
# ============================================================

def chat_with_gpt(question_prompt: str, user_answer: str, history: list) -> str:
    """
    回應使用者的回答，並自然地帶出下一個問題。

    Args:
        question_prompt: 下一題的問題文字
        user_answer:     使用者剛才的回答
        history:         對話歷史 [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        AI 回應字串
    """
    system_prompt = (
        "你是一個親切的咖啡廳推薦助理，正在透過輕鬆的對話了解使用者的喜好。\n"
        "規則：\n"
        "1. 先用 1-2 句話自然回應使用者剛才說的內容，表示理解或共鳴。\n"
        "2. 接著提出這個問題：「" + question_prompt + "」\n"
        "3. 語氣輕鬆像朋友聊天，不要太正式，不要條列式。\n"
        "4. 全程使用繁體中文，回應控制在 80 字以內。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    if user_answer:
        messages.append({"role": "user", "content": user_answer})

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        max_tokens=200,
        temperature=0.75,
    )
    return response.choices[0].message.content.strip()


def get_opening_message(first_question_prompt: str) -> str:
    """
    產生第一句開場白 + 第一題（不需要使用者先說話）
    """
    system_prompt = (
        "你是一個親切的咖啡廳推薦助理。\n"
        "請用 1-2 句輕鬆的開場白歡迎使用者，然後提出這個問題：「" + first_question_prompt + "」\n"
        "全程繁體中文，80 字以內，語氣像朋友。"
    )

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        max_tokens=200,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()


# ============================================================
# 分析功能：把整段對話整理成 dimensions JSON
# 目前用 GPT，之後可換成 Ollama（見下方註解）
# ============================================================

def analyze_to_dimensions(conversation_history: list) -> list:
    """
    把完整對話丟給模型，整理出使用者的咖啡廳偏好 dimensions。

    Args:
        conversation_history: [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        dimensions 陣列
    """
    # --- 目前使用 GPT ---
    return _analyze_with_gpt(conversation_history)

    # --- 之後換 Ollama，把上面那行改成下面這行 ---
    # return _analyze_with_ollama(conversation_history)


def _analyze_with_gpt(conversation_history: list) -> list:
    """用 GPT-4o-mini 分析對話"""

    convo_text = "\n".join(
        f"{'使用者' if m['role'] == 'user' else 'AI'}: {m['content']}"
        for m in conversation_history
    )

    system_prompt = """你是資料分析助理。請根據對話內容，輸出一個 JSON 陣列分析使用者偏好。
只輸出合法 JSON，不要加任何說明文字或 markdown。"""

    user_prompt = f"""對話記錄：
{convo_text}

請輸出包含以下 8 個維度的 JSON 陣列，每個物件格式如下：
{{
  "key": "維度英文key",
  "label": "維度中文名稱",
  "description": "根據對話推斷出的使用者偏好，1-2句話",
  "detect_keywords": ["從對話中偵測到的相關詞"],
  "confidence": 0到1的浮點數（推斷的把握程度）,
  "example_prompts": ["可用來確認此偏好的追問範例1", "範例2"]
}}

必須包含這 8 個 key（若對話中沒提到，confidence 設 0.2 並 description 寫「未明確提及」）：
purpose, companion, atmosphere, duration, budget, must_have, location_pref, food"""

    response = client.chat.completions.create(
        model=ANALYZE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1500,
        temperature=0.3,   # 分析任務用較低溫度，輸出更穩定
    )

    raw = response.choices[0].message.content.strip()
    return _safe_parse_json(raw)


def _analyze_with_ollama(conversation_history: list) -> list:
    """
    【預留】之後換 Ollama 時啟用這個函式。
    需要 import requests 並確認 Ollama 已啟動。
    """
    import requests

    convo_text = "\n".join(
        f"{'使用者' if m['role'] == 'user' else 'AI'}: {m['content']}"
        for m in conversation_history
    )

    prompt = f"""以下是對話記錄：
{convo_text}

請輸出 JSON 陣列分析使用者的咖啡廳偏好，包含 purpose/companion/atmosphere/duration/budget/must_have/location_pref/food 共 8 個維度。
每個維度格式：{{"key":"...","label":"...","description":"...","detect_keywords":[],"confidence":0.0,"example_prompts":[]}}
只輸出 JSON，不要其他文字。"""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "llama3", "prompt": prompt, "stream": False},
        timeout=60
    )
    raw = response.json().get("response", "[]")
    return _safe_parse_json(raw)


def _safe_parse_json(raw: str) -> list:
    """安全解析 JSON，失敗時嘗試從字串中擷取"""
    # 去掉可能的 markdown code fence
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return []
