import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from google import genai
from PIL import Image
import io

# 1. Servidor HTTP simulado para el puerto en el plan gratuito de Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot OK")

def start_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=start_health_check_server, daemon=True).start()

# 2. Configuración del Bot de Telegram y Gemini API
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "¡Hola! Soy tu bot de Gemini. Envíame un texto o una foto.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
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
            model='gemini-3.8-flash',
            contents=[prompt, image],
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        print(f"Error Gemini Foto: {e}")
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen:\n{e}")

if __name__ == '__main__':
    print("Bot activo y escuchando...")
    bot.infinity_polling()
    
