import os
import io
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, Request, Response, status, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finance-bot")

# Carregamento de Variáveis de Ambiente
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://bot-financeiro-telegram-daqm.onrender.com")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""

app = FastAPI(title="Auditor Fiscal - Bot & Google Sheets Pipeline")

genai_client = None
if GEMINI_API_KEY:
    try:
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e_init:
        logger.error(f"Erro ao inicializar cliente GenAI: {e_init}")

processing_logs: List[Dict[str, Any]] = []

def get_sheets_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    if not GOOGLE_CREDENTIALS_JSON:
        raise ValueError("Variável GOOGLE_CREDENTIALS_JSON não configurada.")
    cred_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    credentials = Credentials.from_service_account_info(cred_dict, scopes=scopes)
    return gspread.authorize(credentials)

def send_telegram_message(chat_id: int, text: str, reply_to_message_id: int = None):
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN não configurado. Mensagem não enviada.")
        return
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem Telegram: {e}")

def download_telegram_file(file_id: str) -> bytes:
    res_path = requests.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id}, timeout=8).json()
    if not res_path.get("ok"):
        raise RuntimeError(f"Erro Telegram getFile: {res_path.get('description', 'Arquivo não encontrado')}")
    file_path = res_path["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    file_res = requests.get(download_url, timeout=25)
    return file_res.content

def optimize_receipt_image(image_bytes: bytes) -> bytes:
    """
    Otimiza a imagem do comprovante fiscal (Melhoria 3):
    - Corrige orientacao EXIF de fotos de smartphone (evita fotos de lado/invertidas)
    - Reduz dimensoes para max 1600px mantendo a proporcao
    - Comprime em JPEG qualidade 85% para reduzir arquivos pesados de 8MB para ~200-300KB
    """
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            max_dimension = 1600
            if max(img.width, img.height) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            optimized_bytes = buf.getvalue()
            logger.info(f"Otimizacao de imagem: {len(image_bytes)/1024:.1f} KB -> {len(optimized_bytes)/1024:.1f} KB")
            return optimized_bytes
    except Exception as e:
        logger.warning(f"Otimizacao Pillow ignorada/indisponivel ({e}). Usando imagem original.")
        return image_bytes

def analyze_receipt(image_bytes: bytes, max_rounds: int = 3) -> Dict[str, Any]:
    if not genai_client:
        raise RuntimeError("GEMINI_API_KEY não configurada ou cliente não inicializado.")

    # Melhoria 3: Otimiza e comprime imagem
    processed_bytes = optimize_receipt_image(image_bytes)

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
        '  "categoria": "Alimentação / Transporte / Saúde / Lazer / Moradia / Veículo / Educação / Outros",\n'
        '  "pagamento": "PIX / Cartão de Crédito / Cartão de Débito / Dinheiro / Boleto / Não Informado"\n'
        "}\n"
        "3. Se algum campo não estiver visível ou legível na imagem, atribua 'Não Informado' (ou 0.00 para valor).\n"
        "4. Não inclua texto, explicação ou marcações markdown (como ```json) fora do objeto JSON."
    )

    # Melhoria 4: Incluindo modelos Lite e alternativas rapidas com menor latencia
    candidate_models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-8b",
        "gemini-3.8-flash",
        "gemini-flash-latest"
    ]
    last_err = None

    for round_num in range(1, max_rounds + 1):
        for model_idx, model_name in enumerate(candidate_models, start=1):
            try:
                logger.info(f"Tentando extração fiscal com {model_name} (rodada {round_num}/{max_rounds}, candidato {model_idx})")
                response = genai_client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=processed_bytes, mime_type="image/jpeg"),
                        user_prompt
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json"
                    )
                )
                raw_text = (response.text or "").strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]

                parsed = json.loads(raw_text.strip())
                logger.info(f"Extração concluída com sucesso usando {model_name}")
                return parsed
            except Exception as err:
                err_str = str(err)
                logger.warning(f"Tentativa com modelo {model_name} falhou: {err_str}")
                last_err = err
                # Backoff adaptativo se for 503 / alta demanda
                if "503" in err_str or "UNAVAILABLE" in err_str or "demand" in err_str:
                    time.sleep(1.5 * round_num)
                else:
                    time.sleep(0.4)

        if round_num < max_rounds:
            pause_time = round_num * 2.5
            logger.info(f"Modelos sobrecarregados na rodada {round_num}. Aguardando {pause_time}s antes de re-tentar...")
            time.sleep(pause_time)

    raise last_err or RuntimeError("Falha ao analisar imagem com Gemini AI após múltiplas tentativas.")

