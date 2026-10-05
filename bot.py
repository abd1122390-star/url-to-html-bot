import os
import re
import html
import tempfile
from urllib.parse import urlparse

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")

START_TEXT = (
    "🌐 <b>URL TO HTML</b>\n\n"
    "Send me a public website URL and I will fetch its HTML "
    "and return it as an <code>.html</code> file."
)

def valid_url(value: str) -> bool:
    try:
        p = urlparse(value.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🌐 URL TO HTML", callback_data="url_to_html")]]
    await update.message.reply_text(
        START_TEXT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "url_to_html":
        context.user_data["waiting_url"] = True
        await query.message.reply_text(
            "🔗 Send the full URL, for example:\n"
            "<code>https://example.com</code>",
            parse_mode="HTML",
        )

async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_url"):
        return

    url = update.message.text.strip()
    if not valid_url(url):
        await update.message.reply_text(
            "❌ Invalid URL. Please send a full http:// or https:// URL."
        )
        return

    context.user_data["waiting_url"] = False
    status = await update.message.reply_text("⏳ Fetching HTML...")

    try:
        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 URL-to-HTML-Bot/1.0"},
            allow_redirects=True,
        )
        r.raise_for_status()

        content_type = r.headers.get("content-type", "").lower()
        if "html" not in content_type and not re.search(r"<html|<!doctype", r.text, re.I):
            await status.edit_text("❌ The URL does not appear to return an HTML page.")
            return

        data = r.content
        if len(data) > 10 * 1024 * 1024:
            await status.edit_text("❌ The HTML response is larger than 10 MB.")
            return

        filename = urlparse(r.url).netloc.replace(":", "_") or "page"
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:80] + ".html"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as f:
            f.write(data)
            path = f.name

        with open(path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"✅ HTML created\n🌐 {html.escape(r.url)}",
                parse_mode="HTML",
            )

        os.unlink(path)
        await status.delete()

    except requests.RequestException as e:
        await status.edit_text(f"❌ Could not fetch the URL.\n{str(e)[:300]}")
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:300]}")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
