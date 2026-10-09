import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import telebot
from telebot import types
from groq import Groq

# ---------------------------------------------------------
# 1. Servidor HTTP y Mecanismo Self-Ping (Keep-Alive)
# ---------------------------------------------------------
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot activo y corriendo exitosamente.")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"Servidor HTTP escuchando en el puerto {port}...")
    httpd.serve_forever()

def auto_ping_loop():
    """Realiza un disparo HTTP a la URL pública de Render cada 10 min."""
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        print("Aviso: RENDER_EXTERNAL_URL no está definida. Auto-ping desactivado.")
        return

    print(f"Iniciando Auto-Ping hacia: {render_url}")
    while True:
        time.sleep(600)  # Esperar 10 minutos (600 segundos)
        try:
            res = requests.get(render_url, timeout=10)
            print(f"[Auto-Ping] Petición enviada a {render_url} - Status Code: {res.status_code}")
        except Exception as e:
            print(f"[Auto-Ping Error] Falló al enviar petición: {str(e)}")

# Iniciar servidor HTTP en segundo plano
http_thread = threading.Thread(target=run_http_server, daemon=True)
http_thread.start()

# Iniciar hilo de auto-ping en segundo plano
ping_thread = threading.Thread(target=auto_ping_loop, daemon=True)
ping_thread.start()

# ---------------------------------------------------------
# 2. Configuración y Clientes de API
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Faltan las variables TELEGRAM_TOKEN o GROQ_API_KEY en las variables de entorno.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Modelos oficiales de Groq
TEXT_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
VISION_MODELS = ["qwen/qwen3.8-27b"]

chat_histories = {}

SYSTEM_PROMPT = (
    "Eres un asistente virtual empático, claro, servicial y técnico cuando se requiere.\n\n"
    "REGLAS DE FORMATO Y MATEMÁTICAS:\n"
    "- Responde de manera bien estructurada en formato Markdown amigable en español.\n"
    "- NO utilices sintaxis LaTeX como $, $$, \\frac, \\begin, \\end.\n"
    "- Utiliza símbolos Unicode claros para matemáticas (ejemplos: x², √x, a / b, π, ±, ∫, ×, ÷, ∞)."
)

def call_groq_text(messages_payload):
    last_exception = None
    for model_name in TEXT_MODELS:
        try:
            response = groq_client.chat.completions.create(
                model=model_name,
                messages=messages_payload,
                temperature=0.7,
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_exception = e
            print(f"Advertencia: Modelo {model_name} falló: {str(e)}")
    raise last_exception

def call_groq_vision(prompt_text, image_url):
    last_exception = None
    for model_name in VISION_MODELS:
        try:
            response = groq_client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{SYSTEM_PROMPT}\n\n{prompt_text}"},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_exception = e
            print(f"Advertencia: Modelo de visión {model_name} falló: {str(e)}")
    raise last_exception

# ---------------------------------------------------------
# 3. Teclado Interactivo
# ---------------------------------------------------------
def get_control_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_continue = types.InlineKeyboardButton("💬 Continuar Tema", callback_data="topic_continue")
    btn_reset = types.InlineKeyboardButton("🔄 Nuevo Tema", callback_data="topic_reset")
    keyboard.add(btn_continue, btn_reset)
    return keyboard

# ---------------------------------------------------------
# 4. Manejadores de Comandos y Callbacks
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "¡Hola! 👋 Soy tu asistente virtual.\n\n"
        "Puedo ayudarte con:\n"
        "• 💬 **Consultas de texto:** Pregúntame lo que necesites.\n"
        "• 🖼️ **Análisis de imágenes:** Envíame una foto para analizarla.\n\n"
        "Usa los botones al final de los mensajes para administrar la memoria."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=get_control_keyboard())

@bot.callback_query_handler(func=lambda call: call.data in ["topic_continue", "topic_reset"])
def handle_topic_buttons(call):
    chat_id = call.message.chat.id
    if call.data == "topic_reset":
        chat_histories[chat_id] = []
        bot.answer_callback_query(call.id, "Contexto reiniciado")
        bot.send_message(chat_id, "🔄 **Tema reiniciado.** ¿En qué te puedo ayudar ahora?", parse_mode="Markdown")
    elif call.data == "topic_continue":
        bot.answer_callback_query(call.id, "Continuando el tema actual")

# ---------------------------------------------------------
# 5. Manejador de Fotos Recibidas (Visión)
# ---------------------------------------------------------
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    try:
        bot.send_chat_action(chat_id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        user_prompt = message.caption if message.caption else "Describe esta imagen con detalle."

        answer = call_groq_vision(user_prompt, file_url)

        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
        chat_histories[chat_id].append({"role": "user", "content": f"[Foto enviada] {user_prompt}"})
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-14:]

        # Intento de envío con parse_mode="Markdown", respaldo sin formato ante error de sintaxis
        try:
            bot.reply_to(message, answer, parse_mode="Markdown", reply_markup=get_control_keyboard())
        except Exception:
            bot.reply_to(message, answer, reply_markup=get_control_keyboard())

    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {str(e)}")

# ---------------------------------------------------------
# 6. Manejador de Texto Conversacional
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()

    bot.send_chat_action(chat_id, 'typing')
    
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    chat_histories[chat_id].append({"role": "user", "content": text})
    chat_histories[chat_id] = chat_histories[chat_id][-14:]

    payload = [{"role": "system", "content": SYSTEM_PROMPT}] + chat_histories[chat_id]

    try:
        answer = call_groq_text(payload)
        
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-14:]

        # Intento de envío con parse_mode="Markdown", respaldo sin formato ante error de sintaxis
        try:
            bot.reply_to(message, answer, parse_mode="Markdown", reply_markup=get_control_keyboard())
        except Exception:
            bot.reply_to(message, answer, reply_markup=get_control_keyboard())

    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la solicitud: {str(e)}")

# ---------------------------------------------------------
# 7. Inicio del Bucle Polling
# ---------------------------------------------------------
if __name__ == '__main__':
    print("Bot iniciando en Telegram...")
    # Limpieza segura de la cola sin forzar peticiones offset conflictivas
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Aviso en limpieza de webhook: {e}")

    # Bucle continuo con reintento automático integrado
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
                         
