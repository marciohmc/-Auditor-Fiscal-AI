import os
import json
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, Response, status
import requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finance-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = FastAPI()
genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def get_sheets_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    cred_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    credentials = Credentials.from_service_account_info(cred_dict, scopes=scopes)
    return gspread.authorize(credentials)

def send_telegram_message(chat_id: int, text: str, reply_to_message_id: int = None):
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    requests.post(url, json=payload)

def download_telegram_file(file_id: str) -> bytes:
    res_path = requests.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id}).json()
    file_path = res_path["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    file_res = requests.get(download_url)
    return file_res.content

def analyze_receipt(image_bytes: bytes) -> Dict[str, Any]:
    system_instruction = (
        "Você é um assistente especialista em auditoria financeira e extração de dados de comprovantes fiscais. "
        "Sua tarefa é analisar imagens de notas fiscais, cupons fiscais e recibos enviados pelos usuários e retornar "
        "estritamente um JSON estruturado com os dados financeiros extraídos."
    )
    user_prompt = (
        "Analise esta imagem de comprovante/nota fiscal e extraia os dados conforme as regras abaixo:\n"
        "1. Identifique se o documento é uma 'Nota Fiscal', 'Cupom Fiscal' ou 'Recibo'.\n"
        "2. Extraia estritamente um JSON no seguinte formato:\n"
        "{\n"
        '  "tipo_documento": "Nota Fiscal / Cupom Fiscal / Recibo",\n'
        '  "data": "DD/MM/AAAA",\n'
        '  "estabelecimento": "Nome do Fornecedor / Estabelecimento",\n'
        '  "valor": 0.00,\n'
        '  "categoria": "Alimentação / Transporte / Saúde / Lazer / Moradia / Veículo / Outros",\n'
        '  "pagamento": "PIX / Cartão de Crédito / Cartão de Débito / Dinheiro / Boleto / Não Informado"\n'
        "}\n"
        "3. Se algum campo não estiver visível ou legível na imagem, atribua 'Não Informado' (ou 0.00 para valor).\n"
        "4. Não inclua texto fora do objeto JSON."
    )

    response = genai_client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            user_prompt
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json"
        )
    )

    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]

    return json.loads(raw_text.strip())

def append_to_sheet(data: Dict[str, Any]):
    gc = get_sheets_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(0)
    row = [
        data.get("data", "Não Informado"),
        data.get("estabelecimento", "Não Informado"),
        data.get("tipo_documento", "Não Informado"),
        data.get("categoria", "Não Informado"),
        data.get("pagamento", "Não Informado"),
        float(data.get("valor", 0.0))
    ]
    worksheet.append_row(row)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        message = update.get("message") or update.get("channel_post")
        if not message:
            return Response(status_code=status.HTTP_200_OK)

        chat_id = message["chat"]["id"]
        message_id = message["message_id"]

        if "photo" in message:
            largest_photo = message["photo"][-1]
            file_id = largest_photo["file_id"]

            send_telegram_message(chat_id, "🔍 Processando comprovante fiscal com Gemini...", message_id)
            img_bytes = download_telegram_file(file_id)
            extracted_data = analyze_receipt(img_bytes)
            append_to_sheet(extracted_data)

            success_msg = (
                "✅ *Lançamento Registrado com Sucesso!*\n\n"
                f"• *Data:* {extracted_data.get('data')}\n"
                f"• *Estabelecimento:* {extracted_data.get('estabelecimento')}\n"
                f"• *Documento:* {extracted_data.get('tipo_documento')}\n"
                f"• *Categoria:* {extracted_data.get('categoria')}\n"
                f"• *Pagamento:* {extracted_data.get('pagamento')}\n"
                f"• *Valor:* R$ {float(extracted_data.get('valor', 0)):.2f}"
            )
            send_telegram_message(chat_id, success_msg, message_id)

        return Response(status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {str(e)}", exc_info=True)
        return Response(status_code=status.HTTP_200_OK)

@app.get("/")
def health_check():
    return {"status": "ok", "service": "finance-bot"}
