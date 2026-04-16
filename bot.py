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
# 🔑 VARIABLES
# =========================

TELEGRAM_TOKEN = "8571397317:AAHu7xMNjsrm0clf-xZ1Mroa6nX-VxTRbYk"
VENICE_API_KEY = "VENICE_INFERENCE_KEY_MELO54gD7Efx0cM5dwLoM2-QJ-FbkSJAdbNNTAf2zv"
DATABASE_URL = "postgresql://postgres:OwNZeaCPLcYkbZnCbWppsmEjMUzbBbMR@monorail.proxy.rlwy.net:46807/railway"

# =========================
# 🪵 LOGS
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# 🗄️ DB
# =========================
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    telegram_id BIGINT PRIMARY KEY,
    nombre TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS warnings (
    telegram_id BIGINT PRIMARY KEY,
    count INT DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS historial (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT,
    mensaje TEXT,
    rol TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
# 🧠 HISTORIAL
# =========================
def guardar_historial(user_id, mensaje, rol):
    cursor.execute(
        "INSERT INTO historial (telegram_id, mensaje, rol) VALUES (%s, %s, %s)",
        (user_id, mensaje, rol)
    )
    conn.commit()

def obtener_historial(user_id):
    cursor.execute("""
        SELECT rol, mensaje FROM historial
        WHERE telegram_id=%s
        ORDER BY id DESC LIMIT 6
    """, (user_id,))
    rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# =========================
# 🤖 VENICE IA
# =========================
async def preguntar_venice(user_id, prompt):
    historial = obtener_historial(user_id)

    messages = [
        {"role": "system", "content": "Eres un asistente universitario experto de la UTM."}
    ] + historial + [
        {"role": "user", "content": prompt}
    ]

    headers = {
        "Authorization": f"Bearer {VENICE_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "venice-uncensored",
        "messages": messages
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.venice.ai/api/v1/chat/completions",
                json=data,
                headers=headers
            )
            result = response.json()

        reply = result["choices"][0]["message"]["content"]

        guardar_historial(user_id, prompt, "user")
        guardar_historial(user_id, reply, "assistant")

        return reply

    except Exception as e:
        print("ERROR IA:", e)
        return "🤖 IA temporalmente no disponible."

# =========================
# 🛡️ SEGURIDAD
# =========================
def contiene_link(texto):
    return any(x in texto.lower() for x in ["http://", "https://", "t.me"])

def es_spam(texto):
    spam = ["crypto", "xxx", "onlyfans", "dinero fácil"]
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
        cursor.execute("INSERT INTO warnings VALUES (%s, %s)", (user_id, count))

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
# 👥 BIENVENIDA
# =========================
async def bienvenida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        await update.message.reply_text(f"""
👋 Bienvenido {user.first_name}

📜 Reglas:
❌ No spam
❌ No links
""")

# =========================
# 📊 STATS
# =========================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM historial")
    mensajes = cursor.fetchone()[0]

    await update.message.reply_text(f"👥 Usuarios: {users}\n💬 Mensajes: {mensajes}")

# =========================
# 📢 BROADCAST
# =========================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await es_admin(update, context):
        return

    mensaje = " ".join(context.args)

    cursor.execute("SELECT telegram_id FROM usuarios")
    users = cursor.fetchall()

    for u in users:
        try:
            await context.bot.send_message(u[0], mensaje)
        except:
            pass

    await update.message.reply_text("📢 Enviado")

# =========================
# 🚫 BAN
# =========================
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await es_admin(update, context):
        return

    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        await context.bot.ban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text("🚫 Usuario baneado")

# =========================
# 💬 MENSAJES
# =========================
async def mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    user = update.effective_user

    cursor.execute(
        "INSERT INTO usuarios VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user.id, user.first_name)
    )
    conn.commit()

    # SPAM
    if es_spam(texto):
        await update.message.delete()
        return

    # LINKS
    if contiene_link(texto):
        if not await es_admin(update, context):
            count = agregar_warning(user.id)
            await update.message.delete()
            await update.message.reply_text(f"⚠️ Advertencia {count}/3")

            if count >= 3:
                await context.bot.ban_chat_member(update.effective_chat.id, user.id)
            return

    # RESPUESTAS RÁPIDAS
    t = texto.lower()
    if "admision" in t:
        respuesta = "📚 Debes rendir examen de admisión."
    elif "matricula" in t:
        respuesta = "📝 Se realiza en el sistema académico."
    elif "clases" in t:
        respuesta = "📅 Modalidad presencial o virtual."
    else:
        respuesta = await preguntar_venice(user.id, texto)

    await update.message.reply_text(respuesta)

# =========================
# 🚀 MAIN
# =========================
def main():
    print("🚀 BOT NIVEL DIOS INICIADO v2")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("ban", ban))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bienvenida))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje))

    app.run_polling()

if __name__ == "__main__":
    main()