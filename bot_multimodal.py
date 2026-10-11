import os
import time
import threading
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import telebot
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
        time.sleep(600)  # Esperar 10 minutos
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
    "Eres un tutor experto, cálido y sumamente ordenado. "
    "Tu objetivo es explicar los ejercicios paso a paso de forma limpia, directa y muy fácil de leer en pantallas de celular.\n\n"
    "ESTRUCTURA OBLIGATORIA DE RESPUESTA (SIN LÍNEAS SEPARADORAS ---):\n"
    "PROBLEMA\n"
    "[Planteamiento claro o datos iniciales]\n\n"
    "PASOS A SEGUIR\n"
    "1. Fórmula: ...\n"
    "2. Sustitución: ...\n"
    "3. Operaciones: ...\n\n"
    "RESULTADO FINAL\n"
    "[Resultado destacado]\n\n"
    "RESUMEN RÁPIDO\n"
    "- [Punto clave 1]\n"
    "- [Punto clave 2]\n\n"
    "REGLAS ESTRICTAS DE FORMATO Y ESTILO:\n"
    "- PROHIBIDO ABSOLUTAMENTE usar LaTeX complejo o comandos como \\begin{matrix}. \n"
    "- USO DE CORCHETES: Emplea corchetes reales [ ] cuando sea necesario en ejercicios matemáticos, como para representar matrices en renglones separados o agrupar operaciones que lo requieran.\n"
    "- PROHIBIDO usar líneas divisorias con guiones (---) ni hashtags (#).\n"
    "- FRACCIONES ESTÉTICAS: Utiliza caracteres de fracción Unicode (ejemplo: ½, ⅓, ¼, ¾) o la barra diagonal simple (ejemplo: 1/2).\n"
    "- Escribe las potencias de forma sencilla (ejemplo: x², t²) y las raíces usando el símbolo √ (ejemplo: √36).\n"
    "- Mantén un tono sumamente empático, didáctico y cercano."
)

def clean_latex_output(text):
    """Filtro ultra-limpio que elimina LaTeX pesado pero preserva corchetes matemáticos necesarios."""
    if not text:
        return text
    
    # 1. Eliminar solo los comandos de bloques LaTeX complejos, preservando corchetes reales de texto
    text = re.sub(r'\\begin\{[a-z]*\*?\}|\\end\{[a-z]*\*?\}', '', text)
    text = re.sub(r'\$', '', text)
    
    # 2. Eliminar líneas divisorias feas con guiones (---)
    text = re.sub(r'---+', '', text)
    
    # 3. Convertir fracciones comunes a formato Unicode estético (½, ⅓, ¼, ¾)
    text = re.sub(r'\b1/2\b|\(\s*1\s*\)\s*/\s*\(\s*2\s*\)|\\frac\{1\}\{2\}', '½', text)
    text = re.sub(r'\b1/3\b|\(\s*1\s*\)\s*/\s*\(\s*3\s*\)|\\frac\{1\}\{3\}', '⅓', text)
    text = re.sub(r'\b1/4\b|\(\s*1\s*\)\s*/\s*\(\s*4\s*\)|\\frac\{1\}\{4\}', '¼', text)
    text = re.sub(r'\b3/4\b|\(\s*3\s*\)\s*/\s*\(\s*4\s*\)|\\frac\{3\}\{4\}', '¾', text)
    
    # 4. Convertir otras fracciones LaTeX tipo \frac{A}{B} a formato limpio (A / B)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'\1/\2', text)
    
    # 5. Reemplazar símbolos matemáticos comunes por texto plano legible
    text = text.replace(r'\Delta', 'Δ')
    text = text.replace(r'\sum', '∑')
    text = text.replace(r'\int', '∫')
    text = text.replace(r'\prod', '∏')
    text = text.replace(r'\partial', '∂')
    text = text.replace(r'\infty', '∞')
    text = text.replace(r'\pm', '±')
    text = text.replace(r'\approx', '≈')
    text = text.replace(r'\cdot', '×')
    text = text.replace(r'\times', '×')
    text = text.replace(r'\sqrt', '√')
    text = text.replace('\\text', '')
    
    # 6. Limpiar llaves sobrantes que deja el modelo
    text = re.sub(r'\{([^}]+)\}', r'\1', text)
    
    return text

def send_split_message(message, text):
    """Maneja el límite de caracteres dividiendo la respuesta en partes de forma limpia."""
    text = clean_latex_output(text)
    max_length = 3500
    if len(text) <= max_length:
        try:
            bot.reply_to(message, text, parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, text)
    else:
        chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]
        for index, chunk in enumerate(chunks):
            try:
                if index == 0:
                    bot.reply_to(message, chunk + "\n\n*(Continuamos en el siguiente mensaje...)*", parse_mode="Markdown")
                else:
                    bot.send_message(message.chat.id, chunk, parse_mode="Markdown")
            except Exception:
                if index == 0:
                    bot.reply_to(message, chunk)
                else:
                    bot.send_message(message.chat.id, chunk)

def call_groq_text(messages_payload):
    last_exception = None
    for model_name in TEXT_MODELS:
        try:
            response = groq_client.chat.completions.create(
                model=model_name,
                messages=messages_payload,
                temperature=0.7,
                max_tokens=3000,
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
                max_tokens=1500,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_exception = e
            print(f"Advertencia: Modelo de visión {model_name} falló: {str(e)}")
    raise last_exception

# ---------------------------------------------------------
# 3. Manejadores de Comandos
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "¡Hola! 👋 Qué gusto saludarte. Soy tu asistente personal.\n\n"
        "• 💬 **Texto y Matemáticas:** Resuelvo dudas de ingenierías, licenciaturas o cualquier tema.\n"
        "• 🖼️ **Imágenes:** Envíame fotos de ejercicios o esquemas para analizarlos a detalle.\n"
        "• 🔄 **Nuevo tema:** Usa `/reset` para limpiar el historial."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['reset', 'nuevotema'])
def reset_conversation(message):
    chat_id = message.chat.id
    chat_histories[chat_id] = []
    bot.reply_to(message, "🔄 **Tema reiniciado.** ¿Qué proyecto, cálculo o duda abordamos ahora?", parse_mode="Markdown")

# ---------------------------------------------------------
# 4. Manejador de Fotos Recibidas (Visión Asíncrona)
# ---------------------------------------------------------
def process_photo_async(message):
    chat_id = message.chat.id
    try:
        bot.send_chat_action(chat_id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        user_prompt = message.caption if message.caption else "Analiza esta imagen paso a paso y resuelve cualquier ejercicio o problema técnico que contenga."

        answer = call_groq_vision(user_prompt, file_url)

        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
        chat_histories[chat_id].append({"role": "user", "content": f"[Foto enviada] {user_prompt}"})
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-14:]

        send_split_message(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {str(e)}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    threading.Thread(target=process_photo_async, args=(message,), daemon=True).start()

# ---------------------------------------------------------
# 5. Manejador de Texto Conversacional
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

        send_split_message(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la solicitud: {str(e)}")

# ---------------------------------------------------------
# 6. Inicio del Bucle Polling
# ---------------------------------------------------------
if __name__ == '__main__':
    print("Bot iniciando en Telegram...")
    
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"Aviso al limpiar webhook: {e}")

    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=15)
        