def append_to_sheet(data: Dict[str, Any]) -> int:
    if not SPREADSHEET_ID:
        raise ValueError("Variável SPREADSHEET_ID não configurada.")
    
    gc = get_sheets_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(0)
    
    row = [
        str(data.get("data", "Não Informado")),
        str(data.get("estabelecimento", "Não Informado")),
        str(data.get("tipo_documento", "Não Informado")),
        str(data.get("categoria", "Não Informado")),
        str(data.get("pagamento", "Não Informado")),
        float(data.get("valor", 0.0))
    ]
    worksheet.append_row(row)
    return 1

@app.get("/api/diagnostico", response_class=JSONResponse)
def run_fast_diagnostics():
    host_url = RENDER_EXTERNAL_URL.rstrip("/")
    target_webhook_url = f"{host_url}/webhook"
    
    results = {
        "telegram_token": {"ok": False, "msg": "", "detail": ""},
        "telegram_webhook": {"ok": False, "msg": "", "detail": "", "current_url": ""},
        "gemini_api": {"ok": False, "msg": "", "detail": ""},
        "google_sheets": {"ok": False, "msg": "", "detail": "", "client_email": ""},
    }

    if not TELEGRAM_BOT_TOKEN:
        results["telegram_token"]["ok"] = False
        results["telegram_token"]["msg"] = "Variável TELEGRAM_BOT_TOKEN ausente"
        results["telegram_token"]["detail"] = "Configure a variável TELEGRAM_BOT_TOKEN no painel Environment do Render."
    else:
        try:
            r = requests.get(f"{TELEGRAM_API_BASE}/getMe", timeout=3.5)
            res = r.json()
            if res.get("ok"):
                bot_user = res["result"].get("username", "Desconhecido")
                bot_name = res["result"].get("first_name", "Bot")
                results["telegram_token"]["ok"] = True
                results["telegram_token"]["msg"] = f"Token Válido (@{bot_user} - {bot_name})"
                results["telegram_token"]["detail"] = f"Autenticado com sucesso na API do Telegram (ID: {res['result'].get('id')})."
            else:
                results["telegram_token"]["ok"] = False
                results["telegram_token"]["msg"] = f"Token Inválido ({res.get('description')})"
                results["telegram_token"]["detail"] = "Verifique o token copiado do @BotFather no Telegram."
        except Exception as e:
            results["telegram_token"]["ok"] = False
            results["telegram_token"]["msg"] = "Erro de conexão com api.telegram.org"
            results["telegram_token"]["detail"] = str(e)

    if results["telegram_token"]["ok"]:
        try:
            r_wh = requests.get(f"{TELEGRAM_API_BASE}/getWebhookInfo", timeout=3.5)
            wh_info = r_wh.json().get("result", {})
            registered_url = wh_info.get("url", "")
            results["telegram_webhook"]["current_url"] = registered_url or "Nenhum webhook registrado"

            if registered_url == target_webhook_url:
                pending = wh_info.get("pending_update_count", 0)
                results["telegram_webhook"]["ok"] = True
                results["telegram_webhook"]["msg"] = "Webhook Registrado Corretamente"
                results["telegram_webhook"]["detail"] = f"URL configurada: {registered_url} | Mensagens pendentes: {pending}"
            elif registered_url:
                results["telegram_webhook"]["ok"] = False
                results["telegram_webhook"]["msg"] = "URL do Webhook Diferente"
                results["telegram_webhook"]["detail"] = f"URL no Telegram: '{registered_url}'. Esperado: '{target_webhook_url}'. Clique no botão para registrar."
            else:
                results["telegram_webhook"]["ok"] = False
                results["telegram_webhook"]["msg"] = "Webhook Não Registrado no Telegram"
                results["telegram_webhook"]["detail"] = "O Telegram não sabe para onde enviar as fotos. Clique no botão azul abaixo para registrar."
        except Exception as e:
            results["telegram_webhook"]["ok"] = False
            results["telegram_webhook"]["msg"] = "Erro ao checar Webhook"
            results["telegram_webhook"]["detail"] = str(e)
    else:
        results["telegram_webhook"]["ok"] = False
        results["telegram_webhook"]["msg"] = "Não verificado (Token inválido)"
        results["telegram_webhook"]["detail"] = "Configure o token do Telegram primeiro."

    if not GEMINI_API_KEY:
        results["gemini_api"]["ok"] = False
        results["gemini_api"]["msg"] = "Variável GEMINI_API_KEY ausente"
        results["gemini_api"]["detail"] = "Adicione a chave GEMINI_API_KEY no painel Environment do Render."
    else:
        if len(GEMINI_API_KEY) > 10 and GEMINI_API_KEY.startswith("AIza"):
            results["gemini_api"]["ok"] = True
            results["gemini_api"]["msg"] = "Chave Configurada & Pronta"
            results["gemini_api"]["detail"] = f"Chave AIza...{GEMINI_API_KEY[-4:]} carregada para modelos Gemini Flash."
        else:
            results["gemini_api"]["ok"] = True
            results["gemini_api"]["msg"] = "Chave Carregada"
            results["gemini_api"]["detail"] = "Chave configurada nas variáveis de ambiente."

    client_email = ""
    if not GOOGLE_CREDENTIALS_JSON:
        results["google_sheets"]["ok"] = False
        results["google_sheets"]["msg"] = "GOOGLE_CREDENTIALS_JSON ausente"
        results["google_sheets"]["detail"] = "Cole o JSON da Service Account no Render."
    elif not SPREADSHEET_ID:
        results["google_sheets"]["ok"] = False
        results["google_sheets"]["msg"] = "SPREADSHEET_ID ausente"
        results["google_sheets"]["detail"] = "Configure o ID da planilha do Google."
    else:
        try:
            cred_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            client_email = cred_dict.get("client_email", "")
            results["google_sheets"]["client_email"] = client_email

            gc = get_sheets_client()
            sh = gc.open_by_key(SPREADSHEET_ID)
            sheet_title = sh.title

            results["google_sheets"]["ok"] = True
            results["google_sheets"]["msg"] = f"Conectado: '{sheet_title}'"
            results["google_sheets"]["detail"] = f"Acesso confirmado. Conta autorizada: {client_email}"
        except json.JSONDecodeError:
            results["google_sheets"]["ok"] = False
            results["google_sheets"]["msg"] = "JSON de Credenciais Inválido"
            results["google_sheets"]["detail"] = "O conteúdo de GOOGLE_CREDENTIALS_JSON não é um JSON válido."
        except Exception as e_sheet:
            err_str = str(e_sheet)
            results["google_sheets"]["ok"] = False
            if "403" in err_str or "PERMISSION_DENIED" in err_str:
                results["google_sheets"]["msg"] = "Permissão Negada (403 Forbidden)"
                results["google_sheets"]["detail"] = f"A planilha NÃO foi compartilhada! Abra a planilha no Google Sheets, clique em 'Compartilhar' e adicione: '{client_email}' como EDITOR."
            elif "SpreadsheetNotFound" in err_str or "404" in err_str:
                results["google_sheets"]["msg"] = "Planilha Não Encontrada (404)"
                results["google_sheets"]["detail"] = f"O ID '{SPREADSHEET_ID}' não existe. Verifique na URL da planilha."
            else:
                results["google_sheets"]["msg"] = "Erro de Acesso ao Google Sheets"
                results["google_sheets"]["detail"] = err_str

    return results

