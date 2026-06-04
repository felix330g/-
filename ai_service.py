# 在檔案頂端加
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

def chat_with_gpt(question_prompt: str, user_answer: str, history: list) -> str:
    """
    單輪 GPT 對話：
    - 回應使用者的回答
    - 自然地銜接到下一題
    history 格式：[{"role": "user"/"assistant", "content": "..."}]
    """
    system_prompt = """你是一個親切的咖啡廳推薦助理，正在透過對話了解使用者的喜好。
請用 2-3 句話自然回應使用者剛才說的內容，然後提出問題：{question}
語氣要輕鬆自然，像朋友聊天，不要太正式。回應用繁體中文。""".format(question=question_prompt)

    messages = [{"role": "system", "content": system_prompt}]
    messages += history  # 帶入對話歷史
    if user_answer:
        messages.append({"role": "user", "content": user_answer})

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=200,
        temperature=0.7,
    )
    return response.choices[0].message.content
