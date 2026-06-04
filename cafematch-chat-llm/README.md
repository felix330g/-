# cafematch-chat-llm

chat_llm 功能測試 repo。對話與分析全部使用 GPT，不需要 Ollama。

---

## 快速啟動

```bash
git clone <this-repo>
cd cafematch-chat-llm

pip install -r requirements.txt

cp .env.example .env
# 編輯 .env，填入 OPENAI_API_KEY

python app.py
# 伺服器跑在 http://localhost:5001
```

---

## API 測試順序

### 1. 取得問題清單
```
GET http://localhost:5001/api/chat_llm/questions
```

### 2. 開始對話（取得開場白 + session_token）
```
POST http://localhost:5001/api/chat_llm/start
```

### 3. 每次使用者回答
```
POST http://localhost:5001/api/chat_llm/respond
Content-Type: application/json

{
  "user_answer": "我想一個人來讀書",
  "question_index": 0,
  "history": []
}
```

### 4. 按「開始分析」
```
POST http://localhost:5001/api/chat_llm/analyze
Content-Type: application/json

{
  "conversation_history": [
    {"role": "assistant", "content": "你好！..."},
    {"role": "user", "content": "我想一個人來讀書"},
    ...
  ],
  "session_token": "從 /start 拿到的 uuid"
}
```

---

## 之後換回 Ollama

只需改 `services/ai_service.py` 的 `analyze_to_dimensions` 函式，
把 `return _analyze_with_gpt(...)` 換成 `return _analyze_with_ollama(...)`，
一行搞定。

---

## 合併到正式專案（3 步）

1. 複製 `services/chat_questions.py` → 正式專案的 `services/`
2. 把 `services/ai_service.py` 裡的新函式貼進正式專案的 `ai_service.py`
3. 把 `app.py` 裡的 `UserChatAnalysis` model 和 4 支路由貼進正式 `app.py`