@app.get("/registrar-webhook")
def register_telegram_webhook():
    if not TELEGRAM_BOT_TOKEN:
        return HTMLResponse("<h3>Erro: TELEGRAM_BOT_TOKEN não configurado.</h3>", status_code=400)
    
    webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/webhook"
    url_req = f"{TELEGRAM_API_BASE}/setWebhook?url={webhook_url}"
    try:
        res = requests.get(url_req, timeout=8).json()
        if res.get("ok"):
            return RedirectResponse(url="/?msg=webhook_sucesso", status_code=status.HTTP_302_FOUND)
        else:
            return HTMLResponse(f"<h3>Falha ao registrar webhook:</h3><pre>{json.dumps(res, indent=2)}</pre>", status_code=400)
    except Exception as e:
        return HTMLResponse(f"<h3>Erro de conexão:</h3><pre>{str(e)}</pre>", status_code=500)

def process_receipt_background(file_id: str, chat_id: int, chat_user: str, message_id: int, log_entry: Dict[str, Any]):
    """
    Processamento em segundo plano (Melhoria 2):
    - Baixa o arquivo do Telegram
    - Comprime e otimiza a imagem (Melhoria 3)
    - Executa analise com modelos Flash/Lite e retentativas automaticas (Melhoria 4)
    - Grava na planilha do Google Sheets
    - Notifica o usuario no Telegram com o resultado final
    """
    try:
        img_bytes = download_telegram_file(file_id)
        extracted_data = analyze_receipt(img_bytes)

        log_entry["status_gemini"] = "Sucesso"
        log_entry["estabelecimento"] = extracted_data.get("estabelecimento", "Não Informado")
        log_entry["tipo_documento"] = extracted_data.get("tipo_documento", "Não Informado")
        log_entry["categoria"] = extracted_data.get("categoria", "Não Informado")
        log_entry["pagamento"] = extracted_data.get("pagamento", "Não Informado")
        log_entry["valor"] = float(extracted_data.get("valor", 0.0))
        log_entry["detalhes"] = json.dumps(extracted_data, ensure_ascii=False)

        try:
            append_to_sheet(extracted_data)
            log_entry["status_sheets"] = "Enviado com Sucesso"
            log_entry["detalhes"] += " | Gravado na Planilha"
        except Exception as e_sheets:
            log_entry["status_sheets"] = "Falha no Envio"
            log_entry["erro"] = f"Erro Google Sheets: {str(e_sheets)}"
            logger.error(f"Erro ao salvar na planilha Google: {e_sheets}")
            send_telegram_message(
                chat_id,
                f"⚠️ *Dados extraídos*, porém falhou ao gravar na planilha:\n`{str(e_sheets)}`",
                message_id
            )
            processing_logs.insert(0, log_entry)
            return

        success_msg = (
            "✅ *Lançamento Registrado com Sucesso!*\n\n"
            f"• *Data:* {extracted_data.get('data')}\n"
            f"• *Estabelecimento:* {extracted_data.get('estabelecimento')}\n"
            f"• *Documento:* {extracted_data.get('tipo_documento')}\n"
            f"• *Categoria:* {extracted_data.get('categoria')}\n"
            f"• *Pagamento:* {extracted_data.get('pagamento')}\n"
            f"• *Valor:* R$ {float(extracted_data.get('valor', 0)):.2f}\n\n"
            "📊 *Gravado na Planilha do Google Sheets!*"
        )
        send_telegram_message(chat_id, success_msg, message_id)
        processing_logs.insert(0, log_entry)

    except Exception as e_proc:
        err_msg = str(e_proc)
        logger.error(f"Falha no processamento em segundo plano: {err_msg}")
        log_entry["status_gemini"] = "Falha"
        log_entry["status_sheets"] = "Cancelado"
        log_entry["erro"] = err_msg

        if "503" in err_msg or "UNAVAILABLE" in err_msg or "demand" in err_msg:
            user_msg = (
                "⏳ Os servidores de IA do Google estão enfrentando alta demanda atípica no momento "
                "(mesmo após retentativas automáticas). Por favor, reenvie a foto em 1 minuto."
            )
        else:
            user_msg = f"⚠️ Erro ao analisar comprovante fiscal: {err_msg}"

        send_telegram_message(chat_id, user_msg, message_id)
        processing_logs.insert(0, log_entry)

