import logging
import psycopg2
import httpx
import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# 🔑 VARIABLES (Railway)
# =========================

TELEGRAM_TOKEN = "8571397317:AAHu7xMNjsrm0clf-xZ1Mroa6nX-VxTRbYk"
VENICE_API_KEY = "VENICE_INFERENCE_KEY_MELO54gD7Efx0cM5dwLoM2-QJ-FbkSJAdbNNTAf2zv"
DATABASE_URL = "postgresql://postgres:OwNZeaCPLcYkbZnCbWppsmEjMUzbBbMR@monorail.proxy.rlwy.net:46807/railway"

# =========================
# 🪵 LOGS
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# 🗄️ BASE DE DATOS
# =========================
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    nombre TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS warnings (
    telegram_id BIGINT PRIMARY KEY,
    count INT DEFAULT 0
)
""")

conn.commit()

# =========================
# 🎛️ MENÚ
# =========================
keyboard = [
    ["📚 Admisión", "📝 Matrícula"],
    ["📅 Clases", "ℹ️ Información"]
]
markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# =========================
# 🤖 VENICE AI
# =========================
async def preguntar_venice(prompt):
    headers = {
        "Authorization": f"Bearer {VENICE_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "venice-uncensored",
        "messages": [
            {"role": "system", "content": "Eres un asistente universitario amigable de la UTM."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.venice.ai/api/v1/chat/completions",
                json=data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()

        return result["choices"][0]["message"]["content"]

    except Exception as e:
        print("ERROR IA:", e)
        return "🤖 Estoy activo pero la IA no responde ahora."

# =========================
# 🛡️ SEGURIDAD
# =========================
def contiene_link(texto):
    return any(x in texto.lower() for x in ["http://", "https://", "t.me"])

def es_spam(texto):
    spam = ["bitcoin", "ganar dinero", "xxx"]
    return any(p in texto.lower() for p in spam)

async def es_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in ["administrator", "creator"]

# =========================
# 🚨 WARNINGS
# =========================
def agregar_warning(user_id):
    cursor.execute("SELECT count FROM warnings WHERE telegram_id=%s", (user_id,))
    row = cursor.fetchone()

    if row:
        count = row[0] + 1
        cursor.execute("UPDATE warnings SET count=%s WHERE telegram_id=%s", (count, user_id))
    else:
        count = 1
        cursor.execute("INSERT INTO warnings (telegram_id, count) VALUES (%s, %s)", (user_id, count))

    conn.commit()
    return count

# =========================
# 👋 START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bienvenido al Bot UTM\nSelecciona una opción 👇",
        reply_markup=markup
    )

# =========================
# 👋 BIENVENIDA GRUPO
# =========================
async def bienvenida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.new_chat_members:
        for user in update.message.new_chat_members:
            await update.message.reply_text(f"""
👋 Bienvenido/a {user.first_name}

📜 REGLAS:
❌ No spam  
❌ No enlaces  
🤖 Información UTM ▶️: /start  
""")

# =========================
# 📊 ADMIN
# =========================
async def usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    total = cursor.fetchone()[0]
    await update.message.reply_text(f"👥 Usuarios registrados: {total}")

# =========================
# 💬 MENSAJES
# =========================
async def mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    user = update.effective_user

    # Guardar usuario
    cursor.execute(
        "INSERT INTO usuarios (telegram_id, nombre) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user.id, user.first_name)
    )
    conn.commit()

    # 🚫 SPAM
    if es_spam(texto):
        await update.message.delete()
        return

    # 🚫 LINKS
    if contiene_link(texto):
        if not await es_admin(update, context):
            count = agregar_warning(user.id)

            await update.message.delete()
            await update.message.reply_text(f"⚠️ Advertencia {count}/3")

            if count >= 3:
                await context.bot.ban_chat_member(update.effective_chat.id, user.id)

            return

    # ⚡ RESPUESTAS RÁPIDAS
    texto_lower = texto.lower()

    if "admision" in texto_lower:
        respuesta = "📚 Para ingresar debes rendir examen de admisión."
    elif "matricula" in texto_lower:
        respuesta = "📝 La matrícula se hace en el sistema académico."
    elif "clases" in texto_lower:
        respuesta = "📅 Las clases pueden ser virtuales o presenciales."
    else:
        respuesta = await preguntar_venice(texto)

    await update.message.reply_text(respuesta)

# =========================
# 🚀 MAIN
# =========================
def main():
    print("🚀 Bot PRO iniciado...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("usuarios", usuarios))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bienvenida))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje))

    app.run_polling()

if __name__ == "__main__":
    main()