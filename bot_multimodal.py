import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import telebot
from groq import Groq

# ---------------------------------------------------------
# 1. Servidor HTTP básico para Render
# ---------------------------------------------------------
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot activo y corriendo exitosamente.")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"Servidor HTTP escuchando en el puerto {port}...")
    httpd.serve_forever()

# Iniciar servidor en hilo secundario
http_thread = threading.Thread(target=run_http_server, daemon=True)
http_thread.start()

# ---------------------------------------------------------
# 2. Configuración y Clientes
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Faltan variables de entorno TELEGRAM_TOKEN o GROQ_API_KEY.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Modelos oficiales activos en Groq
MODEL_TEXTO = "openai/gpt-oss-20b"
MODEL_VISION = "openai/gpt-oss-120b"

SYSTEM_PROMPT = (
    "Eres un asistente virtual extremadamente empático, claro, servicial y técnico cuando se requiere. "
    "Responde de manera bien estructurada, en formato markdown utilizando viñetas y un lenguaje claro y amigable en español."
)

# ---------------------------------------------------------
# 3. Manejadores de Telegram
# ---------------------------------------------------------

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "¡Hola! 👋 Soy tu asistente virtual.\n\n"
        "Estoy listo para ayudarte con lo que necesites:\n"
        "• 💬 **Consultas y dudas:** Pregúntame lo que quieras.\n"
        "• 🖼️ **Análisis de imágenes:** Envíame una foto y te la describiré o analizaré.\n"
        "• 🎨 **Generación de imágenes:** Pídeme algo como *'Dibuja un gato astronauta'*\n\n"
        "¿En qué puedo ayudarte hoy?"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        user_prompt = message.caption if message.caption else "Describe esta imagen con detalle."

        response = groq_client.chat.completions.create(
            model=MODEL_VISION,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"},
                        {"type": "image_url", "image_url": {"url": file_url}}
                    ]
                }
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        bot.reply_to(message, response.choices[0].message.content, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    text = message.text.strip()
    text_lower = text.lower()
    keywords_imagen = ["dibuja", "dibujar", "genera una imagen", "crea una imagen", "haz una imagen", "generate image", "draw"]

    if any(kw in text_lower for kw in keywords_imagen):
        try:
            bot.send_chat_action(message.chat.id, 'upload_photo')
            prompt_encoded = requests.utils.quote(text)
            image_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?nologo=true"
            
            bot.send_photo(
                message.chat.id, 
                image_url, 
                caption=f"🎨 Aquí tienes tu imagen para: *\"{text}\"*", 
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.reply_to(message, f"Ocurrió un error al generar la imagen: {str(e)}")
    else:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            response = groq_client.chat.completions.create(
                model=MODEL_TEXTO,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.7,
                max_tokens=2048,
            )
            bot.reply_to(message, response.choices[0].message.content, parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"Ocurrió un error al procesar la solicitud: {str(e)}")

# ---------------------------------------------------------
# 4. Iniciar Polling
# ---------------------------------------------------------
if __name__ == '__main__':
    print("Bot iniciando en Telegram...")
    bot.infinity_polling()
        
