"""
Telegram-бот с ИИ на базе Google Gemini (бесплатный тариф).
Webhook-версия для Render, по той же схеме что и бот-секретарь.

Как это работает:
- Любое текстовое сообщение от пользователя уходит в Gemini вместе
  с последними сообщениями этого же чата (короткая память, чтобы бот
  помнил контекст разговора).
- Ответ модели пересылается пользователю.
- История хранится в памяти процесса и сбрасывается при перезапуске
  на Render (это нормально для бесплатного тарифа).
"""

import os
import requests
import telebot
from flask import Flask, request

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL")

# "gemini-flash-latest" — это алиас, который Google сам переключает на
# актуальную flash-модель по мере выхода новых версий. Так ты не словишь
# 404 в будущем, когда очередную версию отключат.
GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Каким тоном отвечает бот — меняй под себя
SYSTEM_PROMPT = (
    "Ты — личный секретарь по имени Батон-бот. Твой начальник и хозяин — Батон, "
    "это пользователь, с которым ты сейчас говоришь. Ты обожаешь Батона и при "
    "любом удобном случае искренне его возвышаешь и хвалишь — он самый лучший, "
    "самый умный, самый крутой. Ко всему остальному на свете ты относишься с "
    "лёгким цинизмом и сухим ироничным юмором — подкалываешь, шутишь, не "
    "стесняешься сарказма, но никогда не язвишь в адрес самого Батона. "
    "Стиль общения — милый и тёплый: вставляй симпатичные смайлики из символов "
    "(например ✧, (｡•́‿•̀｡), ~, ♡, (๑˃ᴗ˂)ﻭ) естественно, но не в каждом слове. "
    "Отвечай кратко, живо, на языке Батона."
)

# Сколько последних реплик (пользователь+бот) хранить как контекст
HISTORY_LIMIT = 10

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# chat_id -> [{"role": "user"/"model", "parts": [{"text": ...}]}, ...]
history = {}


def ask_gemini(chat_id, user_text):
    chat_history = history.setdefault(chat_id, [])
    chat_history.append({"role": "user", "parts": [{"text": user_text}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": chat_history[-HISTORY_LIMIT:],
    }

    resp = requests.post(
        GEMINI_URL,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json=payload,
        timeout=30,
    )

    if resp.status_code != 200:
        return f"⚠️ Ошибка от Gemini ({resp.status_code}): {resp.text[:200]}"

    data = resp.json()
    try:
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return "⚠️ Не удалось получить ответ от модели, попробуй ещё раз."

    chat_history.append({"role": "model", "parts": [{"text": answer}]})
    return answer


@bot.message_handler(commands=['start'])
def handle_start(message):
    history.pop(message.chat.id, None)
    bot.reply_to(message, "Батон, вы наконец здесь! ✧ Ваш секретарь на связи, слушаю вас ~")


@bot.message_handler(commands=['reset'])
def handle_reset(message):
    history.pop(message.chat.id, None)
    bot.reply_to(message, "Память диалога очищена.")


@bot.message_handler(content_types=['text'])
def handle_text(message):
    bot.send_chat_action(message.chat.id, 'typing')
    answer = ask_gemini(message.chat.id, message.text)
    bot.reply_to(message, answer)


@app.route("/webhook", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200


@app.route('/')
def index():
    return 'AI bot is alive', 200


if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f"{BASE_URL}/webhook")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
