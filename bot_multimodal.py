import os
import io
import urllib.parse
import urllib.request
import telebot
from telebot import types
from groq import Groq

# ---------------------------------------------------------
# 1. CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Faltan las variables de entorno TELEGRAM_TOKEN o GROQ_API_KEY.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Modelos recomendados de Groq
TEXT_MODEL = "llama-3.3-70b-versatile"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Almacenamiento de memoria conversacional por chat (hasta 14 mensajes)
chat_histories = {}

SYSTEM_PROMPT = (
    "Eres un asistente virtual multimodal útil, inteligente y versátil. "
    "Respondes preguntas, realizas investigaciones, ayudas con tareas, traduces texto y escribes o depuras código de programación.\n\n"
    "REGLAS DE FORMATO MATEMÁTICO:\n"
    "- NO utilices sintaxis LaTeX compleja como $,$$, \\frac, \\begin, \\end ni corchetes especiales que puedan fallar en Telegram.\n"
    "- Usa siempre caracteres Unicode claros y símbolos estándar legible para matemáticas (ejemplos: x², √x, a / b, π, ±, ∫, ×, ÷, ∞).\n"
    "- Utiliza formato Markdown de Telegram (negritas, cursivas, bloques de código ```) para organizar la información claramente."
)

# ---------------------------------------------------------
# 2. TECLADO INTERACTIVO (BOTONES CONTINUAR / NUEVO TEMA)
# ---------------------------------------------------------
def get_control_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_continue = types.InlineKeyboardButton("💬 Continuar Tema", callback_data="topic_continue")
    btn_reset = types.InlineKeyboardButton("🔄 Nuevo Tema", callback_data="topic_reset")
    keyboard.add(btn_continue, btn_reset)
    return keyboard

# ---------------------------------------------------------
# 3. MANEJADORES DE COMANDOS Y CALLBACKS
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "¡Hola! 👋 Soy tu asistente multimodal.\n\n"
        "Puedo ayudarte con:\n"
        "• 🧠 Investigaciones, tareas, traducciones y resúmenes.\n"
        "• 💻 Programación y corrección de código.\n"
        "• 👁️ Análisis de imágenes y capturas de pantalla.\n"
        "• 🎨 Generación de imágenes (pídeme 'Dibuja...' o 'Crea una imagen...').\n\n"
        "Control manual de tema: Al final de mis respuestas podrás pulsar 'Continuar Tema' o 'Nuevo Tema' para gestionar el contexto."
    )
    bot.reply_to(message, welcome_text, reply_markup=get_control_keyboard())

@bot.callback_query_handler(func=lambda call: call.data in ["topic_continue", "topic_reset"])
def handle_topic_buttons(call):
    chat_id = call.message.chat.id
    if call.data == "topic_reset":
        chat_histories[chat_id] = []
        bot.answer_callback_query(call.id, "Contexto reiniciado")
        bot.send_message(chat_id, "🔄 **Tema reiniciado.** ¿En qué te ayudo ahora?", parse_mode="Markdown")
    elif call.data == "topic_continue":
        bot.answer_callback_query(call.id, "Continuando el tema actual")

# ---------------------------------------------------------
# 4. MANEJADOR DE FOTOS (ANÁLISIS DE IMÁGENES)
# ---------------------------------------------------------
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')
    
    caption = message.caption if message.caption else "Describe y analiza esta imagen en detalle."
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"[https://api.telegram.org/file/bot](https://api.telegram.org/file/bot){TELEGRAM_TOKEN}/{file_info.file_path}"
        
        response = groq_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": caption},
                        {"type": "image_url", "image_url": {"url": file_url}}
                    ]
                }
            ],
            temperature=0.7,
            max_tokens=1024
        )
        
        answer = response.choices[0].message.content
        
        # Guardar interacción en la memoria
        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
        chat_histories[chat_id].append({"role": "user", "content": f"[Foto enviada] {caption}"})
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-14:]
        
        bot.reply_to(message, answer, parse_mode="Markdown", reply_markup=get_control_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {str(e)}")

# ---------------------------------------------------------
# 5. MANEJADOR DE TEXTO (CHAT Y GENERACIÓN DE IMÁGENES)
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    user_text = message.text.strip()
    
    # Detección para generación de imágenes vía Pollinations.ai
    trigger_words = ["dibuja", "dibujar", "crea una imagen", "haz una imagen", "genera una imagen", "haz un dibujo"]
    if any(phrase in user_text.lower() for phrase in trigger_words):
        bot.send_chat_action(chat_id, 'upload_photo')
        try:
            prompt_encoded = urllib.parse.quote(user_text)
            image_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){prompt_encoded}?width=1024&height=1024&nologo=true"
            
            req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                image_bytes = resp.read()
            
            photo_file = io.BytesIO(image_bytes)
            photo_file.name = 'generated_image.jpg'
            
            bot.send_photo(chat_id, photo_file, caption=f"🖼️ Imagen para: *{user_text}*", parse_mode="Markdown", reply_markup=get_control_keyboard())
            return
        except Exception as e:
            bot.reply_to(message, f"Ocurrió un error al generar la imagen: {str(e)}")
            return

    # Procesamiento de texto normal con Groq
    bot.send_chat_action(chat_id, 'typing')
    
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
        
    chat_histories[chat_id].append({"role": "user", "content": user_text})
    chat_histories[chat_id] = chat_histories[chat_id][-14:]
    
    messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}] + chat_histories[chat_id]
    
    try:
        response = groq_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=messages_payload,
            temperature=0.7,
            max_tokens=2048
        )
        
        answer = response.choices[0].message.content
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-14:]
        
        bot.reply_to(message, answer, parse_mode="Markdown", reply_markup=get_control_keyboard())
    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la solicitud: {str(e)}")

# ---------------------------------------------------------
# 6. SERVIDOR HTTP PARA HEALTH CHECKS EN RENDER Y RUNNER
# ---------------------------------------------------------
import http.server
import socketserver
import threading

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        return

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()
    print("Bot iniciando infinity_polling...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
