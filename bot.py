import os
import sys
import json
import uuid
import logging
import asyncio

from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

import firebase_admin
from firebase_admin import credentials, db

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram токен и URL приложения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
APP_URL = os.environ.get('APP_URL')  # https://your-app-name.onrender.com

# Firebase credentials
firebase_key_json = os.environ.get('FIREBASE_CREDENTIALS')
if not firebase_key_json:
    raise Exception("FIREBASE_CREDENTIALS не установлена")

cred_dict = json.loads(firebase_key_json)
cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
cred = credentials.Certificate(cred_dict)

firebase_admin.initialize_app(cred, {
    'databaseURL': "https://hot-wheels-1-default-rtdb.europe-west1.firebasedatabase.app/"
})
root_ref = db.reference('/activation_codes')

# Flask-приложение
app = Flask(__name__)

# Telegram App
telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# Хендлеры
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Выберите подписку:\n"
        "1. Подписка на месяц — 149₽\n"
        "2. Подписка на год — 1099₽\n\n"
        "Отправьте 1 или 2, чтобы получить ссылку на оплату."
    )

async def choose_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == '1':
        await update.message.reply_text("Оплатите подписку на месяц:\nhttps://t.me/UnionBot?start=pay_month")
    elif text == '2':
        await update.message.reply_text("Оплатите подписку на год:\nhttps://t.me/UnionBot?start=pay_year")
    else:
        await update.message.reply_text("Пожалуйста, отправьте '1' или '2'.")

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    args = context.args
    if not args or args[0].lower() not in ['month', 'year']:
        await update.message.reply_text("Использование: /confirm <month|year>")
        return
    plan = args[0].lower()
    code = str(uuid.uuid4()).replace("-", "").upper()[:10]
    root_ref.child(user_id).set({'code': code, 'plan': plan})
    await update.message.reply_text(f"Оплата подтверждена. Ваш код: {code}")

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    data = root_ref.child(user_id).get()
    if data:
        await update.message.reply_text(f"Ваш код: {data['code']}\nПлан: {data.get('plan')}")
    else:
        await update.message.reply_text("Код не найден. Оплатите подписку.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start /confirm <month|year> /code /help")

# Добавляем хендлеры
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("confirm", confirm_payment))
telegram_app.add_handler(CommandHandler("code", get_code))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, choose_plan))

# Flask endpoint для webhook
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.create_task(telegram_app.process_update(update))
    return "ok"

@app.route("/", methods=["GET"])
def root():
    return "Hello from Telegram bot!", 200

# Устанавливаем Webhook перед первым запросом
async def init_webhook():
    await telegram_app.bot.delete_webhook()
    await telegram_app.bot.set_webhook(url=f"{APP_URL}/{TELEGRAM_TOKEN}")
    logger.info(f"Webhook установлен на: {APP_URL}/{TELEGRAM_TOKEN}")

if __name__ == "__main__":
    asyncio.run(init_webhook())  # ← правильно запускаем асинхронную функцию
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
