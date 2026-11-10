import os
import logging
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuração estruturada de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("finance-bot")

# Variáveis do Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""

# Variáveis do Google Sheets
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()

# Chaves Gemini (Principal e Reserva para Failover / Erro 429)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_API_KEY_1 = os.getenv("GEMINI_API_KEY_1", "").strip()

# Lista de chaves ativas para rotação automática
GEMINI_KEYS = [k for k in [GEMINI_API_KEY, GEMINI_API_KEY_1] if k]

# Configurações de Servidor
PORT = int(os.getenv("PORT", "3000"))
PASSCM = os.getenv("PASSCM", "admin123").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
