import os
import time
import http.server
import socketserver
import threading
from google import genai
import telebot

# 1. Servidor HTTP en segundo plano para Render
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot activo y funcionando.")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# 2. Inicialización de clientes y APIs
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Función auxiliar para llamar a Gemini con reintentos si ocurre un error 503
def generate_with_retry(contents):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=contents
            )
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(2)  # Espera 2 segundos antes de reintentar
                continue
            raise e

# 3. Manejadores del bot de Telegram
@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        text_response = generate_with_retry(message.text)
        bot.reply_to(message, text_response)
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar el texto: {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        caption = message.caption if message.caption else "Describe esta imagen"
        
        contents = [
            {"mime_type": "image/jpeg", "data": downloaded_file},
            caption
        ]
        
        text_response = generate_with_retry(contents)
        bot.reply_to(message, text_response)
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {e}")

# 4. Iniciar el bot
if __name__ == "__main__":
    bot.infinity_polling()
