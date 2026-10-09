import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from google import genai

# Leer credenciales desde variables de entorno
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializar cliente de Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Envíame texto, fotos o documentos y los analizaré con Gemini.")

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=update.message.text
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text("Ocurrió un error al procesar el texto.")
        print(f"Error: {e}")

async def manejar_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    caption = message.caption or "Analiza este archivo y describe su contenido en detalle."
    
    if message.photo:
        tg_file = await message.photo[-1].get_file()
        file_path = "temp_image.jpg"
    elif message.document:
        tg_file = await message.document.get_file()
        file_name = message.document.file_name or "documento"
        file_path = f"temp_{file_name}"
    else:
        return

    await message.reply_text("Procesando archivo...")

    try:
        await tg_file.download_to_drive(file_path)
        uploaded_file = client.files.upload(file=file_path)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded_file, caption]
        )
        await message.reply_text(response.text)
    except Exception as e:
        await message.reply_text("Error al procesar el archivo.")
        print(f"Error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), manejar_texto))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, manejar_archivo))
    
    print("Bot multimodal en ejecución...")
    app.run_polling()