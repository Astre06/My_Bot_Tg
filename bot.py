import asyncio
import nest_asyncio
import random
import string
import aiohttp
import re
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters,
    ContextTypes
)

nest_asyncio.apply()

MAIL_TM_API = "https://api.mail.tm"
BOT_TOKEN = os.getenv("BOT_TOKEN")

polling_tasks = {}
seen_ids_map = {}

def generate_username():
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"astreraven{suffix}"

async def get_all_domains():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MAIL_TM_API}/domains") as resp:
            data = await resp.json()
            return [d['domain'] for d in data['hydra:member']]

async def create_account():
    domains = await get_all_domains()
    username = generate_username()
    password = "Neljane143"
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

async def poll_inbox(context: ContextTypes.DEFAULT_TYPE, token, chat_id):
    seen_ids_map[chat_id] = set()
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MAIL_TM_API}/messages", headers=headers) as init_resp:
            init_data = await init_resp.json()
            for msg in init_data.get('hydra:member', []):
                seen_ids_map[chat_id].add(msg['id'])

    seen_ids = seen_ids_map[chat_id]

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

                            # Skip block if only XHTML appears in the whole message
                            if body_html.lower().count("www.w3.org/1999/xhtml") > 2:
                                continue

                            # Clean inner xhtml html segment (if present)
                            body_html = re.sub(r'<html[^>]*xmlns="http://www\\.w3\\.org/1999/xhtml"[^>]*>.*?</html>', '', body_html, flags=re.DOTALL | re.IGNORECASE)

                            # Must include this full <td> pattern to identify correct code
                            td_pattern = r'<td align="left" class="copy lrg-number regular content-padding" style="padding-left: 40px; padding-right: 40px; font-size: 28px; line-height: 32px; letter-spacing: 6px; font-family: \'Netflix Sans\', \'Helvetica Neue\', Roboto, Segoe UI, sans-serif; font-weight: 400; color: #232323; padding-top: 20px;">\\s*(\\d{4,8})\\s*</td>'
                            full_td_match = re.search(td_pattern, body_html, re.IGNORECASE)
                            if full_td_match:
                                sender = full_msg.get('from', {}).get('address', 'Unknown sender')
                                await context.bot.send_message(chat_id=chat_id, text=f"📨 From: {sender}\n🔢 Code: {full_td_match.group(1)}")
                                continue

                            # Fallback: Look for Netflix code after text "Enter this code to sign in"
                            if "Enter this code to sign in" in body_html:
                                segment = body_html.split("Enter this code to sign in", 1)[-1]
                                netflix_block = re.search(r">\\s*(\\d{4,8})\\s*<", segment, re.IGNORECASE)
                                if netflix_block:
                                    sender = full_msg.get('from', {}).get('address', 'Unknown sender')
                                    await context.bot.send_message(chat_id=chat_id, text=f"📨 From: {sender}\n🔢 Code: {netflix_block.group(1)}")
                                    continue

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
                                sender = full_msg.get('from', {}).get('address', 'Unknown sender')
                                await context.bot.send_message(chat_id=chat_id, text=f"📨 From: {sender}\n🔢 Code: {codes[0]}")
            await asyncio.sleep(2)

