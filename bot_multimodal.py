import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from groq import Groq

# ---------------------------------------------------------
# 1. Servidor HTTP básico para mantener activo Render
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

http_thread = threading.Thread(target=run_http_server, daemon=True)
http_thread.start()

# ---------------------------------------------------------
# 2. Configuración, Clientes y Memoria
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Faltan variables TELEGRAM_TOKEN o GROQ_API_KEY.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Modelos oficiales de producción en Groq
MODEL_TEXTO = "llama-3.1-8b-instant"
MODEL_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = (
    "Eres un asistente virtual empático, amigable, claro y técnicamente preciso.\n"
    "REGLAS DE CONVERSACIÓN:\n"
    "1. Usa el historial previo para dar seguimiento a la conversación si el usuario mantiene el tema.\n"
    "2. Si el usuario cambia de tema, responde de manera directa al nuevo tema.\n"
    "3. NUNCA uses sintaxis LaTeX (evita $, $$, \\frac, \\sqrt). Formatea todas las matemáticas con "
    "Markdown claro y símbolos Unicode simples (ejemplos: 'x²', '√x', 'a / b').\n"
    "4. Responde en español con formato limpio y viñetas."
)

# Diccionario global para guardar el historial por chat_id
chat_histories = {}

def get_chat_history(chat_id):
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    return chat_histories[chat_id]

def add_message_to_history(chat_id, role, content):
    history = get_chat_history(chat_id)
    history.append({"role": role, "content": content})
    # Conservar máximo los últimos 14 mensajes (7 turnos)
    if len(history) > 14:
        chat_histories[chat_id] = history[-14:]

def reset_chat_history(chat_id):
    chat_histories[chat_id] = []

# Botones interactivos para controlar el contexto manualmente
def get_topic_keyboard():
    markup = InlineKeyboardMarkup()
    btn_continue = InlineKeyboardButton("💬 Continuar Tema", callback_data="continue_topic")
    btn_reset = InlineKeyboardButton("🔄 Nuevo Tema", callback_data="reset_topic")
    markup.row(btn_continue, btn_reset)
    return markup

# ---------------------------------------------------------
# 3. Manejadores de Eventos
# ---------------------------------------------------------

# Manejo de botones interactivos
@bot.callback_query_handler(func=lambda call: call.data in ["continue_topic", "reset_topic"])
def handle_topic_buttons(call):
    chat_id = call.message.chat.id
    
    if call.data == "continue_topic":
        bot.answer_callback_query(call.id, "Continuamos con el tema actual 👍")
    elif call.data == "reset_topic":
        reset_chat_history(chat_id)
        bot.answer_callback_query(call.id, "¡Tema reiniciado!")
        bot.send_message(chat_id, "🧹 **Memoria reiniciada.** ¿De qué te gustaría hablar ahora?", parse_mode="Markdown")

@bot.message_handler(commands=['start', 'help', 'reset'])
def send_welcome(message):
    chat_id = message.chat.id
    if message.text.startswith('/reset'):
        reset_chat_history(chat_id)
        bot.reply_to(message, "🧹 Memoria reiniciada. ¿En qué te puedo ayudar?")
        return

    welcome_text = (
        "¡Hola! 👋 Soy tu asistente virtual.\n\n"
        "• 💬 **Control manual de tema:** Al final de mis respuestas podrás pulsar *'Continuar Tema'* o *'Nuevo Tema'*.\n"
        "• 🖼️ **Análisis de imágenes:** Envíame fotos con preguntas o solicitudes.\n"
        "• 🎨 **Generación de imágenes:** Pídeme cosas como *'Dibuja un paisaje digital'*\n\n"
        "¿En qué te ayudo hoy?"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

# Manejo de imágenes (Visión)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    try:
        bot.send_chat_action(chat_id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        user_prompt = message.caption if message.caption else "Analiza o describe esta imagen."

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": file_url}
                    }
                ]
            }
        ]

        response = groq_client.chat.completions.create(
            model=MODEL_VISION,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        
        reply_text = response.choices[0].message.content
        bot.reply_to(message, reply_text, parse_mode="Markdown", reply_markup=get_topic_keyboard())
        
        add_message_to_history(chat_id, "user", f"[El usuario envió una imagen]: {user_prompt}")
        add_message_to_history(chat_id, "assistant", reply_text)

    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {str(e)}")

# Manejo de texto y generación de imágenes
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()
    text_lower = text.lower()
    keywords_imagen = ["dibuja", "dibujar", "genera una imagen", "crea una imagen", "haz una imagen", "generate image", "draw"]

    if any(kw in text_lower for kw in keywords_imagen):
        try:
            bot.send_chat_action(chat_id, 'upload_photo')
            prompt_encoded = requests.utils.quote(text)
            image_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?nologo=true"
            
            bot.send_photo(
                chat_id, 
                image_url, 
                caption=f"🎨 Aquí tienes tu imagen para: *\"{text}\"*", 
                parse_mode="Markdown",
                reply_markup=get_topic_keyboard()
            )
            add_message_to_history(chat_id, "user", text)
            add_message_to_history(chat_id, "assistant", f"[Imagen generada sobre: {text}]")
        except Exception as e:
            bot.reply_to(message, f"Ocurrió un error al generar la imagen: {str(e)}")
    else:
        try:
            bot.send_chat_action(chat_id, 'typing')
            
            history = get_chat_history(chat_id)
            messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}]
            
            for msg in history:
                messages_payload.append(msg)
                
            messages_payload.append({"role": "user", "content": text})

            response = groq_client.chat.completions.create(
                model=MODEL_TEXTO,
                messages=messages_payload,
                temperature=0.7,
                max_tokens=2048,
            )
            
            reply_text = response.choices[0].message.content
            bot.reply_to(message, reply_text, parse_mode="Markdown", reply_markup=get_topic_keyboard())
            
            add_message_to_history(chat_id, "user", text)
            add_message_to_history(chat_id, "assistant", reply_text)

        except Exception as e:
            bot.reply_to(message, f"Ocurrió un error al procesar la solicitud: {str(e)}")

# ---------------------------------------------------------
# 4. Iniciar Polling
# ---------------------------------------------------------
if __name__ == '__main__':
    print("Bot iniciando en Telegram...")
    bot.infinity_polling()
    