@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    timestamp_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log_entry: Dict[str, Any] = {
        "id": f"log-{int(datetime.now().timestamp() * 1000)}",
        "timestamp": timestamp_str,
        "chat_id": "Desconhecido",
        "username": "Desconhecido",
        "tipo_envio": "Desconhecido",
        "status_gemini": "Em Processamento",
        "status_sheets": "Pendente",
        "estabelecimento": "-",
        "tipo_documento": "-",
        "categoria": "-",
        "pagamento": "-",
        "valor": 0.0,
        "erro": None,
        "detalhes": ""
    }

    try:
        update = await request.json()
        message = update.get("message") or update.get("channel_post")
        
        if not message:
            return Response(status_code=status.HTTP_200_OK)

        chat_id = message["chat"]["id"]
        chat_user = message.get("from", {}).get("username") or message.get("from", {}).get("first_name") or f"ID: {chat_id}"
        message_id = message["message_id"]

        log_entry["chat_id"] = str(chat_id)
        log_entry["username"] = str(chat_user)

        file_id = None
        if "photo" in message and isinstance(message["photo"], list) and len(message["photo"]) > 0:
            file_id = message["photo"][-1]["file_id"]
            log_entry["tipo_envio"] = "Foto (Comprimida)"
        elif "document" in message:
            doc = message["document"]
            mime = doc.get("mime_type", "")
            file_name = doc.get("file_name", "").lower()
            if mime.startswith("image/") or file_name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                file_id = doc["file_id"]
                log_entry["tipo_envio"] = f"Documento de Imagem ({file_name})"
            else:
                send_telegram_message(chat_id, "⚠️ Por favor, envie uma imagem de nota fiscal (JPG, PNG ou foto direta).", message_id)
                return Response(status_code=status.HTTP_200_OK)

        if file_id:
            # Resposta imediata de confirmacao de recebimento no Telegram
            send_telegram_message(
                chat_id,
                "🔍 *Comprovante recebido!* Otimizando imagem e analisando com Gemini em segundo plano...",
                message_id
            )
            # Executa analise, retentativas e gravacao em background sem risco de timeout do webhook
            background_tasks.add_task(
                process_receipt_background,
                file_id,
                chat_id,
                chat_user,
                message_id,
                log_entry
            )
            return Response(status_code=status.HTTP_200_OK)

        return Response(status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Erro geral no webhook: {str(e)}", exc_info=True)
        log_entry["erro"] = str(e)
        log_entry["status_sheets"] = "Erro Geral"
        processing_logs.insert(0, log_entry)
        return Response(status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Erro geral no webhook: {str(e)}", exc_info=True)
        log_entry["erro"] = str(e)
        log_entry["status_sheets"] = "Erro Geral"
        processing_logs.insert(0, log_entry)
        return Response(status_code=status.HTTP_200_OK)

@app.get("/api/logs", response_class=JSONResponse)
def get_logs_json():
    return {
        "status": "ok",
        "total_logs": len(processing_logs),
        "logs": processing_logs
    }

# Template HTML estático (NÃO usa f-string para evitar conflito com chaves do CSS e JS)
HTML_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel de Diagnóstico & Auditoria Fiscal</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8fafc;
            --surface-color: #ffffff;
            --border-color: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --primary: #10b981;
            --primary-dark: #059669;
            --primary-light: #ecfdf5;
            --danger: #ef4444;
            --danger-light: #fef2f2;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }
        .title-group h1 {
            font-size: 20px;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .title-group p { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
        .refresh-btn {
            background: #ffffff;
            border: 1px solid var(--border-color);
            padding: 8px 16px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            color: var(--text-main);
            text-decoration: none;
        }
        .refresh-btn:hover { background: #f1f5f9; }
        .btn-action {
            display: inline-block;
            background: #0284c7;
            color: white;
            font-size: 11px;
            font-weight: 700;
            padding: 7px 12px;
            border-radius: 6px;
            text-decoration: none;
            margin-top: 8px;
        }
        .btn-action:hover { background: #0369a1; }
        .section-title {
            font-size: 14px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 12px;
        }
        .prereqs-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .prereq-card {
            background: var(--surface-color);
            border-radius: 12px;
            padding: 16px 18px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
            border: 1px solid var(--border-color);
            transition: all 0.3s;
        }
        .prereq-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .prereq-title { font-size: 13px; font-weight: 700; }
        .prereq-msg { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
        .prereq-detail { font-size: 11.5px; color: var(--text-muted); line-height: 1.45; word-break: break-word; }
        .badge-status {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
        }
        .badge-ok { background: var(--primary-light); color: var(--primary-dark); border: 1px solid #a7f3d0; }
        .badge-falha { background: var(--danger-light); color: var(--danger); border: 1px solid #fecaca; }
        .badge-loading { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .kpi-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 18px 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }
        .kpi-card .label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
        .kpi-card .value { font-size: 24px; font-weight: 800; font-family: 'JetBrains Mono', monospace; margin-top: 4px; }
        .kpi-card .subtext { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
        .table-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        }
        .table-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .table-header h2 { font-size: 15px; font-weight: 700; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
        th {
            background: #f8fafc;
            padding: 12px 18px;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
        }
        td { padding: 14px 18px; border-bottom: 1px solid var(--border-color); color: #1e293b; }
        tr:hover td { background-color: #f8fafc; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .font-bold { font-weight: 700; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .text-muted { color: var(--text-muted); }
        .pill-category { background: #f1f5f9; color: #334155; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
        .error-msg { font-size: 11px; color: var(--danger); margin-top: 4px; font-family: 'JetBrains Mono', monospace; }
        footer { margin-top: 24px; text-align: center; font-size: 12px; color: var(--text-muted); }
    </style>
</head>
<body>
    <div class="container">
        __ALERT_BOX__

        <header>
            <div class="title-group">
                <h1>🔍 Diagnóstico & Auditoria Fiscal (Google Sheets)</h1>
                <p>Verificação de pré-requisitos, webhook do Telegram e histórico de sincronização</p>
            </div>
            <div>
                <button class="refresh-btn" onclick="executarDiagnostico()">↻ Testar Conexões</button>
            </div>
        </header>

        <div class="section-title">Pré-Requisitos do Sistema</div>
        <div class="prereqs-grid">
            <div id="card-token" class="prereq-card">
                <div class="prereq-header">
                    <span class="prereq-title">1. Token do Bot Telegram</span>
                    <span id="badge-token" class="badge-status badge-loading">Testando...</span>
                </div>
                <div id="msg-token" class="prereq-msg">Verificando com api.telegram.org...</div>
                <div id="detail-token" class="prereq-detail">Aguardando resposta do servidor.</div>
            </div>

            <div id="card-webhook" class="prereq-card">
                <div class="prereq-header">
                    <span class="prereq-title">2. Webhook Telegram Conectado</span>
                    <span id="badge-webhook" class="badge-status badge-loading">Testando...</span>
                </div>
                <div id="msg-webhook" class="prereq-msg">Verificando rota /webhook...</div>
                <div id="detail-webhook" class="prereq-detail">Checando se o Telegram está roteando para este servidor.</div>
                <div id="action-webhook"></div>
            </div>

            <div id="card-gemini" class="prereq-card">
                <div class="prereq-header">
                    <span class="prereq-title">3. Inteligência Artificial (Gemini)</span>
                    <span id="badge-gemini" class="badge-status badge-loading">Testando...</span>
                </div>
                <div id="msg-gemini" class="prereq-msg">Checando chave GEMINI_API_KEY...</div>
                <div id="detail-gemini" class="prereq-detail">Validando credencial da IA.</div>
            </div>

            <div id="card-sheets" class="prereq-card">
                <div class="prereq-header">
                    <span class="prereq-title">4. Google Sheets & Permissão</span>
                    <span id="badge-sheets" class="badge-status badge-loading">Testando...</span>
                </div>
                <div id="msg-sheets" class="prereq-msg">Verificando planilha e conta de serviço...</div>
                <div id="detail-sheets" class="prereq-detail">Checando permissões de edição no Google Drive.</div>
            </div>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="label">Gravados no Google Sheets</div>
                <div class="value" style="color: var(--primary-dark);">__SUCESSOS_SHEETS__</div>
                <div class="subtext">Sincronizados com sucesso</div>
            </div>
            <div class="kpi-card">
                <div class="label">Falhas de Envio</div>
                <div class="value" style="color: var(--danger);">__FALHAS_SHEETS__</div>
                <div class="subtext">Erros detectados</div>
            </div>
            <div class="kpi-card">
                <div class="label">Valor Total Registrado</div>
                <div class="value">R$ __TOTAL_VALOR__</div>
                <div class="subtext">Soma das notas enviadas</div>
            </div>
            <div class="kpi-card">
                <div class="label">Total Recebidos</div>
                <div class="value">__TOTAL_RECEBIDOS__</div>
                <div class="subtext">Mensagens via Telegram</div>
            </div>
        </div>

        <div class="table-card">
            <div class="table-header">
                <h2>Histórico de Envios para a Planilha do Google Sheets</h2>
                <span class="text-muted font-mono" style="font-size: 11px;">Endpoint ativo: /webhook</span>
            </div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Data/Hora</th>
                            <th>Estabelecimento</th>
                            <th>Categoria</th>
                            <th>Doc / Pagamento</th>
                            <th class="text-right">Valor</th>
                            <th class="text-center">Status Google Sheets</th>
                            <th>Usuário Telegram</th>
                        </tr>
                    </thead>
                    <tbody>
                        __ROWS_HTML__
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            <div>Auditor Fiscal AI · Telegram & Google Sheets Pipeline</div>
        </footer>
    </div>

    <script>
        async function executarDiagnostico() {
            try {
                const res = await fetch('/api/diagnostico');
                const data = await res.json();
                
                atualizarCard('token', data.telegram_token);
                atualizarCard('webhook', data.telegram_webhook);
                if (!data.telegram_webhook.ok && data.telegram_token.ok) {
                    document.getElementById('action-webhook').innerHTML = 
                        '<a href="/registrar-webhook" class="btn-action">⚡ Registrar Webhook Automaticamente Agora</a>';
                } else {
                    document.getElementById('action-webhook').innerHTML = '';
                }
                atualizarCard('gemini', data.gemini_api);
                atualizarCard('sheets', data.google_sheets);

            } catch (err) {
                console.error("Falha ao rodar diagnóstico:", err);
            }
        }

        function atualizarCard(prefix, item) {
            const card = document.getElementById('card-' + prefix);
            const badge = document.getElementById('badge-' + prefix);
            const msg = document.getElementById('msg-' + prefix);
            const detail = document.getElementById('detail-' + prefix);

            if (item.ok) {
                card.style.borderLeft = '4px solid #10b981';
                card.style.background = '#ffffff';
                badge.className = 'badge-status badge-ok';
                badge.innerText = '✓ OK';
            } else {
                card.style.borderLeft = '4px solid #ef4444';
                card.style.background = '#fffdfd';
                badge.className = 'badge-status badge-falha';
                badge.innerText = '✕ FALHA';
            }
            msg.innerText = item.msg;
            detail.innerText = item.detail;
        }

        window.addEventListener('DOMContentLoaded', executarDiagnostico);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def dashboard_logs_page(request: Request):
    total_recebidos = len(processing_logs)
    sucessos_sheets = sum(1 for log in processing_logs if log.get("status_sheets") == "Enviado com Sucesso")
    falhas_sheets = sum(1 for log in processing_logs if "Falha" in log.get("status_sheets", "") or "Erro" in log.get("status_sheets", ""))
    total_valor = sum(log.get("valor", 0.0) for log in processing_logs if log.get("status_sheets") == "Enviado com Sucesso")

    alert_box = ""
    if request.query_params.get("msg") == "webhook_sucesso":
        alert_box = (
            '<div style="background: #ecfdf5; border: 1px solid #10b981; color: #065f46; '
            'padding: 12px 18px; border-radius: 10px; margin-bottom: 20px; font-weight: 600; font-size: 13px;">'
            '🎉 Webhook registrado com sucesso no Telegram! Agora seu bot já recebe mensagens e grava na planilha.'
            '</div>'
        )

    rows_html = ""
    if not processing_logs:
        rows_html = """
        <tr>
            <td colspan="7" class="empty-state">
                <div style="padding: 40px 20px; text-align: center; color: #64748b;">
                    <div style="font-size: 32px; margin-bottom: 8px;">📋</div>
                    <div style="font-weight: 600; font-size: 15px; color: #334155;">Nenhum comprovante processado até o momento</div>
                    <div style="font-size: 13px; margin-top: 4px;">Envie uma foto de nota fiscal no Telegram para ver o registro em tempo real.</div>
                </div>
            </td>
        </tr>
        """
    else:
        for log in processing_logs:
            is_success = log.get("status_sheets") == "Enviado com Sucesso"
            status_badge = (
                '<span class="badge-status badge-ok">✓ Gravado no Sheets</span>'
                if is_success
                else f'<span class="badge-status badge-falha">✕ {log.get("status_sheets")}</span>'
            )
            erro_html = f'<div class="error-msg">{log.get("erro")}</div>' if log.get("erro") else ""

            rows_html += f"""
            <tr>
                <td class="font-mono text-muted">{log.get("timestamp")}</td>
                <td class="font-bold">{log.get("estabelecimento")}</td>
                <td><span class="pill-category">{log.get("categoria")}</span></td>
                <td>{log.get("tipo_documento")} / {log.get("pagamento")}</td>
                <td class="font-mono font-bold text-right">R$ {log.get("valor", 0.0):.2f}</td>
                <td class="text-center">{status_badge}{erro_html}</td>
                <td class="text-muted font-mono">{log.get("username")} ({log.get("tipo_envio", "-")})</td>
            </tr>
            """

    html_content = (
        HTML_DASHBOARD_TEMPLATE
        .replace("__ALERT_BOX__", alert_box)
        .replace("__ROWS_HTML__", rows_html)
        .replace("__SUCESSOS_SHEETS__", str(sucessos_sheets))
        .replace("__FALHAS_SHEETS__", str(falhas_sheets))
        .replace("__TOTAL_VALOR__", f"{total_valor:.2f}")
        .replace("__TOTAL_RECEBIDOS__", str(total_recebidos))
    )

    return HTMLResponse(content=html_content, status_code=200)
