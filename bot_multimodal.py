import os
import io
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import telebot
from telebot import types
from groq import Groq

# ---------------------------------------------------------
# 1. Servidor HTTP para mantener el servicio activo en Render
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

# Iniciar servidor en segundo plano
http_thread = threading.Thread(target=run_http_server, daemon=True)
http_thread.start()

# ---------------------------------------------------------
# 2. Configuración y Clientes de API
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Faltan las variables TELEGRAM_TOKEN o GROQ_API_KEY.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Modelos para la API de Groq
MODEL_TEXTO = "llama3-8b-8192"
MODEL_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"

# Almacenamiento de contexto (hasta 14 mensajes por chat_id)
chat_histories = {}

SYSTEM_PROMPT = (
    "Eres un asistente virtual empático, claro, servicial y técnico cuando se requiere.\n\n"
    "REGLAS DE FORMATO Y MATEMÁTICAS:\n"
    "- Responde de manera bien estructurada en formato Markdown amigable en español.\n"
    "- NO utilices sintaxis LaTeX como $, $$, \\frac, \\begin, \\end.\n"
    "- Utiliza símbolos Unicode claros para matemáticas (ejemplos: x², √x, a / b, π, ±, ∫, ×, ÷, ∞)."
)

# ---------------------------------------------------------
# 3. Teclado Interactivo de Memoria Conversacional
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
        "¡Hola! 👋 Soy tu asistente virtual multimodal.\n\n"
        "Puedo ayudarte con:\n"
        "• 💬 **Consultas de texto:** Pregúntame lo que necesites.\n"
        "• 🖼️ **Análisis de imágenes:** Envíame una foto o captura para analizarla.\n"
        "• 🎨 **Generación de imágenes:** Pídeme cosas como *'Dibuja un paisaje digital'*\n\n"
        "Al final de cada respuesta podrás pulsar 'Continuar Tema' o 'Nuevo Tema' para controlar la memoria."
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
# 5. Manejador de Imágenes (Visión Artificial)
# ---------------------------------------------------------
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    try:
        bot.send_chat_action(chat_id, 'typing')
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
        answer = response.choices[0].message.content

        # Guardar en memoria
        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
        chat_histories[chat_id].append({"role": "user", "content": f"[Foto enviada] {user_prompt}"})
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-14:]

        bot.reply_to(message, answer, parse_mode="Markdown", reply_markup=get_control_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {str(e)}")

# ---------------------------------------------------------
# 6. Manejador de Texto (Chat y Generación de Imágenes)
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()
    text_lower = text.lower()
    keywords_imagen = ["dibuja", "dibujar", "genera una imagen", "crea una imagen", "haz una imagen", "generate image", "draw"]

    # Caso 1: Generación de imágenes vía Pollinations.ai
    if any(kw in text_lower for kw in keywords_imagen):
        try:
            bot.send_chat_action(chat_id, 'upload_photo')
            prompt_encoded = requests.utils.quote(text)
            image_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=1024&nologo=true"
            
            res = requests.get(image_url, timeout=15)
            if res.status_code == 200:
                photo_bytes = io.BytesIO(res.content)
                photo_bytes.name = "generated.jpg"
                bot.send_photo(
                    chat_id, 
                    photo_bytes, 
                    caption=f"🎨 Aquí tienes tu imagen para: *\"{text}\"*", 
                    parse_mode="Markdown",
                    reply_markup=get_control_keyboard()
                )
            else:
                bot.reply_to(message, "No se pudo generar la imagen en Pollinations en este momento.")
        except Exception as e:
            bot.reply_to(message, f"Ocurrió un error al generar la imagen: {str(e)}")
        return

    # Caso 2: Conversación general con memoria usando Groq
    bot.send_chat_action(chat_id, 'typing')
    
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    chat_histories[chat_id].append({"role": "user", "content": text})
    chat_histories[chat_id] = chat_histories[chat_id][-14:]

    payload = [{"role": "system", "content": SYSTEM_PROMPT}] + chat_histories[chat_id]

    try:
        response = groq_client.chat.completions.create(
            model=MODEL_TEXTO,
            messages=payload,
            temperature=0.7,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content
        
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-14:]

        bot.reply_to(message, answer, parse_mode="Markdown", reply_markup=get_control_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la solicitud: {str(e)}")

# ---------------------------------------------------------
# 7. Iniciar Polling
# ---------------------------------------------------------
if __name__ == '__main__':
    print("Bot iniciando en Telegram...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
    