async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📄 Canva", callback_data="account_canva"),
            InlineKeyboardButton("🎵 Spotify", callback_data="account_spotify")
        ],
        [
            InlineKeyboardButton("🎥 YouTube", callback_data="account_youtube"),
            InlineKeyboardButton("🧚 Sample 1", callback_data="account_sample1")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an account type:", reply_markup=reply_markup)

async def tempmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📧 Mail.tm", callback_data="mail_tm"),
            InlineKeyboardButton("🧚 Sample 1", callback_data="sample_1")
        ],
        [
            InlineKeyboardButton("🧚 Sample 2", callback_data="sample_2"),
            InlineKeyboardButton("🧚 Sample 3", callback_data="sample_3")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a tempmail service or sample:", reply_markup=reply_markup)

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    await query.answer()

    if query.data == "mail_tm":
        keyboard = [
            [
                InlineKeyboardButton("📝 Sign Up", callback_data="signup_tm"),
                InlineKeyboardButton("🔐 Log In", callback_data="login_tm")
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="main_menu")
            ]
        ]
        await query.edit_message_text("📧 Mail.tm Options:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "signup_tm":
        await query.edit_message_text("📝 Creating Mail.tm account...")
        try:
            email, token = await create_account()
            await context.bot.send_message(chat_id=chat_id, text=f"📬 Temp Email: `{email}`", parse_mode='Markdown')
            await context.bot.send_message(chat_id=chat_id, text="📱 Listening for incoming emails...")
            task = asyncio.create_task(poll_inbox(context, token, chat_id))
            polling_tasks[chat_id] = task

except Exception as e:
    await context.bot.send_message(chat_id=chat_id, text=f"❌ Error: {e}")


elif query.data == "login_tm":
        await context.bot.send_message(chat_id=chat_id, text="🔐 Please send your Mail.tm email address:")
        context.user_data['login_step'] = 'awaiting_email'

    elif query.data == "dot_gen":
        await query.edit_message_text("✉️ Please send your real Gmail address:")
        context.user_data['dot_step'] = 'awaiting_gmail'

    elif query.data == "next_dot":
        state = dot_state.get(chat_id)
        if not state:
            await context.bot.send_message(chat_id=chat_id, text="❌ No Gmail in memory. Start with Dot Gen again.")
            return
        state['index'] += 1
        variants = state['variants']
        idx = state['index']
        if idx >= len(variants):
            await context.bot.send_message(chat_id=chat_id, text="✅ No more dot variants.")
            return
        next_email = f"{variants[idx]}@gmail.com"
        keyboard = [[
            InlineKeyboardButton("🔁 New", callback_data="next_dot"),
            InlineKeyboardButton("🔙 Back", callback_data="back_dot")
        ]]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Dot Email:\n`{next_email}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif query.data == "back_dot":
        await context.bot.send_message(chat_id=chat_id, text="✉️ Send your new real Gmail address:")
        context.user_data['dot_step'] = 'awaiting_gmail'
        dot_state.pop(chat_id, None)

    elif query.data == "main_menu":
        keyboard = [
            [
                InlineKeyboardButton("📧 Mail.tm", callback_data="mail_tm"),
                InlineKeyboardButton("🧚 Sample 1", callback_data="sample_1")
            ],
            [
                InlineKeyboardButton("🧚 Sample 2", callback_data="sample_2"),
                InlineKeyboardButton("🧚 Sample 3", callback_data="sample_3")
            ]
        ]
        await query.edit_message_text("Choose a tempmail service or sample:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("sample_") or query.data.startswith("account_"):
        await query.edit_message_text(f"You selected: {query.data.replace('_', ' ').title()}")

async def login_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    step = context.user_data.get('login_step')

    if step == 'awaiting_email':

    if context.user_data.get('dot_step') == 'awaiting_gmail':
        gmail = text.strip().lower()
        if not gmail.endswith("@gmail.com") or '@' not in gmail:
            await update.message.reply_text("⚠️ Please send a valid Gmail address.")
            return
        username = gmail.split("@")[0]
        variants = generate_dot_variants(username)
        dot_state[chat_id] = {"variants": variants, "index": 0, "base": username}
        first = f"{variants[0]}@gmail.com"
        keyboard = [[
            InlineKeyboardButton("🔁 New", callback_data="next_dot"),
            InlineKeyboardButton("🔙 Back", callback_data="back_dot")
        ]]
        await update.message.reply_text(
            f"✅ Dot Email:\n`{first}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        context.user_data['dot_step'] = None
        return

        context.user_data['login_email'] = text
        context.user_data['login_step'] = 'awaiting_password'
        await update.message.reply_text("🔑 Now send your Mail.tm password:")
    elif step == 'awaiting_password':
        email = context.user_data.get('login_email')
        password = text
        async with aiohttp.ClientSession() as session:
            payload = {"address": email, "password": password}
            async with session.post(f"{MAIL_TM_API}/token", json=payload) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    token = token_data.get('token')
                    if token:
                        await update.message.reply_text(f"✅ Logged in as `{email}`", parse_mode='Markdown')
                        await update.message.reply_text("📱 Listening for incoming emails...")
                        task = asyncio.create_task(poll_inbox(context, token, chat_id))
                        polling_tasks[chat_id] = task
                        return
        await update.message.reply_text("❌ Wrong email or password. Please try again.")
        context.user_data['login_step'] = 'awaiting_password'

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in polling_tasks:
        polling_tasks[chat_id].cancel()
        del polling_tasks[chat_id]
    if chat_id in seen_ids_map:
        del seen_ids_map[chat_id]
    context.user_data.clear()
    await update.message.reply_text("🔒 You have been logged out and listener stopped.")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in polling_tasks:
        polling_tasks[chat_id].cancel()
        del polling_tasks[chat_id]
        await update.message.reply_text("❌ Cancelled inbox listener.")
    else:
        await update.message.reply_text("Nothing is running.")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("tempmail", tempmail_command))
    app.add_handler(CommandHandler("account", account_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(CallbackQueryHandler(inline_button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), login_flow_handler))

    await app.bot.set_my_commands([
        BotCommand("logout", "Stop inbox and clear login data"),
        BotCommand("tempmail", "Generate temp email and receive codes"),
        BotCommand("account", "Choose account type for signup"),
        BotCommand("cancel", "Cancel inbox listener and reset")
    ])

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except RuntimeError as e:
        if "event loop is closed" in str(e):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        else:
            raise 
