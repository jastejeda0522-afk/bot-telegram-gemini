import os
import base64
import urllib.parse
import http.server
import socketserver
import threading
import telebot
from groq import Groq

# 1. Servidor HTTP en segundo plano para mantenerse activo en Render
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot activo, multimodal y generador de imagenes.")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# 2. Clientes de Groq y Telegram
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

client = Groq(api_key=GROQ_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Personalidad idéntica a la mía
SYSTEM_INSTRUCTION = (
    "Eres un colaborador y asistente de IA empático, auténtico, directo y con un toque de ingenio. "
    "Respondes con explicaciones claras, estructuradas y detalladas en español. "
    "Cuando analices imágenes o resuelvas dudas, sé conciso pero exhaustivo, "
    "resaltando puntos clave en negrita y organizando la información para que sea fácil de leer."
)

def send_long_message(message_obj, text):
    max_length = 4000
    for i in range(0, len(text), max_length):
        bot.reply_to(message_obj, text[i:i + max_length])

# 3. Manejador de Texto y Peticiones de Generación de Imágenes
@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_text = message.text.lower()
    
    # Detectar si el usuario pide crear/generar/dibujar una imagen
    keywords_image = ["dibuja", "dibujame", "genera una imagen", "crea una imagen", "haz una imagen", "hazme una imagen"]
    is_image_request = any(kw in user_text for kw in keywords_image)
    
    if is_image_request:
        try:
            bot.reply_to(message, "🎨 Generando tu imagen, dame un segundo...")
            prompt_encoded = urllib.parse.quote(message.text)
            # Servicio gratuito Pollinations AI
            image_url = f"https://pollinations.ai/p/{prompt_encoded}?width=1024&height=1024&seed=42&model=flux"
            bot.send_photo(message.chat.id, photo=image_url, caption=f"Aquí tienes: *{message.text}*", parse_mode="Markdown")
            return
        except Exception as e:
            bot.reply_to(message, f"No pude generar la imagen: {e}")
            return

    # Si es una conversación normal
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": message.text}
            ],
            temperature=0.7
        )
        response_text = completion.choices[0].message.content
        send_long_message(message, response_text)
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la solicitud: {e}")

# 4. Manejador de Análisis de Fotos que te envíen
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        base64_image = base64.b64encode(downloaded_file).decode('utf-8')
        caption = message.caption if message.caption else "Analiza esta imagen detalladamente"
        
        completion = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": caption},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.7
        )
        response_text = completion.choices[0].message.content
        send_long_message(message, response_text)
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al analizar la imagen: {e}")

if __name__ == "__main__":
    bot.infinity_polling()
    
