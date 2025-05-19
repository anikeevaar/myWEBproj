from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

TOKEN = "7994081893:AAEsX9QN3095Qu0RYszBuCCZpINdF2p95-o"
ADMIN_ID = 1322101244


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Добро пожаловать в службу поддержки!")


async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_ID:
        return

    await update.message.reply_text("✅ Ваше сообщение отправлено администратору.")

    await context.bot.send_message(
        ADMIN_ID,
        f"📩 Новое сообщение от @{update.message.from_user.username}:\n\n{update.message.text}"
    )


app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admin))
app.run_polling()
