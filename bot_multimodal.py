import os
import telebot
import google.generativeai as genai
from PIL import Image
import io

# Configuración de claves desde las variables de entorno de Render
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Configuración de la API de Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Modelo actualizado a Gemini 3.8 Flash
model = genai.GenerativeModel('gemini-3.8-flash')

# Inicialización del Bot de Telegram
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "¡Hola! Soy tu bot con Gemini 3.8 Flash. Envíame texto o una foto para ayudarte.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        response = model.generate_content(message.text)
        bot.reply_to(message, response.text)
    except Exception as e:
        print(f"Error al procesar texto: {e}")
        bot.reply_to(message, "Ocurrió un error al procesar el texto.")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        # Descargar la foto enviada por el usuario
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Convertir bytes a imagen PIL
        image = Image.open(io.BytesIO(downloaded_file))
        
        # Usar el texto de la foto si existe, de lo contrario usar una orden predeterminada
        prompt = message.caption if message.caption else "Describe esta imagen con detalle."
        
        # Enviar prompt e imagen al modelo
        response = model.generate_content([prompt, image])
        bot.reply_to(message, response.text)
    except Exception as e:
        print(f"Error al procesar imagen: {e}")
        bot.reply_to(message, "Ocurrió un error al analizar la imagen.")

if __name__ == '__main__':
    print("Bot activo y escuchando mensajes...")
    bot.infinity_polling()
    
