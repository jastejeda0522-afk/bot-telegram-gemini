import os
import telebot
import google.generativeai as genai
from PIL import Image
import io

# Obtener variables de entorno
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Configurar Gemini con el modelo actualizado
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.8-flash')

# Inicializar el Bot de Telegram
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "¡Hola! Soy tu bot de Gemini 3.8 Flash. Envíame un mensaje de texto o una foto.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        response = model.generate_content(message.text)
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
        response = model.generate_content([prompt, image])
        bot.reply_to(message, response.text)
    except Exception as e:
        print(f"Error Gemini Foto: {e}")
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen:\n{e}")

if __name__ == '__main__':
    print("Bot activo y escuchando...")
    bot.infinity_polling()
    
