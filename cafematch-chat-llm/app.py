# ============================================================
# app.py — 測試版（SQLite，不需要 MySQL）
# ============================================================

from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
import os
import uuid

from services.chat_questions import QUESTIONS, TOTAL
from services import ai_service

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")

# ── 資料庫：測試用 SQLite，合併正式專案時換回 MySQL ──────────
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DB_URI", "sqlite:///test.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

CORS(app, supports_credentials=True)


# ============================================================
# DB Model
# ============================================================

class UserChatAnalysis(db.Model):
    """儲存 chat_llm 對話的分析結果"""
    __tablename__ = "user_chat_analyses"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, nullable=True)         # 登入使用者 ID（訪客為 None）
    session_token = db.Column(db.String(64), nullable=False)   # 用來識別同一次對話
    dimensions  = db.Column(db.JSON, nullable=False)           # dimensions 陣列
    conversation = db.Column(db.JSON, nullable=False)          # 完整對話紀錄
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


# ============================================================
# API 路由
# ============================================================

@app.route("/")
def index():
    return "cafematch-chat-llm test server is running ✅"


# ── 1. 取得問題清單 ──────────────────────────────────────────
@app.route("/api/chat_llm/questions", methods=["GET"])
def get_questions():
    """
    回傳所有問題（含進度條資訊）。
    前端可用來預先知道總題數、各題 label。
    """
    result = []
    for i, q in enumerate(QUESTIONS):
        result.append({
            "index":            i,
            "key":              q["key"],
            "label":            q["label"],
            "prompt":           q["prompt"],
            "detect_keywords":  q["detect_keywords"],
            "total":            TOTAL,
            "progress_percent": round((i / TOTAL) * 100),
        })
    return jsonify({"questions": result, "total": TOTAL})


# ── 2. 開場白（第一題） ─────────────────────────────────────
@app.route("/api/chat_llm/start", methods=["POST"])
def chat_start():
    """
    對話起點：產生開場白 + 第一個問題。
    同時產生 session_token 供後續追蹤。
    回傳：{ ai_message, session_token, next_question_index, progress_percent }
    """
    session_token = str(uuid.uuid4())
    first_q = QUESTIONS[0]

    ai_message = ai_service.get_opening_message(first_q["prompt"])

    return jsonify({
        "ai_message":          ai_message,
        "session_token":       session_token,
        "next_question_index": 1,          # 下一題是 index 1
        "progress_percent":    0,
    })


# ── 3. 使用者回答 → GPT 回應 + 銜接下一題 ──────────────────
@app.route("/api/chat_llm/respond", methods=["POST"])
def chat_respond():
    """
    接收使用者回答，回傳 AI 回應並帶出下一題。

    Request body:
    {
        "user_answer":       "使用者的回答",
        "question_index":    目前回答的是第幾題（0-based），
        "history":           [{"role":"user"/"assistant","content":"..."}]
    }

    Response:
    {
        "ai_message":          "AI 回應文字",
        "next_question_index": 下一題的 index（若已是最後題則為 null）,
        "progress_percent":    0-100,
        "is_last":             true/false
    }
    """
    data         = request.get_json() or {}
    user_answer  = data.get("user_answer", "").strip()
    q_index      = data.get("question_index", 0)
    history      = data.get("history", [])

    if not user_answer:
        return jsonify({"error": "user_answer 不可為空"}), 400

    # 已回答完所有問題
    answered_count = q_index + 1
    is_last        = answered_count >= TOTAL

    if is_last:
        # 最後一題：GPT 給結尾語，提示使用者按「開始分析」
        closing_prompt = "謝謝你的回答！現在可以按下「開始分析」，我幫你找出最適合的咖啡廳。"
        ai_message = ai_service.chat_with_gpt(closing_prompt, user_answer, history)
        return jsonify({
            "ai_message":          ai_message,
            "next_question_index": None,
            "progress_percent":    100,
            "is_last":             True,
        })

    # 取得下一題
    next_q     = QUESTIONS[q_index + 1]
    ai_message = ai_service.chat_with_gpt(next_q["prompt"], user_answer, history)

    progress = round((answered_count / TOTAL) * 100)

    return jsonify({
        "ai_message":          ai_message,
        "next_question_index": q_index + 1,
        "progress_percent":    progress,
        "is_last":             False,
    })


# ── 4. 分析：按「開始分析」觸發 ────────────────────────────
@app.route("/api/chat_llm/analyze", methods=["POST"])
def chat_analyze():
    """
    把完整對話丟給模型分析，存入 DB 並回傳 dimensions。

    Request body:
    {
        "conversation_history": [{"role":"user"/"assistant","content":"..."}],
        "session_token":        "uuid string",
        "user_id":              123  // 選填，未登入可省略
    }

    Response:
    {
        "dimensions":  [...],
        "analysis_id": 123
    }
    """
    data         = request.get_json() or {}
    history      = data.get("conversation_history", [])
    session_token = data.get("session_token", str(uuid.uuid4()))
    user_id      = data.get("user_id", None)

    if not history:
        return jsonify({"error": "conversation_history 不可為空"}), 400

    try:
        dimensions = ai_service.analyze_to_dimensions(history)

        record = UserChatAnalysis(
            user_id=user_id,
            session_token=session_token,
            dimensions=dimensions,
            conversation=history,
        )
        db.session.add(record)
        db.session.commit()

        return jsonify({
            "dimensions":  dimensions,
            "analysis_id": record.id,
        })

    except Exception as e:
        db.session.rollback()
        print(f"Analyze error: {e}")
        return jsonify({"error": str(e)}), 500


# ── 5. 查詢分析結果（by analysis_id） ───────────────────────
@app.route("/api/chat_llm/analysis/<int:analysis_id>", methods=["GET"])
def get_analysis(analysis_id):
    """查詢已存入 DB 的分析結果"""
    record = UserChatAnalysis.query.get(analysis_id)
    if not record:
        return jsonify({"error": "找不到此分析結果"}), 404

    return jsonify({
        "analysis_id": record.id,
        "dimensions":  record.dimensions,
        "created_at":  record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)   # port 5001 避免跟正式專案衝突
