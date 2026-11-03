import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
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

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""

# Inicialização de Clientes
app = FastAPI(title="Auditor Fiscal - Bot & Google Sheets Pipeline")

# Configuração da Google AI API
genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Armazenamento em memória dos logs de processamento e envio
processing_logs: List[Dict[str, Any]] = []

def get_sheets_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    if not GOOGLE_CREDENTIALS_JSON:
        raise ValueError("GOOGLE_CREDENTIALS_JSON não configurada nas variáveis de ambiente.")
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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem Telegram: {e}")

def download_telegram_file(file_id: str) -> bytes:
    res_path = requests.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id}, timeout=10).json()
    file_path = res_path["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    file_res = requests.get(download_url, timeout=30)
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
        '  "categoria": "Alimentação / Transporte / Saúde / Lazer / Moradia / Veículo / Educação / Outros",\n'
        '  "pagamento": "PIX / Cartão de Crédito / Cartão de Débito / Dinheiro / Boleto / Não Informado"\n'
        "}\n"
        "3. Se algum campo não estiver visível ou legível na imagem, atribua 'Não Informado' (ou 0.00 para valor).\n"
        "4. Não inclua texto, explicação ou marcações markdown (como ```json) fora do objeto JSON."
    )

    # Suporte a modelos ativos no SDK oficial google-genai
    candidate_models = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
    last_err = None

    for model_name in candidate_models:
        try:
            response = genai_client.models.generate_content(
                model=model_name,
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

            parsed = json.loads(raw_text.strip())
            return parsed
        except Exception as err:
            logger.warning(f"Tentativa com modelo {model_name} falhou: {err}")
            last_err = err

    raise last_err or RuntimeError("Falha ao analisar imagem com Gemini AI.")

def append_to_sheet(data: Dict[str, Any]) -> int:
    if not SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID não configurada nas variáveis de ambiente.")
    
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
    res = worksheet.append_row(row)
    # Retorna número de linhas atualizado se disponível
    return len(worksheet.get_all_values())

@app.post("/webhook")
async def telegram_webhook(request: Request):
    timestamp_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log_entry: Dict[str, Any] = {
        "id": f"log-{int(datetime.now().timestamp() * 1000)}",
        "timestamp": timestamp_str,
        "chat_id": "Desconhecido",
        "username": "Desconhecido",
        "status_gemini": "Pendente",
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

        # Processar apenas mensagens contendo fotos
        if "photo" in message:
            largest_photo = message["photo"][-1]
            file_id = largest_photo["file_id"]

            send_telegram_message(chat_id, "🔍 Processando comprovante fiscal com Gemini...", message_id)

            # 1. Download e Análise com Gemini
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
            except Exception as e_gemini:
                log_entry["status_gemini"] = "Falha"
                log_entry["status_sheets"] = "Cancelado (Erro Gemini)"
                log_entry["erro"] = f"Erro no Gemini: {str(e_gemini)}"
                send_telegram_message(chat_id, f"⚠️ Erro ao analisar comprovante fiscal: {str(e_gemini)}", message_id)
                processing_logs.insert(0, log_entry)
                return Response(status_code=status.HTTP_200_OK)

            # 2. Envio para a Planilha do Google Sheets
            try:
                total_linhas = append_to_sheet(extracted_data)
                log_entry["status_sheets"] = "Enviado com Sucesso"
                log_entry["detalhes"] += f" | Linha registrada: {total_linhas}"
            except Exception as e_sheets:
                log_entry["status_sheets"] = "Falha no Envio"
                log_entry["erro"] = f"Erro Google Sheets: {str(e_sheets)}"
                logger.error(f"Erro ao salvar na planilha Google: {e_sheets}")
                send_telegram_message(chat_id, f"⚠️ Dados extraídos, mas falhou ao gravar na Planilha Google: {str(e_sheets)}", message_id)
                processing_logs.insert(0, log_entry)
                return Response(status_code=status.HTTP_200_OK)

            # 3. Notificação no Telegram
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
        "spreadsheet_id_configured": bool(SPREADSHEET_ID),
        "credentials_configured": bool(GOOGLE_CREDENTIALS_JSON),
        "gemini_configured": bool(GEMINI_API_KEY),
        "logs": processing_logs
    }

@app.get("/", response_class=HTMLResponse)
def dashboard_logs_page():
    total_recebidos = len(processing_logs)
    sucessos_sheets = sum(1 for log in processing_logs if log.get("status_sheets") == "Enviado com Sucesso")
    falhas_sheets = sum(1 for log in processing_logs if "Falha" in log.get("status_sheets", "") or "Erro" in log.get("status_sheets", ""))
    total_valor = sum(log.get("valor", 0.0) for log in processing_logs if log.get("status_sheets") == "Enviado com Sucesso")

    # Status de configurações
    sheets_ok = bool(SPREADSHEET_ID and GOOGLE_CREDENTIALS_JSON)
    gemini_ok = bool(GEMINI_API_KEY)
    telegram_ok = bool(TELEGRAM_BOT_TOKEN)

    # Geração das linhas da tabela
    rows_html = ""
    if not processing_logs:
        rows_html = """
        <tr>
            <td colspan="7" class="empty-state">
                <div style="padding: 40px 20px; text-align: center; color: #64748b;">
                    <div style="font-size: 32px; margin-bottom: 8px;">📋</div>
                    <div style="font-weight: 600; font-size: 15px; color: #334155;">Nenhum comprovante processado até o momento</div>
                    <div style="font-size: 13px; margin-top: 4px;">Envie uma foto de nota fiscal, cupom ou recibo no Telegram para ver o registro em tempo real.</div>
                </div>
            </td>
        </tr>
        """
    else:
        for log in processing_logs:
            is_success = log.get("status_sheets") == "Enviado com Sucesso"
            status_badge = (
                '<span class="badge badge-success">✓ Gravado na Planilha</span>'
                if is_success
                else f'<span class="badge badge-error">✕ {log.get("status_sheets")}</span>'
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
                <td class="text-muted font-mono">{log.get("username")}</td>
            </tr>
            """

    # Mascarar ID da planilha para exibição segura
    sheet_id_display = "Não configurada"
    if SPREADSHEET_ID:
        if len(SPREADSHEET_ID) > 12:
            sheet_id_display = f"{SPREADSHEET_ID[:6]}...{SPREADSHEET_ID[-6:]}"
        else:
            sheet_id_display = SPREADSHEET_ID

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log de Auditoria & Google Sheets - Bot Financeiro</title>
    <meta http-equiv="refresh" content="15">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
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
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }}
        .title-group h1 {{
            font-size: 20px;
            font-weight: 800;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .title-group p {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
        }}
        .status-indicators {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .indicator {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 8px;
            background: #f1f5f9;
        }}
        .indicator.active {{
            background: var(--primary-light);
            color: var(--primary-dark);
        }}
        .indicator.inactive {{
            background: var(--danger-light);
            color: var(--danger);
        }}
        .dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 18px 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }}
        .kpi-card .label {{
            font-size: 12px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .kpi-card .value {{
            font-size: 26px;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            margin-top: 4px;
            color: var(--text-main);
        }}
        .kpi-card .subtext {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }}
        .table-card {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        }}
        .table-header {{
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #ffffff;
        }}
        .table-header h2 {{
            font-size: 15px;
            font-weight: 700;
        }}
        .refresh-btn {{
            background: #ffffff;
            border: 1px solid var(--border-color);
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            color: var(--text-main);
        }}
        .refresh-btn:hover {{
            background: #f1f5f9;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 13px;
        }}
        th {{
            background: #f8fafc;
            padding: 12px 18px;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 14px 18px;
            border-bottom: 1px solid var(--border-color);
            color: #1e293b;
        }}
        tr:hover td {{
            background-color: #f8fafc;
        }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
        .font-bold {{ font-weight: 700; }}
        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}
        .text-muted {{ color: var(--text-muted); }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
        }}
        .badge-success {{
            background: var(--primary-light);
            color: var(--primary-dark);
            border: 1px solid #a7f3d0;
        }}
        .badge-error {{
            background: var(--danger-light);
            color: var(--danger);
            border: 1px solid #fecaca;
        }}
        .pill-category {{
            background: #f1f5f9;
            color: #334155;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .error-msg {{
            font-size: 11px;
            color: var(--danger);
            margin-top: 4px;
            font-family: 'JetBrains Mono', monospace;
        }}
        footer {{
            margin-top: 24px;
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-group">
                <h1>📊 Monitor de Auditoria & Google Sheets</h1>
                <p>Verificação em tempo real dos comprovantes recebidos e gravados na planilha</p>
            </div>
            <div class="status-indicators">
                <div class="indicator {'active' if sheets_ok else 'inactive'}">
                    <span class="dot"></span> Google Sheets {'Conectado' if sheets_ok else 'Pendente'}
                </div>
                <div class="indicator {'active' if gemini_ok else 'inactive'}">
                    <span class="dot"></span> Gemini AI {'Ativo' if gemini_ok else 'Sem Chave'}
                </div>
                <div class="indicator {'active' if telegram_ok else 'inactive'}">
                    <span class="dot"></span> Telegram {'Pronto' if telegram_ok else 'Sem Token'}
                </div>
            </div>
        </header>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="label">Gravados na Planilha</div>
                <div class="value" style="color: var(--primary-dark);">{sucessos_sheets}</div>
                <div class="subtext">Sincronizados com o Google Sheets</div>
            </div>
            <div class="kpi-card">
                <div class="label">Total Processados</div>
                <div class="value">{total_recebidos}</div>
                <div class="subtext">Comprovantes via Telegram</div>
            </div>
            <div class="kpi-card">
                <div class="label">Valor Total Registrado</div>
                <div class="value">R$ {total_valor:.2f}</div>
                <div class="subtext">Soma das notas válidas</div>
            </div>
            <div class="kpi-card">
                <div class="label">ID da Planilha Ativa</div>
                <div class="value font-mono" style="font-size: 15px; margin-top: 8px;">{sheet_id_display}</div>
                <div class="subtext">Aba 0 (Principal)</div>
            </div>
        </div>

        <div class="table-card">
            <div class="table-header">
                <h2>Histórico de Envios para a Planilha do Google</h2>
                <button class="refresh-btn" onclick="window.location.reload()">↻ Atualizar (Auto 15s)</button>
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
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            <div>Auditor Fiscal AI · Integração Telegram & Google Sheets</div>
            <div>Atualização automática a cada 15 segundos</div>
        </footer>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content, status_code=200)
