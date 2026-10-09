import os
import telebot
from google import genai
from PIL import Image
import io

# Obtener variables de entorno
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Inicializar cliente de Gemini con la nueva librería
client = genai.Client(api_key=GEMINI_API_KEY)

# Inicializar Bot de Telegram
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "¡Hola! Soy tu bot de Gemini. Envíame un texto o una foto.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=message.text,
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        print(f"Error Gemini Texto: {e}")
        bot.reply_to(message, f"Ocurrió un error al procesar el texto:\n{e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(downloaded_file))
        
        prompt = message.caption if message.caption else "Describe esta imagen."
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt],
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        print(f"Error Gemini Foto: {e}")
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen:\n{e}")

if __name__ == '__main__':
    print("Bot activo y escuchando...")
    bot.infinity_polling()
    
