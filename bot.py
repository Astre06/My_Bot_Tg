import asyncio
import nest_asyncio
import random
import string
import aiohttp
import re
import time
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

nest_asyncio.apply()

MAIL_TM_API = "https://api.mail.tm"

# Store polling tasks per user
polling_tasks = {}

# === Generate email format astreravenXXXX@domain ===
def generate_username():
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"astreraven{suffix}"

# === Get all available domains ===
async def get_all_domains():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MAIL_TM_API}/domains") as resp:
            data = await resp.json()
            return [d['domain'] for d in data['hydra:member']]

# === Try creating an account until success ===
async def create_account():
    domains = await get_all_domains()
    username = generate_username()
    password = "AstreSecret123"
    debug_log = []

    for domain in domains:
        email = f"{username}@{domain}"
        async with aiohttp.ClientSession() as session:
            payload = {"address": email, "password": password}

            async with session.post(f"{MAIL_TM_API}/accounts", json=payload) as resp:
                if resp.status != 201:
                    debug_log.append(f"❌ Failed to create {email} (status: {resp.status})")
                    continue

            async with session.post(f"{MAIL_TM_API}/token", json=payload) as resp:
                token_data = await resp.json()
                if resp.status == 200 and 'token' in token_data:
                    return email, token_data['token']
                else:
                    debug_log.append(f"⚠️ Token fail for {email} (status: {resp.status})")

    raise Exception("All domains failed. Debug:\n" + '\n'.join(debug_log))

# === Get new messages with HTML parsing ===
async def poll_inbox(context: ContextTypes.DEFAULT_TYPE, token, chat_id):
    headers = {"Authorization": f"Bearer {token}"}
    seen_ids = set()

    async with aiohttp.ClientSession() as session:
        while True:
            async with session.get(f"{MAIL_TM_API}/messages", headers=headers) as resp:
                data = await resp.json()
                for msg in data.get('hydra:member', []):
                    msg_id = msg['id']
                    if msg_id not in seen_ids:
                        seen_ids.add(msg_id)
                        async with session.get(f"{MAIL_TM_API}/messages/{msg_id}", headers=headers) as msg_resp:
                            full_msg = await msg_resp.json()
                            subject = full_msg.get('subject', '')
                            body_html = full_msg.get('html', [''])[0]

                            if "Verification code" in body_html:
                                try:
                                    fragment = body_html.split("Verification code：")[-1]
                                    code = fragment.split("<")[0].strip()
                                    code_clean = ''.join(filter(str.isalnum, code))[:8]
                                    await context.bot.send_message(chat_id=chat_id, text=f"📨 Code received: {code_clean}")
                                    continue
                                except:
                                    pass

                            codes = re.findall(r"\b\d{4,8}\b", subject + body_html)
                            if codes:
                                await context.bot.send_message(chat_id=chat_id, text=f"📨 Code received: {codes[0]}")

            await asyncio.sleep(2)

# === /email command ===
async def email_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in polling_tasks:
        polling_tasks[chat_id].cancel()

    await update.message.reply_text("🔧 Creating secure temporary email...")

    try:
        email, token = await create_account()
        await update.message.reply_text(f"📬 Your temp email: `{email}`", parse_mode='Markdown')
        await update.message.reply_text("📡 Listening for incoming emails...")

        task = asyncio.create_task(poll_inbox(context, token, chat_id))
        polling_tasks[chat_id] = task

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# === /cancel command ===
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in polling_tasks:
        polling_tasks[chat_id].cancel()
        del polling_tasks[chat_id]
        await update.message.reply_text("❌ Cancelled. Back to start.")
    else:
        await update.message.reply_text("Nothing is running.")

# === Bot setup ===
BOT_TOKEN = "your_bot_token_here"
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("email", email_command))
app.add_handler(CommandHandler("cancel", cancel_command))

async def set_commands():
    await app.bot.set_my_commands([
        BotCommand("email", "Generate temp email and receive codes"),
        BotCommand("cancel", "Cancel inbox listener and reset")
    ])

if __name__ == "__main__":
    asyncio.run(set_commands())
    print("✅ Bot is running...")
    app.run_polling()
