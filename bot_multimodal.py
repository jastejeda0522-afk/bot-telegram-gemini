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
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        print("Aviso: RENDER_EXTERNAL_URL no está definida. Auto-ping desactivado.")
        return

    print(f"Iniciando Auto-Ping hacia: {render_url}")
    while True:
        time.sleep(600)
        try:
            res = requests.get(render_url, timeout=10)
            print(f"[Auto-Ping] Petición enviada a {render_url} - Status Code: {res.status_code}")
        except Exception as e:
            print(f"[Auto-Ping Error] Falló al enviar petición: {str(e)}")

http_thread = threading.Thread(target=run_http_server, daemon=True)
http_thread.start()

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

TEXT_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
VISION_MODELS = ["qwen/qwen3.8-27b"]

chat_histories = {}

# SYSTEM PROMPT ADAPTATIVO Y UNIVERSAL
SYSTEM_PROMPT = (
    "Eres un tutor experto, cálido, directo y sumamente ordenado. "
    "Tu objetivo es adaptarte de forma inteligente al contenido que el usuario te envíe (exámenes de opción múltiple, problemas matemáticos, ejercicios de inglés, código, diagramas o textos en general).\n\n"
    "DIRECTRICES DE RESPUESTA:\n"
    "- **Exámenes / Opción Múltiple:** Indica la respuesta correcta claramente de inmediato y justifica brevemente.\n"
    "- **Problemas matemáticos o técnicos:** Muestra paso a paso fórmulas, sustitución y resultado con unidades.\n"
    "- **Otros temas (inglés, teoría, esquemas):** Explica de forma concisa y muy fácil de leer en pantallas de celular.\n\n"
    "REGLAS ABSOLUTAS DE FORMATO:\n"
    "- PROHIBIDO LaTeX, símbolos de dólar ($), comandos como \\lim, \\frac, \\begin, etc. Usa texto lineal normal.\n"
    "- Símbolos Unicode directos (lim, →, ∫, ∑, √, ±, ≈, ×). Usa corchetes [ ] para matrices o arreglos.\n"
    "- PROHIBIDO usar líneas divisorias (---) o hashtags (#)."
)

def clean_latex_output(text):
    if not text:
        return ""
    text = re.sub(r'\\\[|\\\]|\\\(|\\\)', '', text)
    text = re.sub(r'\$', '', text)
    text = re.sub(r'\\begin\{[a-z]*\*?\}|\\end\{[a-z]*\*?\}', '', text)
    text = re.sub(r'\\displaystyle', '', text)
    text = re.sub(r'\\left|\\right', '', text)
    text = re.sub(r'---+', '', text)
    text = re.sub(r'\\lim_\{([^}]+)\}', r'lim \1', text)
    text = re.sub(r'\\lim', 'lim', text)
    text = re.sub(r'\\to', '→', text)
    text = re.sub(r'\\Delta', 'Δ', text)
    text = re.sub(r'\\sum', '∑', text)
    text = re.sub(r'\\int', '∫', text)
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'√\1', text)
    text = re.sub(r'\\sqrt', '√', text)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1 / \2)', text)
    text = re.sub(r'\{([^}]+)\}', r'\1', text)
    return text

def send_split_message(message, text):
    cleaned = clean_latex_output(text)
    if not cleaned or not cleaned.strip():
        cleaned = "Lo siento, ocurrió un problema al formatear la respuesta."
        
    max_length = 3000
    chunks = [cleaned[i:i + max_length] for i in range(0, len(cleaned), max_length)]
    
    for index, chunk in enumerate(chunks):
        try:
            if index == 0:
                bot.reply_to(message, chunk, parse_mode="Markdown")
            else:
                time.sleep(0.5)
                bot.send_message(message.chat.id, chunk, parse_mode="Markdown")
        except Exception:
            try:
                if index == 0:
                    bot.reply_to(message, chunk)
                else:
                    time.sleep(0.5)
                    bot.send_message(message.chat.id, chunk)
            except Exception as e:
                print(f"[Error enviando mensaje]: {e}")

def call_groq_text(messages_payload):
    full_content = ""
    current_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages_payload)
    
    for _ in range(4):
        response = None
        last_exception = None
        for model_name in TEXT_MODELS:
            try:
                resp = groq_client.chat.completions.create(
                    model=model_name,
                    messages=current_messages,
                    temperature=0.5,
                    max_tokens=1000,
                )
                response = resp
                break
            except Exception as e:
                last_exception = e
                print(f"Advertencia texto: {str(e)}")
        
        if not response:
            if full_content:
                return full_content
            raise last_exception
            
        choice = response.choices[0]
        content_chunk = choice.message.content or ""
        full_content += content_chunk
        
        finish_reason = getattr(choice, 'finish_reason', None)
        if finish_reason in ['length', 'max_tokens']:
            current_messages.append({"role": "assistant", "content": content_chunk})
            current_messages.append({"role": "user", "content": "Continúa exactamente desde donde te quedaste, sin repetir nada."})
        else:
            break
            
    return full_content if full_content.strip() else "No se pudo procesar la respuesta."

# ANÁLISIS VISUAL MULTIPASOS: Extrae la imagen en 2 pasadas complementarias y las une
def call_groq_vision_extract_multiphase(image_url):
    combined_extraction = ""
    
    # Fase 1: Extracción general y lectura principal de textos/enunciados
    prompts_phases = [
        "Analiza la imagen y extrae el texto principal, enunciado, pregunta o contexto general que aparece en ella.",
        "Analiza nuevamente la imagen con atención exhaustiva y extrae cualquier detalle secundario, opciones de respuesta, números, fórmulas, tablas o elementos gráficos que falten."
    ]
    
    for i, phase_prompt in enumerate(prompts_phases):
        for model_name in VISION_MODELS:
            try:
                response = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": phase_prompt},
                                {"type": "image_url", "image_url": {"url": image_url}}
                            ]
                        }
                    ],
                    temperature=0.2,
                    max_tokens=250,
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    combined_extraction += f"\n[Parte {i+1}]: {content.strip()}"
                break
            except Exception as e:
                print(f"Advertencia visión fase {i+1}: {str(e)}")
        time.sleep(0.3) # Pausa corta entre llamadas de visión para evitar saturar TPM/OTPM
        
    if not combined_extraction.strip():
        return "No se pudo extraer información clara de la imagen."
        
    return combined_extraction

# ---------------------------------------------------------
# 3. Manejadores de Comandos
# ---------------------------------------------------------
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "¡Hola! Envíame cualquier imagen compleja (exámenes, ejercicios, inglés, diagramas) y haré un análisis profundo en múltiples pasadas para darte la mejor respuesta.", parse_mode="Markdown")

@bot.message_handler(commands=['reset', 'nuevotema'])
def reset_conversation(message):
    chat_id = message.chat.id
    chat_histories[chat_id] = []
    bot.reply_to(message, "🔄 Historial limpio.", parse_mode="Markdown")

# ---------------------------------------------------------
# 4. Manejador de Fotos con Pipeline Multipasos
# ---------------------------------------------------------
def process_photo_async(message):
    chat_id = message.chat.id
    try:
        bot.send_chat_action(chat_id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        user_prompt = message.caption if message.caption else "Analiza y resuelve detalladamente lo que aparece en esta imagen."

        # Ejecutamos el análisis visual de múltiples pasadas
        extracted_text = call_groq_vision_extract_multiphase(file_url)
        
        full_prompt = f"Contenido consolidado del análisis de la imagen:\n{extracted_text}\n\nInstrucción del usuario: {user_prompt}"
        
        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
        
        recent_history = chat_histories[chat_id][-4:]
        payload = recent_history + [{"role": "user", "content": full_prompt}]
        
        answer = call_groq_text(payload)

        chat_histories[chat_id].append({"role": "user", "content": f"[Foto enviada] {user_prompt}"})
        chat_histories[chat_id].append({"role": "assistant", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-8:]

        send_split_message(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error al procesar la imagen: {str(e)}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    threading.Thread(target=process_photo_async, args=(message,), daemon=True).start()

# ---------------------------------------------------------
# 5. Manejador de Texto
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()

    bot.send_chat_action(chat_id, 'typing')
    
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    chat_histories[chat_id].append({"role": "user", "content": text})
    chat_histories[chat_id] = chat_histories[chat_id][-8:]

    recent_history = chat_histories[chat_id][-4:]

    try:
        answer = call_groq_text(recent_history)
        
        chat_histories[chat_id].append({"role": "user", "content": answer})
        chat_histories[chat_id] = chat_histories[chat_id][-8:]

        send_split_message(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ocurrió un error: {str(e)}")

# ---------------------------------------------------------
# 6. Inicio del Bucle
# ---------------------------------------------------------
if __name__ == '__main__':
    print("Bot iniciando...")
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"Webhook: {e}")

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=15)
        except Exception as e:
            print(f"Polling error: {e}. Reintentando en 5s...")
            time.sleep(5)
