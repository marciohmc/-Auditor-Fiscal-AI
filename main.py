import os
import json
import logging
import time
import threading
import urllib.parse
import hashlib
import re
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Any, List, Set

from fastapi import FastAPI, Request, Response, BackgroundTasks, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import requests
import io
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None
    PYPDF_AVAILABLE = False

try:
    from huggingface_hub import InferenceClient
    HF_HUB_AVAILABLE = True
except ImportError:
    InferenceClient = None
    HF_HUB_AVAILABLE = False

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finance-bot")

# Carregamento de Variáveis de Ambiente
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_1 = os.getenv("GEMINI_API_KEY_1")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
PASSCM = os.getenv("PASSCM", "").strip()
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
HF_MODEL_URL = os.getenv("HF_MODEL_URL", "https://api-inference.huggingface.co/models/microsoft/Florence-2-large")
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "helloworld")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""

def is_authenticated(request: Request) -> bool:
    """Verifica se o usuário possui o cookie de sessão válido gerado a partir da senha PASSCM."""
    passcm = os.getenv("PASSCM", "").strip()
    if not passcm:
        # Se a variável PASSCM não estiver definida no ambiente, permite acesso livre ao painel
        return True
    session_cookie = request.cookies.get("auth_session")
    if not session_cookie:
        return False
    expected_token = hashlib.sha256(f"auth_session_token:{passcm}".encode()).hexdigest()
    return session_cookie == expected_token

def render_login_html(error_msg: str = None, notice_msg: str = None) -> str:
    """Gera a interface visual da tela de login responsiva em HTML."""
    passcm = os.getenv("PASSCM", "").strip()
    
    error_html = f'<div class="alert-danger">{error_msg}</div>' if error_msg else ""
    
    notice_html = ""
    if notice_msg:
        notice_html = f'<div class="alert-warning">{notice_msg}</div>'
    elif not passcm:
        notice_html = '<div class="alert-warning">⚠️ A variável <b>PASSCM</b> não está configurada no ambiente do Render. Defina a senha no painel Environment para ativar a restrição de acesso.</div>'

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Acesso Restrito - Auditor Fiscal Bot</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --border-color: #334155;
            --primary: #10b981;
            --primary-hover: #059669;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --danger: #ef4444;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .login-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 40px;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        }}
        .login-header {{
            text-align: center;
            margin-bottom: 32px;
        }}
        .icon-circle {{
            width: 64px;
            height: 64px;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            margin: 0 auto 16px;
        }}
        .login-header h1 {{
            font-size: 22px;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 6px;
        }}
        .login-header p {{
            font-size: 13px;
            color: var(--text-muted);
        }}
        .form-group {{
            margin-bottom: 24px;
        }}
        .form-group label {{
            display: block;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 8px;
        }}
        .input-field {{
            width: 100%;
            padding: 14px 16px;
            background: #0f172a;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            color: #ffffff;
            font-size: 15px;
            font-family: 'JetBrains Mono', monospace;
            outline: none;
            transition: all 0.2s;
        }}
        .input-field:focus {{
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
        }}
        .btn-submit {{
            width: 100%;
            padding: 14px;
            background: var(--primary);
            color: #ffffff;
            border: none;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .btn-submit:hover {{
            background: var(--primary-hover);
        }}
        .alert-danger {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
            padding: 12px;
            border-radius: 10px;
            font-size: 13px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .alert-warning {{
            background: rgba(245, 158, 11, 0.1);
            border: 1px solid rgba(245, 158, 11, 0.3);
            color: #fde68a;
            padding: 12px;
            border-radius: 10px;
            font-size: 12px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .footer-text {{
            text-align: center;
            margin-top: 24px;
            font-size: 12px;
            color: var(--text-muted);
        }}
    </style>
</head>
<body>
    <div class="login-card">
        <div class="login-header">
            <div class="icon-circle">🔐</div>
            <h1>Acesso ao Painel</h1>
            <p>Informe a senha de administrador (PASSCM) para visualizar os dados de auditoria</p>
        </div>

        {error_html}
        {notice_html}

        <form action="/login" method="POST">
            <div class="form-group">
                <label for="password">Senha de Acesso (PASSCM)</label>
                <input type="password" id="password" name="password" class="input-field" placeholder="Digite a senha..." required autofocus>
            </div>
            <button type="submit" class="btn-submit">🔑 Entrar no Painel</button>
        </form>

        <div class="footer-text">
            Bot Financeiro Telegram & Google Sheets
        </div>
    </div>
</body>
</html>
"""


# Carrega a chave principal e a secundária/reserva
GEMINI_KEYS = [
    GEMINI_API_KEY,
    GEMINI_API_KEY_1
]
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS if k and k.strip()]
current_key_index = 0

def get_gemini_client():
    """Retorna um cliente configurado com a chave ativa no momento (GEMINI_API_KEY ou GEMINI_API_KEY_1)."""
    global current_key_index
    if not GEMINI_KEYS:
        raise ValueError("Nenhuma chave (GEMINI_API_KEY ou GEMINI_API_KEY_1) foi configurada.")
    api_key = GEMINI_KEYS[current_key_index % len(GEMINI_KEYS)]
    return genai.Client(api_key=api_key)

def rotate_gemini_key():
    """Alterna automaticamente para a próxima chave de reserva."""
    global current_key_index
    if len(GEMINI_KEYS) > 1:
        prev_idx = current_key_index % len(GEMINI_KEYS)
        current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
        new_idx = current_key_index % len(GEMINI_KEYS)
        logger.warning(f"⚠️ Chave Gemini do índice {prev_idx} esgotada/limite de cota (429). Alternando para chave do índice {new_idx} (GEMINI_API_KEY_1)...")
    else:
        logger.warning("⚠️ Limite de cota atingido e apenas 1 chave Gemini está configurada.")

# Inicialização de Clientes
app = FastAPI(title="Auditor Fiscal - Bot & Google Sheets Pipeline")

# Armazenamento em memória dos logs de processamento e envio
processing_logs: List[Dict[str, Any]] = []

# Mecanismos de Prevenção de Duplicidade e Controle de Concorrência
processed_update_ids: OrderedDict[int, float] = OrderedDict()  # update_id -> timestamp
in_progress_locks: Set[str] = set()                            # lock_key ("chat_id:message_id:file_id")
sheets_write_lock = threading.Lock()                          # Trava exclusiva para leitura e escrita na planilha

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

# Controle de sincronização do histórico do Google Sheets ao religar o servidor
sheets_history_loaded = False
last_sheets_load_time = 0.0

def carregar_historico_planilha(force: bool = False) -> int:
    """
    Lê todas as abas da planilha do Google Sheets ao iniciar/religar o servidor ou sob demanda,
    populando a lista processing_logs com cache de 120s para evitar estouro de cota 429.
    """
    global sheets_history_loaded, last_sheets_load_time
    if not SPREADSHEET_ID or not GOOGLE_CREDENTIALS_JSON:
        logger.warning("SPREADSHEET_ID ou GOOGLE_CREDENTIALS_JSON não configurados. Leitura do histórico ignorada.")
        return 0

    now = time.time()
    if sheets_history_loaded and not force and (now - last_sheets_load_time < 120):
        return 0

    logs_carregados = 0
    try:
        gc = get_sheets_client()
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheets = sh.worksheets()

        existing_ids = {log.get("id") for log in processing_logs if log.get("id")}
        novos_logs = []

        for ws in worksheets:
            nome_aba = ws.title
            try:
                rows = ws.get_all_values()
            except APIError as e_api:
                logger.warning(f"Cota do Google Sheets (429) atada na aba {nome_aba}: {e_api}")
                break
            except Exception as e_rows:
                logger.warning(f"Erro ao ler linhas da aba {nome_aba}: {e_rows}")
                continue

            if len(rows) <= 1:
                continue

            # Itera a partir da 2ª linha (pulando a linha de cabeçalho)
            for idx, linha in enumerate(rows[1:], start=2):
                if not linha or len(linha) < 2:
                    continue

                log_id = f"sheet-{nome_aba}-{idx}"
                if log_id in existing_ids:
                    continue

                if len(linha) >= 14:
                    data_comprovante = str(linha[0]).strip()
                    hora_comprovante = str(linha[1]).strip()
                    estabelecimento = str(linha[2]).strip()
                    tipo_doc = str(linha[3]).strip()
                    categoria = str(linha[4]).strip()
                    pagamento = str(linha[5]).strip()
                    bandeira = str(linha[6]).strip()
                    try:
                        valor_float = float(str(linha[7]).replace("R$", "").replace(" ", "").replace(",", ".").strip())
                    except ValueError:
                        valor_float = 0.0
                    try:
                        desconto_float = float(str(linha[8]).replace("R$", "").replace(" ", "").replace(",", ".").strip())
                    except ValueError:
                        desconto_float = 0.0
                    try:
                        troco_float = float(str(linha[9]).replace("R$", "").replace(" ", "").replace(",", ".").strip())
                    except ValueError:
                        troco_float = 0.0
                    try:
                        tributos_float = float(str(linha[10]).replace("R$", "").replace(" ", "").replace(",", ".").strip())
                    except ValueError:
                        tributos_float = 0.0
                    responsavel = str(linha[11]).strip() if str(linha[11]).strip() else "Não Informado"
                    comprovante_raw = str(linha[12]).strip()
                    observacao = str(linha[13]).strip()
                else:
                    data_comprovante = str(linha[0]).strip() if len(linha) > 0 else ""
                    hora_comprovante = "Não Informada"
                    estabelecimento = str(linha[1]).strip() if len(linha) > 1 else "Não Informado"
                    tipo_doc = str(linha[2]).strip() if len(linha) > 2 else "Não Informado"
                    categoria = str(linha[3]).strip() if len(linha) > 3 else "Outros"
                    pagamento = str(linha[4]).strip() if len(linha) > 4 else "Não Informado"
                    bandeira = "Não Informada"
                    valor_float = 0.0
                    if len(linha) > 5:
                        try:
                            valor_float = float(str(linha[5]).replace("R$", "").replace(" ", "").replace(",", ".").strip())
                        except ValueError:
                            valor_float = 0.0
                    desconto_float = 0.0
                    troco_float = 0.0
                    tributos_float = 0.0
                    responsavel = str(linha[6]).strip() if len(linha) > 6 and str(linha[6]).strip() else "Não Informado"
                    comprovante_raw = str(linha[7]).strip() if len(linha) > 7 else ""
                    observacao = str(linha[8]).strip() if len(linha) > 8 else ""

                link_url = ""
                if 'HYPERLINK("' in comprovante_raw:
                    try:
                        link_url = comprovante_raw.split('HYPERLINK("')[1].split('"')[0]
                    except Exception:
                        link_url = ""
                elif comprovante_raw.startswith("http"):
                    link_url = comprovante_raw

                log_entry = {
                    "id": log_id,
                    "timestamp": f"{data_comprovante} {hora_comprovante}".strip() if hora_comprovante != "Não Informada" else (data_comprovante or datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
                    "chat_id": "Planilha Google",
                    "username": responsavel,
                    "status_gemini": "Sucesso",
                    "status_sheets": "Enviado com Sucesso",
                    "estabelecimento": estabelecimento or "Não Informado",
                    "tipo_documento": tipo_doc or "Não Informado",
                    "categoria": categoria or "Outros",
                    "pagamento": pagamento or "Não Informado",
                    "bandeira": bandeira,
                    "valor": valor_float,
                    "desconto": desconto_float,
                    "troco": troco_float,
                    "tributos": tributos_float,
                    "data_comprovante": data_comprovante,
                    "hora_comprovante": hora_comprovante,
                    "observacao": observacao or None,
                    "responsavel": responsavel,
                    "origem_foto": "Sincronizado do Google Sheets",
                    "link_telegram": link_url,
                    "aba_planilha": nome_aba,
                    "erro": None,
                    "detalhes": f"Carregado automaticamente da aba {nome_aba} do Google Sheets | Linha: {idx}"
                }

                novos_logs.append(log_entry)
                existing_ids.add(log_id)
                logs_carregados += 1

        if novos_logs:
            processing_logs.extend(novos_logs)

        sheets_history_loaded = True
        last_sheets_load_time = time.time()
        logger.info(f"✅ Histórico do Google Sheets carregado com sucesso: {logs_carregados} lançamentos sincronizados.")
    except Exception as e_sheets_load:
        logger.error(f"⚠️ Erro ao carregar histórico do Google Sheets: {e_sheets_load}")

    return logs_carregados

@app.on_event("startup")
def startup_load_sheets_history():
    """Executa a leitura das abas do Google Sheets ao religar/iniciar o servidor."""
    if not sheets_history_loaded:
        carregar_historico_planilha()

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

def download_telegram_file(file_id: str) -> tuple[bytes, str]:
    res_path = requests.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id}, timeout=10).json()
    file_path = res_path.get("result", {}).get("file_path", "")
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}" if file_path else ""
    if not download_url:
        raise ValueError(f"Não foi possível obter o caminho do arquivo no Telegram para o ID: {file_id}")
    file_res = requests.get(download_url, timeout=30)
    return file_res.content, download_url

def analyze_receipt(file_bytes: bytes, is_pdf: bool = False) -> dict:
    """
    Analisa comprovante (foto ou PDF de nota fiscal).
    Se for PDF, tenta extração nativa digital via pypdf (em milissegundos).
    Se for foto ou PDF escaneado, realiza OCR via OCR.space.
    """
    texto_bruto = ""

    # 1. Se for arquivo PDF, tenta extração nativa digital em memória via pypdf
    if is_pdf and PYPDF_AVAILABLE and PdfReader is not None:
        try:
            logger.info("Tentando extração de texto digital do PDF via pypdf...")
            reader = PdfReader(io.BytesIO(file_bytes))
            pypdf_text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    pypdf_text += extracted + "\n"
            if len(pypdf_text.strip()) >= 15:
                texto_bruto = pypdf_text.strip()
                logger.info(f"Texto do PDF extraído digitalmente com sucesso ({len(texto_bruto)} chars)!")
        except Exception as e_pdf:
            logger.warning(f"Extração nativa do PDF via pypdf falhou ({e_pdf}). Acionando OCR.space...")

    # 2. Se não for PDF ou se a extração nativa digital retornou vazia, usa a API OCR.space
    if not texto_bruto:
        api_key = os.getenv("OCR_SPACE_API_KEY", "helloworld")
        url = "https://api.ocr.space/parse/image"
        
        payload = {
            'isOverlayRequired': False,
            'apikey': api_key,
            'language': 'por',
        }
        if is_pdf:
            payload['filetype'] = 'PDF'
            files = {'file': ('nota_fiscal.pdf', file_bytes, 'application/pdf')}
        else:
            files = {'file': ('comprovante.jpg', file_bytes, 'image/jpeg')}

        try:
            logger.info("Enviando arquivo para a API OCR.space...")
            response = requests.post(url, data=payload, files=files, timeout=30)
            resultado = response.json()
            
            if resultado.get("IsErroredOnProcessing"):
                erro_msg = resultado.get("ErrorMessage", ["Erro desconhecido"])[0]
                logger.error(f"Erro no OCR.space: {erro_msg}")
                return {"status_leitura": "ilegivel", "mensagem_erro": f"Erro OCR: {erro_msg}"}
                
            parsed_results = resultado.get("ParsedResults", [])
            if not parsed_results:
                return {"status_leitura": "ilegivel", "mensagem_erro": "Nenhum texto detectado no documento."}
                
            texto_bruto = parsed_results[0].get("ParsedText", "")
            if not texto_bruto.strip():
                return {"status_leitura": "ilegivel", "mensagem_erro": "Documento ilegível ou sem texto."}

            logger.info(f"Texto bruto capturado via OCR.space:\n{texto_bruto[:200]}...")

        except requests.exceptions.Timeout:
            logger.error("Timeout ao conectar com o OCR.space.")
            return {"status_leitura": "ilegivel", "mensagem_erro": "O serviço de OCR demorou muito para responder."}
        except Exception as e:
            logger.error(f"Erro no processamento do OCR: {str(e)}")
            return {"status_leitura": "ilegivel", "mensagem_erro": f"Erro interno ao processar OCR: {str(e)}"}

    # --- EXTRAÇÃO AVANÇADA POR PADRÕES (REGEX & OPERACIONAIS) ---
    linhas = [l.strip() for l in texto_bruto.replace('\r\n', '\n').split('\n') if l.strip()]
    texto_upper = texto_bruto.upper()
    
    # 1. Identificação de Comprovante Pix e Extração do Recebedor e do Pagador (Quem emitiu)
    is_pix = any(k in texto_upper for k in ["PIX", "COMPROVANTE DE TRANSFERENCIA", "COMPROVANTE DE PAGAMENTO PIX", "TRANSFERENCIA PIX", "TRANSFERÊNCIA PIX"])
    recebedor_pix = ""
    doc_recebedor = ""
    pagador_pix = ""
    doc_pagador = ""

    if is_pix:
        termos_invalidos = ["INSTITUIÇÃO", "INSTITUICAO", "BANCO", "CHAVE", "VALOR", "DATA", "HORA", "PAGADOR", "ORIGEM", "AUTENTICAÇÃO", "TIPO DE CHAVE", "ID DA TRANSAÇÃO", "TRANSFERÊNCIA", "COMPROVANTE"]

        # --- A. QUEM RECEBEU (Destinatário / Favorecido) ---
        ancoras_recebedor = [
            r'(?:DESTINAT[ÁA]RIO|NOME\s+DO\s+DESTINAT[ÁA]RIO|RECEBEDOR|NOME\s+DO\s+RECEBEDOR|BENEFICI[ÁA]RIO|FAVORECIDO|QUEM\s+RECEBEU|PAGO\s+PARA|PAGO\s+A|ENVIADO\s+PARA|PARA)[\s:]+([A-Za-zÀ-ÖØ-öø-ÿ0-9\.\-\s]{3,60})',
            r'(?:DADOS\s+DO\s+DESTINAT[ÁA]RIO|DADOS\s+DE\s+QUEM\s+RECEBEU)[\s\S]*?(?:NOME|RECEBEDOR)[\s:]+([A-Za-zÀ-ÖØ-öø-ÿ0-9\.\-\s]{3,60})'
        ]
        for padrao in ancoras_recebedor:
            m_rec = re.search(padrao, texto_bruto, re.IGNORECASE)
            if m_rec:
                cand = m_rec.group(1).strip()
                cand_linha = [p.strip() for p in cand.split('\n') if p.strip()][0]
                cand_linha = re.sub(r'[\:\,\-\;]+$', '', cand_linha).strip()
                if len(cand_linha) >= 3 and not any(k in cand_linha.upper() for k in termos_invalidos):
                    recebedor_pix = cand_linha
                    break

        if not recebedor_pix:
            rotulo_regex = r'^(PARA|DESTINAT[ÁA]RIO|RECEBEDOR|BENEFICI[ÁA]RIO|FAVORECIDO|QUEM\s+RECEBEU|DADOS\s+DO\s+RECEBEDOR|DADOS\s+DO\s+DESTINAT[ÁA]RIO):?$'
            for idx_l, linha_txt in enumerate(linhas):
                if re.search(rotulo_regex, linha_txt, re.IGNORECASE):
                    for offset in [1, 2]:
                        if idx_l + offset < len(linhas):
                            cand_linha = linhas[idx_l + offset].strip()
                            cand_linha_upper = cand_linha.upper()
                            if cand_linha_upper.startswith("NOME:"):
                                cand_linha = cand_linha[5:].strip()
                            if len(cand_linha) >= 3 and not any(k in cand_linha.upper() for k in termos_invalidos):
                                if not re.match(r'^(CPF|CNPJ|CHAVE|BANCO|INSTITUI)', cand_linha_upper):
                                    recebedor_pix = cand_linha
                                    break
                    if recebedor_pix:
                        break

        # --- B. QUEM EMITIU O PIX (Pagador / Origem / Titular) ---
        ancoras_pagador = [
            r'(?:PAGADOR|NOME\s+DO\s+PAGADOR|ORIGEM|DADOS\s+DO\s+PAGADOR|DADOS\s+DE\s+QUEM\s+PAGOU|QUEM\s+PAGOU|DEBITADO\s+DE|CONTA\s+DE\s+D[ÉE]BITO|CONTA\s+DE\s+ORIGEM|PAGO\s+POR|ENVIADO\s+POR|TITULAR)[\s:]+([A-Za-zÀ-ÖØ-öø-ÿ0-9\.\-\s]{3,60})',
            r'(?:DADOS\s+DO\s+PAGADOR|DADOS\s+DE\s+QUEM\s+PAGOU|ORIGEM|CONTA\s+DE\s+ORIGEM|DEBITADO\s+DE)[\s\S]*?(?:NOME|PAGADOR|TITULAR)[\s:]+([A-Za-zÀ-ÖØ-öø-ÿ0-9\.\-\s]{3,60})',
            r'(?:^|\n)\s*DE[\s:]+([A-Za-zÀ-ÖØ-öø-ÿ0-9\.\-\s]{3,60})'
        ]
        for padrao_p in ancoras_pagador:
            m_pag = re.search(padrao_p, texto_bruto, re.IGNORECASE)
            if m_pag:
                cand_p = m_pag.group(1).strip()
                cand_p_linha = [p.strip() for p in cand_p.split('\n') if p.strip()][0]
                cand_p_linha = re.sub(r'[\:\,\-\;]+$', '', cand_p_linha).strip()
                if len(cand_p_linha) >= 3 and not any(k in cand_p_linha.upper() for k in termos_invalidos):
                    if cand_p_linha.upper() != (recebedor_pix or "").upper():
                        pagador_pix = cand_p_linha
                        break

        if not pagador_pix:
            rotulo_pagador_regex = r'^(DE|PAGADOR|ORIGEM|QUEM\s+PAGOU|DADOS\s+DO\s+PAGADOR|DADOS\s+DE\s+QUEM\s+PAGOU|CONTA\s+DE\s+ORIGEM|DEBITADO\s+DE):?$'
            for idx_p, linha_p in enumerate(linhas):
                if re.search(rotulo_pagador_regex, linha_p.strip(), re.IGNORECASE):
                    for offset in [1, 2, 3]:
                        if idx_p + offset < len(linhas):
                            cand_pl = linhas[idx_p + offset].strip()
                            cand_pl_upper = cand_pl.upper()
                            if cand_pl_upper.startswith("NOME:"):
                                cand_pl = cand_pl[5:].strip()
                            elif re.match(r'^(PAGADOR|TITULAR):\s*', cand_pl, re.IGNORECASE):
                                cand_pl = re.sub(r'^(PAGADOR|TITULAR):\s*', '', cand_pl, flags=re.IGNORECASE).strip()
                            if len(cand_pl) >= 3 and not any(k in cand_pl.upper() for k in termos_invalidos):
                                if not re.match(r'^(CPF|CNPJ|CHAVE|BANCO|INSTITUI|AG[EÊ]NCIA|CONTA|DATA|VALOR)', cand_pl_upper):
                                    if cand_pl.upper() != (recebedor_pix or "").upper():
                                        pagador_pix = cand_pl
                                        break
                    if pagador_pix:
                        break

        # Documentos do Recebedor e Pagador (CPF/CNPJ)
        docs_encontrados = re.findall(r'(\*{2,3}\.?\d{3}\.?\d{3}\-?\*{2}|\d{3}\.?\*{3}\.?\*{3}\-?\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2})', texto_bruto)
        if docs_encontrados:
            doc_recebedor = docs_encontrados[0]
            if len(docs_encontrados) > 1:
                doc_pagador = docs_encontrados[1]

        # Tenta localizar documento explicitamente vinculado ao pagador
        m_doc_pag = re.search(r'(?:PAGADOR|ORIGEM|DEBITADO\s+DE|QUEM\s+PAGOU|PAGO\s+POR|DADOS\s+DO\s+PAGADOR|DE:)[\s\S]{1,120}?(?:CPF|CNPJ)?[\s:]*(\*{2,3}\.?\d{3}\.?\d{3}\-?\*{2}|\d{3}\.?\*{3}\.?\*{3}\-?\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2})', texto_bruto, re.IGNORECASE)
        if m_doc_pag:
            doc_pagador = m_doc_pag.group(1).strip()

    # 1b. Atribuição do Estabelecimento / Recebedor Final
    if recebedor_pix:
        estabelecimento = recebedor_pix
        if doc_recebedor and doc_recebedor not in estabelecimento:
            estabelecimento = f"{estabelecimento} ({doc_recebedor})"
    else:
        estabelecimento = linhas[0] if linhas else "Desconhecido"
        # CNPJ para notas fiscais tradicionais
        cnpj_match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_bruto)
        cnpj = cnpj_match.group(0) if cnpj_match else ""
        if cnpj and "CNPJ:" not in estabelecimento:
            estabelecimento = f"{estabelecimento} (CNPJ: {cnpj})"
    
    # 2. Data (Procura formato DD/MM/AAAA ou DD/MM/AA)
    data_match = re.search(r'(\d{2}/\d{2}/\d{4})', texto_bruto)
    if data_match:
        data_str = data_match.group(1)
    else:
        data_match_curta = re.search(r'(\d{2}/\d{2}/\d{2})', texto_bruto)
        if data_match_curta:
            d_partes = data_match_curta.group(1).split('/')
            data_str = f"{d_partes[0]}/{d_partes[1]}/20{d_partes[2]}"
        else:
            data_str = datetime.now().strftime("%d/%m/%Y")

    # 2b. Hora da Compra / Emissão
    hora_match = re.search(r'(\d{2}:\d{2}(?::\d{2})?)', texto_bruto)
    hora_str = hora_match.group(1) if hora_match else "Não Informada"
    
    # 3. Valor Total
    valor_match = re.search(r'(?:TOTAL|VALOR A PAGAR|PAGAR|VALOR PAGO|VALOR DA TRANSFER[EÊ]NCIA|VALOR|R\$\s*)[\s:]*(\d+[\.,]\d{2})', texto_bruto, re.IGNORECASE)
    if not valor_match:
        valores = re.findall(r'(\d+[\.,]\d{2})', texto_bruto)
        valor = float(valores[-1].replace(',', '.')) if valores else 0.0
    else:
        try:
            valor = float(valor_match.group(1).replace(',', '.'))
        except ValueError:
            valor = 0.0

    # 3b. Valor de Desconto
    desconto_match = re.search(r'(?:DESCONTO|DESC|ABATIMENTO)[\s:]*R?\$?\s*(\d+[\.,]\d{2})', texto_bruto, re.IGNORECASE)
    desconto_val = float(desconto_match.group(1).replace(',', '.')) if desconto_match else 0.0

    # 3c. Valor de Troco
    troco_match = re.search(r'(?:TROCO)[\s:]*R?\$?\s*(\d+[\.,]\d{2})', texto_bruto, re.IGNORECASE)
    troco_val = float(troco_match.group(1).replace(',', '.')) if troco_match else 0.0

    # 3d. Impostos / Tributos Aproximados
    trib_match = re.search(r'(?:TRIB|TRIBUTOS|IMPOSTO|IBPT)[\s\w]*R?\$?\s*(\d+[\.,]\d{2})', texto_bruto, re.IGNORECASE)
    trib_val = float(trib_match.group(1).replace(',', '.')) if trib_match else 0.0

    # 5. Forma de Pagamento & Bandeira do Cartão
    if is_pix:
        pagamento = "Pix"
    elif "CREDITO" in texto_upper or "CRÉDITO" in texto_upper:
        pagamento = "Cartão de Crédito"
    elif "DEBITO" in texto_upper or "DÉBITO" in texto_upper:
        pagamento = "Cartão de Débito"
    elif "DINHEIRO" in texto_upper:
        pagamento = "Dinheiro"
    else:
        pagamento = "Não Informado"

    bandeira_str = "Não Informada"
    if "VISA" in texto_upper:
        bandeira_str = "Visa"
    elif "MASTERCARD" in texto_upper or "MASTER" in texto_upper:
        bandeira_str = "Mastercard"
    elif "ELO" in texto_upper:
        bandeira_str = "Elo"
    elif "AMEX" in texto_upper or "AMERICAN" in texto_upper:
        bandeira_str = "Amex"
    elif "HIPERCARD" in texto_upper or "HIPER" in texto_upper:
        bandeira_str = "Hipercard"

    # 6. Tipo de Documento
    if is_pix:
        tipo_doc = "Comprovante Pix"
    elif is_pdf:
        tipo_doc = "Nota Fiscal (PDF)"
    elif "NFC-E" in texto_upper or "NOTA FISCAL" in texto_upper or "DANFE" in texto_upper:
        tipo_doc = "Nota Fiscal Eletrônica (DANFE)"
    elif "RECIBO" in texto_upper:
        tipo_doc = "Recibo"
    else:
        tipo_doc = "Cupom Fiscal"

    return {
        "status_leitura": "sucesso",
        "mensagem_erro": None,
        "data": data_str,
        "hora": hora_str,
        "estabelecimento": estabelecimento,
        "tipo_documento": tipo_doc,
        "categoria": "Geral",
        "pagamento": pagamento,
        "bandeira": bandeira_str,
        "valor": valor,
        "desconto": desconto_val,
        "troco": troco_val,
        "tributos": trib_val,
        "pagador": pagador_pix if pagador_pix else None,
        "doc_pagador": doc_pagador if doc_pagador else None,
        "recebedor": recebedor_pix if recebedor_pix else None,
        "doc_recebedor": doc_recebedor if doc_recebedor else None,
        "itens": []
    }

def verificar_duplicidade(dados_extraidos: dict, limite_registros: int = 20) -> bool:
    """
    Verifica se os dados extraídos já existem nos registros recentes ou na planilha do Google Sheets.
    Retorna True se for duplicado e False se for um lançamento novo.
    """
    data_nova = str(dados_extraidos.get("data", "")).strip()
    estab_novo = str(dados_extraidos.get("estabelecimento", "")).strip().lower()
    valor_novo = float(dados_extraidos.get("valor", 0.0))

    # 1. Checagem em memória no histórico recente de logs (evita concorrência e economiza cota da API)
    for log in processing_logs[:limite_registros]:
        st = log.get("status_sheets", "")
        if st in ("Enviado com Sucesso", "Gravando na Planilha...", "Processando"):
            e_antigo = str(log.get("estabelecimento", "")).strip().lower()
            v_antigo = float(log.get("valor", 0.0))
            d_antiga = str(log.get("data_comprovante", "")).strip()
            if not d_antiga and log.get("detalhes"):
                try:
                    det_json = json.loads(log["detalhes"].split(" | ")[0])
                    d_antiga = str(det_json.get("data", "")).strip()
                except Exception:
                    pass

            if (data_nova == d_antiga and 
                estab_novo == e_antigo and 
                abs(valor_novo - v_antigo) < 0.01):
                logger.info(f"Duplicidade detectada no cache local em memória: {estab_novo} | R$ {valor_novo:.2f} | {data_nova}")
                return True

    # 2. Checagem opcional na planilha do Google Sheets com proteção contra cota 429
    if SPREADSHEET_ID and GOOGLE_CREDENTIALS_JSON:
        try:
            gc = get_sheets_client()
            sh = gc.open_by_key(SPREADSHEET_ID)
            nome_aba = obter_nome_aba(data_nova)
            try:
                worksheet = sh.worksheet(nome_aba)
            except Exception:
                worksheet = sh.get_worksheet(0)
            
            todas_linhas = worksheet.get_all_values()
            if len(todas_linhas) <= 1:
                return False
            
            ultimas_linhas = todas_linhas[-limite_registros:]
            for linha in ultimas_linhas:
                if len(linha) >= 6:
                    data_existente = str(linha[0]).strip()
                    estab_existente = str(linha[1]).strip().lower()
                    try:
                        valor_existente = float(
                            str(linha[5])
                            .replace("R$", "")
                            .replace(" ", "")
                            .replace(",", ".")
                            .strip()
                        )
                    except ValueError:
                        valor_existente = 0.0
                    
                    if (data_nova == data_existente and 
                        estab_novo == estab_existente and 
                        abs(valor_novo - valor_existente) < 0.01):
                        logger.info(f"Duplicidade detectada no Google Sheets ({nome_aba}): {estab_novo} | R$ {valor_novo:.2f} | {data_nova}")
                        return True
        except APIError as e_api:
            logger.warning(f"Cota de leitura do Google Sheets (429) atingida na duplicidade. Ignorando consulta remota: {e_api}")
        except Exception as e_dup:
            logger.warning(f"Aviso ao consultar duplicidade no Google Sheets: {e_dup}")
            
    return False

# Mapeamento dos meses para nomes em português
MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Marco", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

def obter_nome_aba(data_str: str) -> str:
    """
    Converte uma string de data (DD/MM/AAAA) no nome da aba (ex: Novembro_2026).
    Se a data for inválida ou não informada, utiliza o mês/ano atual.
    """
    try:
        data_obj = datetime.strptime(str(data_str).strip(), "%d/%m/%Y")
        nome_mes = MESES_PT[data_obj.month]
        return f"{nome_mes}_{data_obj.year}"
    except Exception:
        agora = datetime.now()
        nome_mes = MESES_PT[agora.month]
        return f"{nome_mes}_{agora.year}"

def append_to_sheet_aba_mensal(data: dict, file_id: str, url_direta: str = "", observacao: str = "", responsavel: str = "Não Informado") -> tuple[int, str]:
    """
    Grava o lançamento na aba mensal correspondente (ex: Novembro_2026),
    incluindo mecanismo de retry com backoff exponencial contra erros 429 de cota do Google.
    """
    if not SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID não configurada nas variáveis de ambiente.")
    
    gc = get_sheets_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    
    # 1. Determina o nome da aba com base na data do gasto
    nome_aba = obter_nome_aba(data.get("data", ""))
    
    # 2. Tenta selecionar a aba ou cria uma nova se não existir
    try:
        worksheet = sh.worksheet(nome_aba)
    except Exception:
        try:
            worksheet = sh.add_worksheet(title=nome_aba, rows=100, cols=15)
            cabecalho = [
                "Data", "Hora", "Estabelecimento", "Tipo Documento", "Categoria", 
                "Forma Pagamento", "Bandeira", "Valor (R$)", "Desconto (R$)", "Troco (R$)", 
                "Tributos (R$)", "Responsável", "Comprovante", "Observação"
            ]
            worksheet.append_row(cabecalho, value_input_option='USER_ENTERED')
            logger.info(f"Nova aba criada com sucesso: {nome_aba}")
        except Exception as e_add:
            logger.warning(f"Aviso ao criar aba {nome_aba}: {e_add}. Usando aba ativa...")
            worksheet = sh.get_worksheet(0)
    
    # 3. Monta o link direto da imagem no Telegram
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    url_direta_imagem = url_direta
    
    if not url_direta_imagem and file_id and bot_token:
        try:
            res_path = requests.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id}, timeout=10).json()
            if res_path.get("ok"):
                file_path = res_path["result"]["file_path"]
                url_direta_imagem = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        except Exception as e:
            logger.warning(f"Erro ao obter URL da imagem: {e}")
            
    if not url_direta_imagem:
        url_direta_imagem = "Não disponível"

    # 4. Cria a fórmula clicável no Google Sheets
    if url_direta_imagem.startswith("http"):
        formula_link = f'=HYPERLINK("{url_direta_imagem}"; "Ver Imagem")'
    else:
        formula_link = "Armazenado no Telegram"

    # 4b. Formata o Responsável e Observação para o Google Sheets
    # Se houver pagador identificado no comprovante Pix, grava-o como Responsável (coluna 12)
    resp_planilha = str(responsavel or "").strip()
    pagador_ext = data.get("pagador")
    doc_pag_ext = data.get("doc_pagador")
    if pagador_ext:
        doc_s = f" ({doc_pag_ext})" if doc_pag_ext else ""
        pagador_fmt = f"{pagador_ext}{doc_s}"
        if not resp_planilha or resp_planilha == "Não Informado":
            resp_planilha = pagador_fmt
        elif pagador_ext.lower() not in resp_planilha.lower():
            resp_planilha = f"{pagador_fmt} [Telegram: {resp_planilha}]"
    elif not resp_planilha:
        resp_planilha = "Não Informado"

    obs_planilha = str(observacao or "").strip()
    if pagador_ext and "pagador" not in obs_planilha.lower():
        obs_planilha = f"Pagador Pix: {pagador_ext} | {obs_planilha}".strip(" |")

    row = [
        str(data.get("data", "Não Informado")),
        str(data.get("hora", "Não Informada")),
        str(data.get("estabelecimento", "Não Informado")),
        str(data.get("tipo_documento", "Não Informado")),
        str(data.get("categoria", "Não Informado")),
        str(data.get("pagamento", "Não Informado")),
        str(data.get("bandeira", "Não Informada")),
        float(data.get("valor", 0.0)),
        float(data.get("desconto", 0.0)),
        float(data.get("troco", 0.0)),
        float(data.get("tributos", 0.0)),
        resp_planilha,
        formula_link,
        obs_planilha
    ]

    # Tentativas com backoff automático contra erro 429
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            worksheet.append_row(row, value_input_option='USER_ENTERED')
            break
        except APIError as e_api:
            if "429" in str(e_api) or "Quota exceeded" in str(e_api):
                logger.warning(f"Cota do Google Sheets atingida (429). Tentativa {attempt}/{max_retries}. Aguardando {attempt * 2}s...")
                if attempt < max_retries:
                    time.sleep(attempt * 2)
                else:
                    raise e_api
            else:
                raise e_api
        except Exception as e_user_entered:
            logger.warning(f"Tentativa alternativa de inserção no Sheets ({e_user_entered})...")
            if url_direta_imagem.startswith("http"):
                row[7] = f'=HYPERLINK("{url_direta_imagem}", "Ver Imagem")'
            worksheet.append_row(row)
            break

    # Retorna contador estimado em memória sem fazer nova chamada de leitura de todas as linhas da planilha
    total_linhas = len(processing_logs) + 1
    return total_linhas, nome_aba

# Aliases para compatibilidade total
append_to_sheet = append_to_sheet_aba_mensal
append_to_sheet_link_direto = append_to_sheet_aba_mensal
append_to_sheet_telegram = append_to_sheet_aba_mensal
append_to_sheet_com_link_telegram = append_to_sheet_aba_mensal

def gerar_relatorio_mensal(nome_aba: str = None) -> str:
    """
    Lê a aba especificada (ou a aba do mês atual) no Google Sheets,
    calcula o total geral e o acumulado por categoria.
    """
    if not SPREADSHEET_ID or not GOOGLE_CREDENTIALS_JSON:
        return "⚠️ Planilha do Google Sheets não configurada nas variáveis de ambiente."

    try:
        gc = get_sheets_client()
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e_client:
        logger.error(f"Erro ao conectar com Google Sheets para relatório: {e_client}")
        return f"⚠️ Erro ao acessar o Google Sheets: {e_client}"
    
    # Se nenhuma aba for especificada, determina o nome da aba do mês atual
    if not nome_aba:
        agora = datetime.now()
        nome_aba = f"{MESES_PT[agora.month]}_{agora.year}"
    else:
        # Normaliza o nome caso o usuário envie sem ano ou com minúsculas (ex: "novembro" ou "novembro_2026")
        partes = nome_aba.strip().split("_")
        if len(partes) == 1 and not partes[0].isdigit():
            agora = datetime.now()
            nome_aba = f"{partes[0].capitalize()}_{agora.year}"
        elif len(partes) == 2:
            nome_aba = f"{partes[0].capitalize()}_{partes[1]}"
    
    try:
        worksheet = sh.worksheet(nome_aba)
    except Exception:
        try:
            abas_existentes = [ws.title for ws in sh.worksheets()]
            abas_msg = ", ".join([f"`{t}`" for t in abas_existentes if "_" in t]) or "nenhuma aba mensal encontrada"
            return (
                f"⚠️ Nenhuma aba encontrada para o período *{nome_aba}*.\n\n"
                f"📂 *Abas disponíveis na planilha:* {abas_msg}\n\n"
                "💡 *Dica:* use `/resumo Nome_Ano` (ex: `/resumo Novembro_2026`)."
            )
        except Exception:
            return f"⚠️ Nenhuma aba encontrada para o período *{nome_aba}*."

    # Obtém todas as linhas gravadas na aba
    try:
        todas_linhas = worksheet.get_all_values()
    except Exception as e_read:
        return f"⚠️ Erro ao ler dados da aba *{nome_aba}*: {e_read}"
    
    # Se houver apenas o cabeçalho ou estiver vazia
    if len(todas_linhas) <= 1:
        return f"📊 *Relatório Mensal — {nome_aba}*\n\nAinda não há gastos registrados nesta aba."

    total_geral = 0.0
    totais_por_categoria: Dict[str, float] = {}
    total_itens = 0

    # Itera sobre os registros (pulando a linha de cabeçalho)
    for linha in todas_linhas[1:]:
        if len(linha) >= 6:
            categoria = linha[3].strip() if linha[3].strip() else "Outros"
            try:
                val_str = (
                    str(linha[5])
                    .replace("R$", "")
                    .replace(" ", "")
                    .replace(",", ".")
                    .strip()
                )
                valor = float(val_str)
            except ValueError:
                valor = 0.0

            total_geral += valor
            totais_por_categoria[categoria] = totais_por_categoria.get(categoria, 0.0) + valor
            total_itens += 1

    # Formata a mensagem final em Markdown
    relatorio = f"📊 *Relatório de Gastos — {nome_aba}*\n\n"
    relatorio += f"📝 *Total de Comprovantes:* {total_itens}\n"
    relatorio += f"💰 *Total Geral:* R$ {total_geral:.2f}\n\n"
    relatorio += "📌 *Gastos por Categoria:*\n"
    
    # Ordena as categorias por maior valor gasto
    categorias_ordenadas = sorted(totais_por_categoria.items(), key=lambda x: x[1], reverse=True)
    
    for cat, val in categorias_ordenadas:
        percentual = (val / total_geral * 100) if total_geral > 0 else 0
        relatorio += f"• *{cat}:* R$ {val:.2f} _({percentual:.1f}%)_\n"

    relatorio += f"\n🔗 [Abrir Planilha no Google Sheets](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID})"
    return relatorio

def process_receipt_photo_task(chat_id: int, message_id: int, chat_user: str, file_id: str, lock_key: str, observacao: str = "", responsavel: str = "Não Informado", is_pdf: bool = False):
    """
    Executado em segundo plano (BackgroundTasks).
    Permite responder HTTP 200 ao Telegram em milissegundos e processar
    análise de IA/OCR (fotos ou PDFs) e inserção no Sheets de forma assíncrona.
    """
    t_start = time.time()
    t_download = 0.0
    t_gemini = 0.0
    t_duplicidade = 0.0
    t_sheets_write = 0.0

    timestamp_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log_entry: Dict[str, Any] = {
        "id": f"log-{int(datetime.now().timestamp() * 1000)}",
        "timestamp": timestamp_str,
        "chat_id": str(chat_id),
        "username": str(responsavel or chat_user),
        "status_gemini": "Processando",
        "status_sheets": "Pendente",
        "estabelecimento": "-",
        "tipo_documento": "-",
        "categoria": "-",
        "pagamento": "-",
        "valor": 0.0,
        "observacao": observacao or None,
        "responsavel": responsavel,
        "origem_foto": f"Telegram PDF: {file_id[:10]}..." if is_pdf else f"Telegram ID: {file_id[:10]}...",
        "tempo_total_sec": 0.0,
        "metricas_tempo": None,
        "erro": None,
        "detalhes": ""
    }
    processing_logs.insert(0, log_entry)

    try:
        # 1. Envia aviso inicial amigável ao usuário
        msg_inicial = "🔍 Processando nota fiscal (PDF) com IA..." if is_pdf else "🔍 Processando comprovante fiscal com IA (Hugging Face)..."
        send_telegram_message(chat_id, msg_inicial, message_id)

        # 2. Download da imagem do Telegram e Análise com Hugging Face (com cronometragem)
        try:
            t_dl_start = time.time()
            img_bytes, url_direta_imagem = download_telegram_file(file_id)
            t_download = time.time() - t_dl_start

            t_gemini_start = time.time()
            extracted_data = analyze_receipt(img_bytes, is_pdf=is_pdf)
            t_gemini = time.time() - t_gemini_start

            # 3. Verificação do status de leitura (se ilegível, notifica e encerra sem gravar)
            if extracted_data.get("status_leitura") == "ilegivel":
                mensagem_usuario = extracted_data.get(
                    "mensagem_erro",
                    "Não consegui ler os dados com clareza pois a imagem está borrada ou muito escura. Poderia enviar uma foto mais nítida, por favor?"
                )
                t_total = time.time() - t_start
                log_entry["tempo_total_sec"] = round(t_total, 2)
                log_entry["metricas_tempo"] = {
                    "download_sec": round(t_download, 2),
                    "gemini_sec": round(t_gemini, 2),
                    "hf_sec": round(t_gemini, 2),
                    "duplicidade_sec": 0.0,
                    "sheets_write_sec": 0.0,
                    "total_sec": round(t_total, 2)
                }
                log_entry["status_gemini"] = "Ilegível"
                log_entry["status_sheets"] = "Não Enviado (Imagem Ilegível)"
                log_entry["erro"] = mensagem_usuario
                log_entry["detalhes"] = json.dumps(extracted_data, ensure_ascii=False)
                send_telegram_message(chat_id, f"⚠️ {mensagem_usuario}", message_id)
                return

            log_entry["status_gemini"] = "Sucesso"
            log_entry["estabelecimento"] = extracted_data.get("estabelecimento", "Não Informado")
            log_entry["tipo_documento"] = extracted_data.get("tipo_documento", "Não Informado")
            log_entry["categoria"] = extracted_data.get("categoria", "Não Informado")
            log_entry["pagamento"] = extracted_data.get("pagamento", "Não Informado")
            log_entry["valor"] = float(extracted_data.get("valor", 0.0))
            log_entry["data_comprovante"] = extracted_data.get("data", "")
            log_entry["itens"] = extracted_data.get("itens", [])
            log_entry["detalhes"] = json.dumps(extracted_data, ensure_ascii=False)

        except Exception as e_hf:
            t_total = time.time() - t_start
            err_str = str(e_hf)
            log_entry["tempo_total_sec"] = round(t_total, 2)
            log_entry["status_gemini"] = "Falha"
            log_entry["status_sheets"] = "Cancelado (Erro Hugging Face)"
            log_entry["erro"] = f"Erro na Hugging Face IA: {err_str}"

            if "503" in err_str or "aquecendo" in err_str.lower():
                friendly_error = (
                    "⏳ *Modelo de IA da Hugging Face Aquecendo*\n\n"
                    "O modelo de visão computacional (Florence-2) está carregando na memória na Hugging Face (Status 503).\n"
                    "Por favor, aguarde 15 a 30 segundos e **envie a foto novamente**."
                )
            else:
                friendly_error = f"⚠️ Não foi possível analisar o comprovante: {err_str}"

            send_telegram_message(chat_id, friendly_error, message_id)
            return

        # 4. Verificação de Duplicidade e Gravação com Thread Lock Exclusivo (com cronometragem)
        with sheets_write_lock:
            t_dup_start = time.time()
            e_duplicado = verificar_duplicidade(extracted_data)
            t_duplicidade = time.time() - t_dup_start

            if e_duplicado:
                t_total = time.time() - t_start
                alerta_duplicado = (
                    "⚠️ *Atenção: Comprovante Duplicado Detectado!*\n\n"
                    f"Já existe um registro recente para *{extracted_data.get('estabelecimento')}* "
                    f"no valor de *R$ {float(extracted_data.get('valor', 0)):.2f}* na data *{extracted_data.get('data')}*.\n\n"
                    "O lançamento foi ignorado para evitar duplicidade na planilha."
                )
                log_entry["tempo_total_sec"] = round(t_total, 2)
                log_entry["metricas_tempo"] = {
                    "download_sec": round(t_download, 2),
                    "gemini_sec": round(t_gemini, 2),
                    "hf_sec": round(t_gemini, 2),
                    "duplicidade_sec": round(t_duplicidade, 2),
                    "sheets_write_sec": 0.0,
                    "total_sec": round(t_total, 2)
                }
                log_entry["status_sheets"] = "Ignorado (Duplicidade)"
                log_entry["erro"] = "Comprovante idêntico já cadastrado recentemente"
                send_telegram_message(chat_id, alerta_duplicado, message_id)
                return

            # Marca o status de gravação antes de iniciar o append
            log_entry["status_sheets"] = "Gravando na Planilha..."

            # 5. Salva na planilha na aba mensal correspondente
            try:
                log_entry["link_telegram"] = url_direta_imagem
                
                # Define o responsável na planilha (priorizando quem emitiu o Pix se identificado)
                pagador_extraido = extracted_data.get("pagador")
                doc_pagador = extracted_data.get("doc_pagador")
                if pagador_extraido:
                    doc_s = f" ({doc_pagador})" if doc_pagador else ""
                    pagador_fmt = f"{pagador_extraido}{doc_s}"
                    if responsavel and responsavel != "Não Informado" and responsavel.lower() not in pagador_fmt.lower():
                        responsavel_planilha = f"{pagador_fmt} [Telegram: {responsavel}]"
                    else:
                        responsavel_planilha = pagador_fmt
                else:
                    responsavel_planilha = responsavel or "Não Informado"

                log_entry["responsavel"] = responsavel_planilha
                log_entry["username"] = responsavel_planilha
                if pagador_extraido:
                    log_entry["pagador"] = pagador_extraido

                t_write_start = time.time()
                total_linhas, nome_aba = append_to_sheet_aba_mensal(
                    extracted_data, 
                    file_id, 
                    url_direta_imagem, 
                    observacao=observacao, 
                    responsavel=responsavel_planilha
                )
                t_sheets_write = time.time() - t_write_start

                t_total = time.time() - t_start
                log_entry["tempo_total_sec"] = round(t_total, 2)
                log_entry["metricas_tempo"] = {
                    "download_sec": round(t_download, 2),
                    "gemini_sec": round(t_gemini, 2),
                    "hf_sec": round(t_gemini, 2),
                    "duplicidade_sec": round(t_duplicidade, 2),
                    "sheets_write_sec": round(t_sheets_write, 2),
                    "total_sec": round(t_total, 2)
                }

                logger.info(
                    f"⏱️ MEDIÇÃO DE PERFORMANCE (Log #{log_entry['id']}):\n"
                    f"  • Download Telegram: {t_download:.2f}s\n"
                    f"  • Análise Hugging Face IA: {t_gemini:.2f}s\n"
                    f"  • Checagem Duplicidade: {t_duplicidade:.2f}s\n"
                    f"  • Gravação no Sheets: {t_sheets_write:.2f}s\n"
                    f"  • Tempo Total: {t_total:.2f}s"
                )

                log_entry["status_sheets"] = "Enviado com Sucesso"
                log_entry["aba_planilha"] = nome_aba
                det_extra = f" | Aba: {nome_aba} | Linha: {total_linhas} | Responsável: {responsavel_planilha} | Tempo Total: {t_total:.2f}s"
                if observacao:
                    det_extra += f" | Obs: {observacao}"
                log_entry["detalhes"] += det_extra
            except Exception as e_sheets:
                t_total = time.time() - t_start
                log_entry["tempo_total_sec"] = round(t_total, 2)
                log_entry["status_sheets"] = "Falha no Envio"
                log_entry["erro"] = f"Erro Google Sheets: {str(e_sheets)}"
                logger.error(f"Erro ao salvar na planilha Google: {e_sheets}")
                send_telegram_message(chat_id, f"⚠️ Dados extraídos, mas falhou ao gravar na Planilha Google: {str(e_sheets)}", message_id)
                return

        # 6. Mensagem de sucesso limpa no grupo do Telegram
        data_hora_str = extracted_data.get('data', 'Não Informado')
        if extracted_data.get('hora') and extracted_data.get('hora') != 'Não Informada':
            data_hora_str += f" às {extracted_data.get('hora')}"

        pagamento_str = extracted_data.get('pagamento', 'Não Informado')
        if extracted_data.get('bandeira') and extracted_data.get('bandeira') != 'Não Informada':
            pagamento_str += f" ({extracted_data.get('bandeira')})"

        detalhes_pix = ""
        is_pix_doc = "PIX" in str(extracted_data.get('tipo_documento', '')).upper() or "PIX" in str(extracted_data.get('pagamento', '')).upper()
        if extracted_data.get("pagador"):
            doc_p = f" ({extracted_data.get('doc_pagador')})" if extracted_data.get('doc_pagador') else ""
            detalhes_pix = f"• *Quem emitiu (Pagador):* {extracted_data.get('pagador')}{doc_p}\n"

        rotulo_dest = "Quem recebeu (Destinatário)" if (is_pix_doc or extracted_data.get("pagador")) else "Estabelecimento"

        success_msg = (
            "✅ *Lançamento Registrado com Sucesso!*\n\n"
            f"{detalhes_pix}"
            f"• *{rotulo_dest}:* {extracted_data.get('estabelecimento')}\n"
            f"• *Responsável (Planilha):* {responsavel_planilha}\n"
            f"• *Data/Hora:* {data_hora_str}\n"
            f"• *Tipo:* {extracted_data.get('tipo_documento')}\n"
            f"• *Categoria:* {extracted_data.get('categoria')}\n"
            f"• *Pagamento:* {pagamento_str}\n"
            f"• *Valor Total:* R$ {float(extracted_data.get('valor', 0)):.2f}"
        )
        if float(extracted_data.get("desconto", 0)) > 0:
            success_msg += f"\n• *Desconto:* R$ {float(extracted_data.get('desconto', 0)):.2f}"
        if float(extracted_data.get("troco", 0)) > 0:
            success_msg += f"\n• *Troco:* R$ {float(extracted_data.get('troco', 0)):.2f}"
        if float(extracted_data.get("tributos", 0)) > 0:
            success_msg += f"\n• *Tributos IBPT:* R$ {float(extracted_data.get('tributos', 0)):.2f}"

        success_msg += f"\n• *Aba Mensal:* `{nome_aba}`"
        if observacao:
            success_msg += f"\n• *Obs:* {observacao}"
        success_msg += f"\n\n⚡ *Processado em {t_total:.1f}s* | 📊 *Gravado no Google Sheets!*"

        send_telegram_message(chat_id, success_msg, message_id)

    except Exception as e_all:
        logger.error(f"Erro no processamento da foto: {e_all}", exc_info=True)
        log_entry["erro"] = str(e_all)
        log_entry["status_sheets"] = "Erro Geral"
    finally:
        in_progress_locks.discard(lock_key)

@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        update = await request.json()
        update_id = update.get("update_id")

        # 1. Deduplicação imediata por update_id (retentativas automáticas do Telegram)
        if update_id is not None:
            if update_id in processed_update_ids:
                logger.info(f"Webhook update_id {update_id} já registrado ou em andamento. Ignorando repetição.")
                return Response(status_code=status.HTTP_200_OK)
            processed_update_ids[update_id] = time.time()
            if len(processed_update_ids) > 1000:
                processed_update_ids.popitem(last=False)

        message = update.get("message") or update.get("channel_post")
        if not message:
            return Response(status_code=status.HTTP_200_OK)

        chat_id = message["chat"]["id"]
        chat_user = message.get("from", {}).get("username") or message.get("from", {}).get("first_name") or f"ID: {chat_id}"
        message_id = message["message_id"]

        # 2. Trata comandos de texto (como /resumo ou /resumo Novembro_2026)
        if "text" in message:
            texto = message["text"].strip()
            
            # Reconhece /resumo ou /resumo@botname
            if texto.startswith("/resumo"):
                partes = texto.split()
                # Permite passar o mês ex: /resumo Outubro_2026
                nome_aba_especifica = partes[1] if len(partes) > 1 else None
                
                # Registra o comando no histórico de auditoria
                cmd_log = {
                    "id": f"log-{int(datetime.now().timestamp() * 1000)}",
                    "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    "chat_id": str(chat_id),
                    "username": str(chat_user),
                    "status_gemini": "Comando",
                    "status_sheets": "Consulta /resumo",
                    "estabelecimento": f"Comando: {texto}",
                    "tipo_documento": "Relatório",
                    "categoria": "Consulta",
                    "pagamento": "-",
                    "valor": 0.0,
                    "aba_planilha": nome_aba_especifica or "Mês Atual",
                    "origem_foto": "Comando /resumo",
                    "erro": None,
                    "detalhes": f"Consulta de resumo financeiro executada por {chat_user}"
                }
                processing_logs.insert(0, cmd_log)

                send_telegram_message(chat_id, "📊 Gerando resumo financeiro da planilha...", message_id)
                relatorio_msg = gerar_relatorio_mensal(nome_aba_especifica)
                send_telegram_message(chat_id, relatorio_msg, message_id)
                return Response(status_code=status.HTTP_200_OK)

        # 3. Trata arquivos anexados (PDFs de notas fiscais) ou fotos de comprovantes
        file_id = None
        is_pdf = False
        legenda_foto = message.get("caption", "").strip()

        if "photo" in message:
            largest_photo = message["photo"][-1]
            file_id = largest_photo["file_id"]
        elif "document" in message:
            doc = message["document"]
            mime_type = doc.get("mime_type", "").lower()
            file_name = doc.get("file_name", "").lower()
            if "pdf" in mime_type or file_name.endswith(".pdf"):
                file_id = doc["file_id"]
                is_pdf = True

        if file_id:
            user_info = message.get("from", {})
            nome_usuario = user_info.get("first_name", "Usuário")
            sobrenome = user_info.get("last_name", "")
            responsavel_completo = f"{nome_usuario} {sobrenome}".strip() or str(chat_user)

            lock_key = f"{chat_id}:{message_id}:{file_id}"

            if lock_key in in_progress_locks:
                logger.info(f"Mensagem {lock_key} já está em andamento. Ignorando chamada concorrente.")
                return Response(status_code=status.HTTP_200_OK)

            in_progress_locks.add(lock_key)

            background_tasks.add_task(
                process_receipt_photo_task,
                chat_id=chat_id,
                message_id=message_id,
                chat_user=str(chat_user),
                file_id=file_id,
                lock_key=lock_key,
                observacao=legenda_foto,
                responsavel=responsavel_completo,
                is_pdf=is_pdf
            )

        return Response(status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Erro ao receber webhook: {str(e)}", exc_info=True)
        return Response(status_code=status.HTTP_200_OK)

@app.get("/api/logs", response_class=JSONResponse)
def get_logs_json():
    if not sheets_history_loaded:
        carregar_historico_planilha()
    return {
        "status": "ok",
        "total_logs": len(processing_logs),
        "spreadsheet_id_configured": bool(SPREADSHEET_ID),
        "credentials_configured": bool(GOOGLE_CREDENTIALS_JSON),
        "hf_configured": bool(HF_API_TOKEN),
        "hf_model_url": HF_MODEL_URL,
        "gemini_configured": bool(HF_API_TOKEN or GEMINI_KEYS),
        "gemini_keys_count": 1 if HF_API_TOKEN else len(GEMINI_KEYS),
        "active_key_index": 0,
        "logs": processing_logs
    }

@app.get("/login", response_class=HTMLResponse)
def login_page_get(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return HTMLResponse(content=render_login_html(), status_code=200)

@app.post("/login")
async def login_page_post(request: Request):
    passcm = os.getenv("PASSCM", "").strip()
    
    raw_body = (await request.body()).decode("utf-8")
    parsed_body = urllib.parse.parse_qs(raw_body)
    password_input = parsed_body.get("password", [""])[0].strip()

    if not passcm or password_input == passcm:
        token = hashlib.sha256(f"auth_session_token:{passcm}".encode()).hexdigest()
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="auth_session",
            value=token,
            max_age=604800,
            httponly=True,
            path="/"
        )
        return response

    return HTMLResponse(
        content=render_login_html(error_msg="⚠️ Senha incorreta. Tente novamente."),
        status_code=status.HTTP_401_UNAUTHORIZED
    )

@app.get("/logout")
def logout_get():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="auth_session", path="/")
    return response

@app.get("/", response_class=HTMLResponse)
def dashboard_logs_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    if not sheets_history_loaded:
        carregar_historico_planilha()
    
    total_recebidos = len(processing_logs)
    sucessos_sheets = sum(1 for log in processing_logs if log.get("status_sheets") == "Enviado com Sucesso")
    total_valor = sum(log.get("valor", 0.0) for log in processing_logs if log.get("status_sheets") == "Enviado com Sucesso")
    media_valor = (total_valor / sucessos_sheets) if sucessos_sheets > 0 else 0.0

    # Status de configurações
    sheets_ok = bool(SPREADSHEET_ID and GOOGLE_CREDENTIALS_JSON)
    gemini_ok = bool(HF_API_TOKEN or GEMINI_KEYS)
    telegram_ok = bool(TELEGRAM_BOT_TOKEN)

    sheet_id_display = "Não configurada"
    if SPREADSHEET_ID:
        sheet_id_display = f"{SPREADSHEET_ID[:6]}...{SPREADSHEET_ID[-6:]}" if len(SPREADSHEET_ID) > 12 else SPREADSHEET_ID

    # Serializa todos os logs para interatividade no cliente (com os itens discriminados)
    raw_logs_json = json.dumps(processing_logs, ensure_ascii=False)

    template = """<!DOCTYPE html>
<html lang="pt-BR" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Painel Executivo de Auditoria Fiscal — Bot Telegram & Google Sheets</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script>
        (function() {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'light') {
                document.documentElement.classList.remove('dark');
            } else {
                document.documentElement.classList.add('dark');
            }
        })();
    </script>
    <style>
        :root {
            --bg-color: #f8fafc;
            --surface-color: #ffffff;
            --surface-hover: #f1f5f9;
            --border-color: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --primary: #10b981;
            --primary-dark: #059669;
            --primary-light: #ecfdf5;
            --danger: #ef4444;
            --danger-light: #fef2f2;
            --info: #0284c7;
            --info-light: #f0f9ff;
            --telegram-color: #0284c7;
            --telegram-light: #e0f2fe;
            --card-shadow: 0 1px 3px rgba(0,0,0,0.05);
            --input-bg: #ffffff;
            --modal-overlay: rgba(15, 23, 42, 0.6);
        }

        .dark {
            --bg-color: #0b0f19;
            --surface-color: #111827;
            --surface-hover: #1f2937;
            --border-color: #1f2937;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
            --primary: #10b981;
            --primary-dark: #34d399;
            --primary-light: rgba(16, 185, 129, 0.15);
            --danger: #f87171;
            --danger-light: rgba(239, 68, 68, 0.15);
            --info: #38bdf8;
            --info-light: rgba(2, 132, 199, 0.15);
            --telegram-color: #38bdf8;
            --telegram-light: rgba(56, 189, 248, 0.15);
            --card-shadow: 0 4px 12px rgba(0,0,0,0.4);
            --input-bg: #1f2937;
            --modal-overlay: rgba(0, 0, 0, 0.8);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px 16px;
            transition: background-color 0.2s, color 0.2s;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }

        header {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 20px;
            box-shadow: var(--card-shadow);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }
        .brand-zone {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .brand-icon {
            width: 44px;
            height: 44px;
            background: var(--primary-light);
            color: var(--primary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
        }
        .title-group h1 {
            font-size: 20px;
            font-weight: 800;
            color: var(--text-main);
            letter-spacing: -0.3px;
        }
        .title-group p {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .top-actions {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }

        .status-indicators {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .indicator {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 700;
            padding: 6px 10px;
            border-radius: 8px;
            background: var(--surface-hover);
            border: 1px solid var(--border-color);
        }
        .indicator.active {
            background: var(--primary-light);
            color: var(--primary-dark);
        }
        .indicator.active-telegram {
            background: var(--telegram-light);
            color: var(--telegram-color);
        }
        .indicator.inactive {
            background: var(--danger-light);
            color: var(--danger);
        }
        .dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: currentColor;
        }

        .btn-action {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            padding: 8px 14px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s;
            color: var(--text-main);
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
        }
        .btn-action:hover {
            background: var(--surface-hover);
        }
        .btn-primary {
            background: var(--primary);
            color: #ffffff;
            border-color: var(--primary-dark);
        }
        .btn-primary:hover {
            background: var(--primary-dark);
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }
        .kpi-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 18px 20px;
            box-shadow: var(--card-shadow);
        }
        .kpi-card .label {
            font-size: 11px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .kpi-card .value {
            font-size: 24px;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
            margin-top: 6px;
            color: var(--text-main);
        }
        .kpi-card .subtext {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .category-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: var(--card-shadow);
        }
        .category-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }
        .category-header h3 {
            font-size: 14px;
            font-weight: 700;
        }
        .category-progress-bar {
            display: flex;
            height: 12px;
            border-radius: 6px;
            overflow: hidden;
            background: var(--surface-hover);
            margin-bottom: 14px;
        }
        .category-progress-segment {
            height: 100%;
            transition: width 0.4s ease;
        }
        .category-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 12px 20px;
            font-size: 12px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 4px;
            transition: background 0.2s;
        }
        .legend-item:hover {
            background: var(--surface-hover);
        }
        .legend-color {
            width: 100px;
            height: 10px;
            border-radius: 3px;
        }

        .filter-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 20px;
            box-shadow: var(--card-shadow);
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            justify-content: space-between;
        }
        .search-box {
            flex: 1;
            min-width: 240px;
            position: relative;
        }
        .search-box input {
            width: 100%;
            padding: 10px 14px 10px 36px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-main);
            font-size: 13px;
            outline: none;
            transition: border 0.2s;
        }
        .search-box input:focus {
            border-color: var(--primary);
        }
        .search-icon {
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 14px;
        }

        .filter-selects {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .select-field {
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-main);
            font-size: 12px;
            font-weight: 600;
            outline: none;
            cursor: pointer;
        }

        .table-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: var(--card-shadow);
        }
        .table-header-title {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .table-header-title h2 {
            font-size: 15px;
            font-weight: 700;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 13px;
        }
        th {
            background: var(--surface-hover);
            padding: 12px 16px;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }
        th:hover {
            color: var(--text-main);
        }
        td {
            padding: 14px 16px;
            border-bottom: 1px solid var(--border-color);
        }
        tr:hover td {
            background-color: var(--surface-hover);
        }

        .font-mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
        .font-bold { font-weight: 700; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .text-muted { color: var(--text-muted); }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
        }
        .badge-success { background: var(--primary-light); color: var(--primary-dark); border: 1px solid rgba(16,185,129,0.3); }
        .badge-error { background: var(--danger-light); color: var(--danger); border: 1px solid rgba(239,68,68,0.3); }
        .badge-warning { background: rgba(245, 158, 11, 0.15); color: #d97706; border: 1px solid rgba(245, 158, 11, 0.3); }
        .badge-info { background: var(--info-light); color: var(--info); border: 1px solid rgba(2, 132, 199, 0.3); }

        .pill-category {
            background: var(--surface-hover);
            color: var(--text-main);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            border: 1px solid var(--border-color);
        }

        .pagination-bar {
            padding: 14px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid var(--border-color);
            font-size: 12px;
            color: var(--text-muted);
        }

        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: var(--modal-overlay);
            backdrop-filter: blur(4px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s;
            padding: 20px;
        }
        .modal-overlay.active {
            opacity: 1;
            pointer-events: auto;
        }
        .modal-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            width: 100%;
            max-width: 650px;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            padding: 28px;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
        }
        .modal-header h2 { font-size: 18px; font-weight: 800; }
        .modal-close {
            background: var(--surface-hover);
            border: none;
            width: 32px; height: 32px;
            border-radius: 50%;
            cursor: pointer;
            color: var(--text-muted);
            font-size: 18px;
            display: flex; align-items: center; justify-content: center;
        }
        .modal-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }
        .modal-field label {
            font-size: 11px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
        }
        .modal-field p {
            font-size: 14px;
            font-weight: 600;
            margin-top: 4px;
        }

        .items-table-container {
            margin-top: 16px;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
        }
        .items-table-container th { font-size: 10px; background: var(--surface-hover); }
        .items-table-container td { padding: 10px 14px; font-size: 12px; }

        footer {
            margin-top: 24px;
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand-zone">
                <div class="brand-icon">📊</div>
                <div class="title-group">
                    <h1>Auditor Fiscal AI</h1>
                    <p>Painel de Monitoramento & Integração com Google Sheets</p>
                </div>
            </div>

            <div class="top-actions">
                <div class="status-indicators">
                    <div class="indicator %SHEETS_OK_CLASS%">
                        <span class="dot"></span> Sheets %SHEETS_OK_TEXT%
                    </div>
                    <div class="indicator %GEMINI_OK_CLASS%">
                        <span class="dot"></span> Hugging Face IA %GEMINI_OK_TEXT%
                    </div>
                    <div class="indicator %TELEGRAM_OK_CLASS%">
                        <span class="dot"></span> Telegram %TELEGRAM_OK_TEXT%
                    </div>
                </div>

                <button class="btn-action" onclick="toggleTheme()" id="themeToggleBtn">
                    🌙 Tema Escuro
                </button>
                <a href="/logs" class="btn-action">
                    📜 Logs do Sistema
                </a>
                <button class="btn-action" onclick="window.location.reload()">
                    ↻ Atualizar
                </button>
                <a href="/logout" class="btn-action" style="color: var(--danger); border-color: rgba(239,68,68,0.3);">
                    🚪 Sair
                </a>
            </div>
        </header>

        <!-- KPI Cards Grid -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="label">Valor Total Registrado</div>
                <div class="value" style="color: var(--primary);" id="kpiTotalValor">R$ %TOTAL_VALOR%</div>
                <div class="subtext">Soma dos lançamentos válidos</div>
            </div>
            <div class="kpi-card">
                <div class="label">Comprovantes Gravados</div>
                <div class="value" id="kpiSucessos">%SUCESSOS%</div>
                <div class="subtext">Sincronizados na Planilha</div>
            </div>
            <div class="kpi-card">
                <div class="label">Média por Comprovante</div>
                <div class="value" id="kpiMedia">R$ %MEDIA_VALOR%</div>
                <div class="subtext">Ticket médio dos gastos</div>
            </div>
            <div class="kpi-card">
                <div class="label">Planilha Conectada</div>
                <div class="value font-mono" style="font-size: 15px; margin-top: 8px;">%SHEET_ID_DISPLAY%</div>
                <div class="subtext">Abas Mensais Automáticas</div>
            </div>
        </div>

        <!-- Dashboard da Distribuição de Gastos por Categoria -->
        <div class="category-card">
            <div class="category-header">
                <h3>📌 Distribuição dos Gastos por Categoria</h3>
                <span class="text-muted" style="font-size: 12px;" id="catTotalText">Total: R$ %TOTAL_VALOR%</span>
            </div>
            <div class="category-progress-bar" id="categoryProgressBar">
                <!-- Segments rendered dynamically via JavaScript -->
            </div>
            <div class="category-legend" id="categoryLegend">
                <!-- Legend rendered dynamically via JavaScript -->
            </div>
        </div>

        <!-- Filtros e Barra de Ações -->
        <div class="filter-card">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" id="searchInput" placeholder="Buscar por estabelecimento, responsável, observação ou categoria..." oninput="onFilterChange()">
            </div>

            <div class="filter-selects">
                <select id="abaSelect" class="select-field" onchange="onFilterChange()">
                    <option value="">Todas as Abas</option>
                </select>

                <select id="categoriaSelect" class="select-field" onchange="onFilterChange()">
                    <option value="">Todas as Categorias</option>
                </select>

                <select id="sortSelect" class="select-field" onchange="onFilterChange()">
                    <option value="timestamp_desc">Data (Mais recente)</option>
                    <option value="timestamp_asc">Data (Mais antiga)</option>
                    <option value="valor_desc">Valor (Maior -> Menor)</option>
                    <option value="valor_asc">Valor (Menor -> Maior)</option>
                    <option value="estabelecimento_asc">Estabelecimento (A-Z)</option>
                </select>

                <button class="btn-action btn-primary" onclick="exportFilteredCSV()">
                    📥 Exportar CSV
                </button>
            </div>
        </div>

        <!-- Tabela Principal de Registros -->
        <div class="table-card">
            <div class="table-header-title">
                <h2>Histórico de Envios & Comprovantes Fiscais</h2>
                <span class="text-muted" style="font-size: 12px;" id="rowCountInfo">Mostrando 0 registros</span>
            </div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th onclick="setSort('timestamp')">Data/Hora <span id="sort-timestamp">▼</span></th>
                            <th onclick="setSort('estabelecimento')">Estabelecimento <span id="sort-estabelecimento"></span></th>
                            <th onclick="setSort('categoria')">Categoria <span id="sort-categoria"></span></th>
                            <th>Tipo / Pagamento</th>
                            <th class="text-center" onclick="setSort('aba_planilha')">Aba Mensal <span id="sort-aba_planilha"></span></th>
                            <th class="text-right" onclick="setSort('valor')">Valor (R$) <span id="sort-valor"></span></th>
                            <th class="text-center">Comprovante</th>
                            <th class="text-center">Status Planilha</th>
                            <th>Responsável</th>
                            <th class="text-center">Ação</th>
                        </tr>
                    </thead>
                    <tbody id="tableBody">
                        <!-- Table rows populated dynamically -->
                    </tbody>
                </table>
            </div>

            <div class="pagination-bar">
                <div id="pageInfoText">Página 1 de 1</div>
                <div style="display: flex; gap: 6px;">
                    <button class="btn-action" id="btnPrevPage" onclick="changePage(-1)">← Anterior</button>
                    <button class="btn-action" id="btnNextPage" onclick="changePage(1)">Próxima →</button>
                </div>
            </div>
        </div>

        <footer>
            <div>Auditor Fiscal AI · Telegram + Google Sheets (Armazenamento Nativo no Telegram)</div>
            <div>Atualização automática em tempo real</div>
        </footer>
    </div>

    <!-- Modal de Detalhes do Comprovante e Itens -->
    <div class="modal-overlay" id="detailModal" onclick="if(event.target===this) closeModal()">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 id="modalTitle">Detalhes do Comprovante Fiscal</h2>
                    <p class="text-muted" style="font-size: 12px; margin-top: 2px;" id="modalSubtitle">Lançamento processado pela IA Hugging Face (Florence-2)</p>
                </div>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>

            <div class="modal-grid" id="modalMetadataGrid">
                <!-- Metadata rendered dynamically -->
            </div>

            <div style="margin-top: 16px;">
                <h3 style="font-size: 14px; font-weight: 700; margin-bottom: 8px;">🛒 Itens Comprados / Discriminados na Nota</h3>
                <div class="items-table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Descrição do Item</th>
                                <th class="text-center">Qtd</th>
                                <th class="text-right">Valor Total (R$)</th>
                            </tr>
                        </thead>
                        <tbody id="modalItemsTableBody">
                            <!-- Items table rendered dynamically -->
                        </tbody>
                    </table>
                </div>
            </div>

            <div style="margin-top: 24px; display: flex; justify-content: space-between; align-items: center;">
                <div id="modalLinkContainer"></div>
                <button class="btn-action" onclick="closeModal()">Fechar Visualização</button>
            </div>
        </div>
    </div>

    <script>
        const rawLogs = %RAW_LOGS_JSON%;
        
        let filteredLogs = [...rawLogs];
        let currentSortField = 'timestamp';
        let currentSortOrder = 'desc';
        let currentPage = 1;
        const pageSize = 15;

        const CATEGORY_COLORS = {
            'Alimentação': '#10b981',
            'Veículo': '#38bdf8',
            'Saúde': '#f43f5e',
            'Moradia': '#a855f7',
            'Transporte': '#f59e0b',
            'Lazer': '#ec4899',
            'Educação': '#6366f1',
            'Outros': '#64748b'
        };

        function updateThemeButtonText() {
            const isDark = document.documentElement.classList.contains('dark');
            const btn = document.getElementById('themeToggleBtn');
            if (btn) {
                btn.innerHTML = isDark ? '☀️ Tema Claro' : '🌙 Tema Escuro';
            }
        }

        function toggleTheme() {
            const isDark = document.documentElement.classList.contains('dark');
            if (isDark) {
                document.documentElement.classList.remove('dark');
                localStorage.setItem('theme', 'light');
            } else {
                document.documentElement.classList.add('dark');
                localStorage.setItem('theme', 'dark');
            }
            updateThemeButtonText();
        }

        function initSelectOptions() {
            const abas = new Set();
            const categorias = new Set();

            rawLogs.forEach(log => {
                if (log.aba_planilha) abas.add(log.aba_planilha);
                if (log.categoria && log.categoria !== '-') categorias.add(log.categoria);
            });

            const abaSelect = document.getElementById('abaSelect');
            abas.forEach(aba => {
                const opt = document.createElement('option');
                opt.value = aba;
                opt.textContent = `Aba: ${aba}`;
                abaSelect.appendChild(opt);
            });

            const catSelect = document.getElementById('categoriaSelect');
            categorias.forEach(cat => {
                const opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = `Categoria: ${cat}`;
                catSelect.appendChild(opt);
            });
        }

        function onFilterChange() {
            const searchVal = document.getElementById('searchInput').value || '';
            const searchText = searchVal.trim().toLowerCase();
            const selectedAba = document.getElementById('abaSelect').value;
            const selectedCat = document.getElementById('categoriaSelect').value;
            const sortVal = document.getElementById('sortSelect').value;

            if (sortVal) {
                const parts = sortVal.split('_');
                currentSortField = parts[0];
                currentSortOrder = parts[1] || 'desc';
            }

            filteredLogs = rawLogs.filter(log => {
                const matchSearch = !searchText || 
                    (log.estabelecimento || '').toLowerCase().includes(searchText) ||
                    (log.username || '').toLowerCase().includes(searchText) ||
                    (log.categoria || '').toLowerCase().includes(searchText) ||
                    (log.observacao || '').toLowerCase().includes(searchText) ||
                    (log.data_comprovante || '').toLowerCase().includes(searchText);

                const matchAba = !selectedAba || log.aba_planilha === selectedAba;
                const matchCat = !selectedCat || log.categoria === selectedCat;

                return matchSearch && matchAba && matchCat;
            });

            // Ordenação
            filteredLogs.sort((a, b) => {
                let valA = a[currentSortField] || '';
                let valB = b[currentSortField] || '';

                if (currentSortField === 'valor') {
                    valA = parseFloat(valA) || 0;
                    valB = parseFloat(valB) || 0;
                } else if (currentSortField === 'timestamp') {
                    valA = new Date(valA).getTime() || 0;
                    valB = new Date(b.timestamp).getTime() || 0;
                }

                if (valA < valB) return currentSortOrder === 'asc' ? -1 : 1;
                if (valA > valB) return currentSortOrder === 'asc' ? 1 : -1;
                return 0;
            });

            currentPage = 1;
            renderDashboard();
        }

        function setSort(field) {
            if (currentSortField === field) {
                currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                currentSortField = field;
                currentSortOrder = 'desc';
            }
            document.getElementById('sortSelect').value = `${currentSortField}_${currentSortOrder}`;
            onFilterChange();
        }

        function renderDashboard() {
            renderCategoryDistribution();
            renderTable();
            renderKPIs();
        }

        function renderKPIs() {
            const sucessos = filteredLogs.filter(l => l.status_sheets === 'Enviado com Sucesso');
            const totalVal = sucessos.reduce((sum, l) => sum + (parseFloat(l.valor) || 0), 0);
            const media = sucessos.length > 0 ? (totalVal / sucessos.length) : 0;

            document.getElementById('kpiTotalValor').textContent = `R$ ${totalVal.toFixed(2)}`;
            document.getElementById('kpiSucessos').textContent = sucessos.length;
            document.getElementById('kpiMedia').textContent = `R$ ${media.toFixed(2)}`;
        }

        function renderCategoryDistribution() {
            const totaisPorCat = {};
            let totalGeral = 0;

            filteredLogs.forEach(log => {
                if (log.status_sheets === 'Enviado com Sucesso') {
                    const cat = log.categoria && log.categoria !== '-' ? log.categoria : 'Outros';
                    const val = parseFloat(log.valor) || 0;
                    totaisPorCat[cat] = (totaisPorCat[cat] || 0) + val;
                    totalGeral += val;
                }
            });

            document.getElementById('catTotalText').textContent = `Total Filtrado: R$ ${totalGeral.toFixed(2)}`;

            const progressBar = document.getElementById('categoryProgressBar');
            const legend = document.getElementById('categoryLegend');
            progressBar.innerHTML = '';
            legend.innerHTML = '';

            if (totalGeral === 0) {
                progressBar.innerHTML = '<div style="width:100%; height:100%; background:var(--surface-hover);"></div>';
                legend.innerHTML = '<span class="text-muted" style="font-size:12px;">Nenhum gasto gravado no filtro selecionado.</span>';
                return;
            }

            const sortedCats = Object.entries(totaisPorCat).sort((a, b) => b[1] - a[1]);

            sortedCats.forEach(([cat, val]) => {
                const pct = (val / totalGeral) * 100;
                const color = CATEGORY_COLORS[cat] || '#64748b';

                const seg = document.createElement('div');
                seg.className = 'category-progress-segment';
                seg.style.width = `${pct}%`;
                seg.style.backgroundColor = color;
                seg.title = `${cat}: R$ ${val.toFixed(2)} (${pct.toFixed(1)}%)`;
                progressBar.appendChild(seg);

                const legItem = document.createElement('div');
                legItem.className = 'legend-item';
                legItem.onclick = () => {
                    document.getElementById('categoriaSelect').value = cat;
                    onFilterChange();
                };
                legItem.innerHTML = `
                    <div class="legend-color" style="background-color: ${color};"></div>
                    <span style="font-weight:600;">${cat}</span>
                    <span class="text-muted">R$ ${val.toFixed(2)} (${pct.toFixed(1)}%)</span>
                `;
                legend.appendChild(legItem);
            });
        }

        function renderTable() {
            const tbody = document.getElementById('tableBody');
            tbody.innerHTML = '';

            const totalRows = filteredLogs.length;
            document.getElementById('rowCountInfo').textContent = `${totalRows} comprovante(s) no filtro`;

            if (totalRows === 0) {
                tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center" style="padding: 40px; color: var(--text-muted);">
                        <div style="font-size: 28px; margin-bottom: 6px;">🔍</div>
                        <div style="font-weight:700;">Nenhum registro encontrado para estes filtros</div>
                        <div style="font-size:12px; margin-top:4px;">Tente alterar a busca ou selecionar outra aba mensal.</div>
                    </td>
                </tr>
                `;
                document.getElementById('pageInfoText').textContent = 'Página 0 de 0';
                document.getElementById('btnPrevPage').disabled = true;
                document.getElementById('btnNextPage').disabled = true;
                return;
            }

            const maxPages = Math.ceil(totalRows / pageSize);
            if (currentPage > maxPages) currentPage = maxPages;
            if (currentPage < 1) currentPage = 1;

            const startIndex = (currentPage - 1) * pageSize;
            const pageLogs = filteredLogs.slice(startIndex, startIndex + pageSize);

            pageLogs.forEach((log) => {
                const tr = document.createElement('tr');

                const st = log.status_sheets || '';
                let statusBadge = '';
                if (st === 'Enviado com Sucesso') {
                    statusBadge = '<span class="badge badge-success">✓ Gravado</span>';
                } else if (st.includes('Duplicidade') || st.includes('Ignorado')) {
                    statusBadge = '<span class="badge badge-warning">⚠️ Ignorado (Duplicado)</span>';
                } else if (st.includes('Gravando') || st.includes('Processando') || st.includes('Pendente')) {
                    statusBadge = `<span class="badge badge-info">⏳ ${st}</span>`;
                } else {
                    statusBadge = `<span class="badge badge-error">✕ ${st}</span>`;
                }

                const erroHtml = log.erro ? `<div class="error-msg">${log.erro}</div>` : '';

                let origemHtml = '';
                if (log.link_telegram && log.link_telegram.startsWith('http')) {
                    origemHtml = `<a href="${log.link_telegram}" target="_blank" rel="noopener" class="btn-action" style="padding:4px 8px; font-size:11px; color:#0284c7;">🖼️ Ver Imagem</a>`;
                } else {
                    origemHtml = `<span class="text-muted" style="font-size:11px;">💬 Telegram</span>`;
                }

                const abaBadge = `<span class="pill-category">${log.aba_planilha || 'Mensal'}</span>`;
                const obsHtml = log.observacao ? `<div style="font-size:11px; color:var(--text-muted); font-style:italic; margin-top:2px;">💬 ${log.observacao}</div>` : '';

                tr.innerHTML = `
                    <td class="font-mono text-muted" style="font-size:12px;">${log.timestamp || '-'}</td>
                    <td class="font-bold">${log.estabelecimento || '-'}${obsHtml}</td>
                    <td><span class="pill-category">${log.categoria || '-'}</span></td>
                    <td style="font-size:12px;">${log.tipo_documento || '-'} / ${log.pagamento || '-'}</td>
                    <td class="text-center">${abaBadge}</td>
                    <td class="font-mono font-bold text-right" style="color:var(--text-main);">R$ ${(parseFloat(log.valor) || 0).toFixed(2)}</td>
                    <td class="text-center">${origemHtml}</td>
                    <td class="text-center">${statusBadge}${erroHtml}</td>
                    <td class="text-muted font-mono" style="font-size:12px;">${log.username || '-'}</td>
                    <td class="text-center">
                        <button class="btn-action" style="padding:4px 8px; font-size:11px;" onclick="openDetailModal('${log.id}')">
                            🔍 Detalhes
                        </button>
                    </td>
                `;

                tbody.appendChild(tr);
            });

            document.getElementById('pageInfoText').textContent = `Página ${currentPage} de ${maxPages} (${totalRows} total)`;
            document.getElementById('btnPrevPage').disabled = currentPage === 1;
            document.getElementById('btnNextPage').disabled = currentPage === maxPages;
        }

        function changePage(delta) {
            currentPage += delta;
            renderTable();
        }

        function openDetailModal(logId) {
            const log = rawLogs.find(l => l.id === logId);
            if (!log) return;

            document.getElementById('modalTitle').textContent = log.estabelecimento && log.estabelecimento !== '-' ? log.estabelecimento : 'Comprovante Fiscal';
            document.getElementById('modalSubtitle').textContent = `Lançado em ${log.timestamp || ''} — Aba: ${log.aba_planilha || 'Mensal'}`;

            const metaGrid = document.getElementById('modalMetadataGrid');
            metaGrid.innerHTML = `
                <div class="modal-field">
                    <label>Valor Total</label>
                    <p class="font-mono font-bold" style="font-size:20px; color:var(--primary);">R$ ${(parseFloat(log.valor) || 0).toFixed(2)}</p>
                </div>
                <div class="modal-field">
                    <label>Tipo Documento</label>
                    <p>${log.tipo_documento || '-'}</p>
                </div>
                <div class="modal-field">
                    <label>Categoria</label>
                    <p>${log.categoria || '-'}</p>
                </div>
                <div class="modal-field">
                    <label>Forma Pagamento</label>
                    <p>${log.pagamento || '-'}</p>
                </div>
                <div class="modal-field">
                    <label>Data Comprovante</label>
                    <p class="font-mono">${log.data_comprovante || log.timestamp || '-'}</p>
                </div>
                <div class="modal-field">
                    <label>Responsável</label>
                    <p>${log.username || log.responsavel || '-'}</p>
                </div>
            `;

            if (log.observacao) {
                metaGrid.innerHTML += `
                <div class="modal-field" style="grid-column: 1 / -1;">
                    <label>Legenda / Observação Telegram</label>
                    <p style="font-style:italic; font-weight:normal; color:var(--text-muted);">💬 "${log.observacao}"</p>
                </div>
                `;
            }

            const tbody = document.getElementById('modalItemsTableBody');
            tbody.innerHTML = '';

            let itens = log.itens || [];
            if (!itens.length && log.detalhes) {
                try {
                    const parsedDet = JSON.parse(log.detalhes.split(' | ')[0]);
                    if (parsedDet.itens) itens = parsedDet.itens;
                } catch (e) {}
            }

            if (itens && itens.length > 0) {
                itens.forEach((item, idx) => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td class="font-mono text-muted">${idx + 1}</td>
                        <td class="font-bold">${item.descricao || item.name || 'Item'}</td>
                        <td class="text-center font-mono">${item.quantidade || 1}</td>
                        <td class="text-right font-mono font-bold">R$ ${(parseFloat(item.valor_total_item || item.valor_total || 0)).toFixed(2)}</td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="4" class="text-center text-muted" style="padding:20px;">
                            Nenhum item individual discriminado na nota.
                        </td>
                    </tr>
                `;
            }

            const linkContainer = document.getElementById('modalLinkContainer');
            if (log.link_telegram && log.link_telegram.startsWith('http')) {
                linkContainer.innerHTML = `<a href="${log.link_telegram}" target="_blank" rel="noopener" class="btn-action btn-primary">🖼️ Ver Foto Completa no Telegram</a>`;
            } else {
                linkContainer.innerHTML = `<span class="text-muted" style="font-size:12px;">Foto armazenada no chat do Telegram</span>`;
            }

            document.getElementById('detailModal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('detailModal').classList.remove('active');
        }

        function exportFilteredCSV() {
            let csv = '\\uFEFFData/Hora;Estabelecimento;Categoria;Tipo Documento;Forma Pagamento;Valor (R$);Aba Mensal;Responsável;Observações\\n';

            filteredLogs.forEach(log => {
                const row = [
                    `"${(log.timestamp || '').replace(/"/g, '""')}"`,
                    `"${(log.estabelecimento || '').replace(/"/g, '""')}"`,
                    `"${(log.categoria || '').replace(/"/g, '""')}"`,
                    `"${(log.tipo_documento || '').replace(/"/g, '""')}"`,
                    `"${(log.pagamento || '').replace(/"/g, '""')}"`,
                    (parseFloat(log.valor) || 0).toFixed(2).replace('.', ','),
                    `"${(log.aba_planilha || '').replace(/"/g, '""')}"`,
                    `"${(log.username || '').replace(/"/g, '""')}"`,
                    `"${(log.observacao || '').replace(/"/g, '""')}"`
                ];
                csv += row.join(';') + '\\n';
            });

            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `relatorio_auditoria_${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });

        window.onload = function() {
            updateThemeButtonText();
            initSelectOptions();
            onFilterChange();
        };
    </script>
</body>
</html>
"""
    html_content = (
        template
        .replace("%SHEETS_OK_CLASS%", 'active' if sheets_ok else 'inactive')
        .replace("%SHEETS_OK_TEXT%", 'Conectado' if sheets_ok else 'Pendente')
        .replace("%GEMINI_OK_CLASS%", 'active' if gemini_ok else 'inactive')
        .replace("%GEMINI_OK_TEXT%", 'Ativo' if gemini_ok else 'Sem Token')
        .replace("%TELEGRAM_OK_CLASS%", 'active-telegram' if telegram_ok else 'inactive')
        .replace("%TELEGRAM_OK_TEXT%", 'Pronto' if telegram_ok else 'Sem Token')
        .replace("%TOTAL_VALOR%", f"{total_valor:.2f}")
        .replace("%SUCESSOS%", str(sucessos_sheets))
        .replace("%MEDIA_VALOR%", f"{media_valor:.2f}")
        .replace("%SHEET_ID_DISPLAY%", sheet_id_display)
        .replace("%RAW_LOGS_JSON%", raw_logs_json)
    )
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/logs", response_class=HTMLResponse)
def system_logs_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not sheets_history_loaded:
        carregar_historico_planilha()

    total_logs = len(processing_logs)
    sucessos_sheets = sum(1 for log in processing_logs if log.get("status_sheets") == "Enviado com Sucesso")
    falhas_count = sum(1 for log in processing_logs if log.get("erro") or "Falha" in str(log.get("status_sheets")) or "Falha" in str(log.get("status_gemini")))

    sheets_ok = bool(SPREADSHEET_ID and GOOGLE_CREDENTIALS_JSON)
    gemini_ok = bool(HF_API_TOKEN or GEMINI_KEYS)
    telegram_ok = bool(TELEGRAM_BOT_TOKEN)

    active_key_idx = 1 if HF_API_TOKEN else (current_key_index % len(GEMINI_KEYS) + 1 if GEMINI_KEYS else 0)
    hf_keys_count = 1 if HF_API_TOKEN else len(GEMINI_KEYS)
    raw_logs_json = json.dumps(processing_logs, ensure_ascii=False)

    template = """<!DOCTYPE html>
<html lang="pt-BR" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Central de Logs do Sistema — Auditor Fiscal AI</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script>
        (function() {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'light') {
                document.documentElement.classList.remove('dark');
            } else {
                document.documentElement.classList.add('dark');
            }
        })();
    </script>
    <style>
        :root {
            --bg-color: #f8fafc;
            --surface-color: #ffffff;
            --surface-hover: #f1f5f9;
            --border-color: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --primary: #10b981;
            --primary-dark: #059669;
            --primary-light: #ecfdf5;
            --danger: #ef4444;
            --danger-light: #fef2f2;
            --info: #0284c7;
            --info-light: #f0f9ff;
            --telegram-color: #0284c7;
            --telegram-light: #e0f2fe;
            --card-shadow: 0 1px 3px rgba(0,0,0,0.05);
            --input-bg: #ffffff;
            --modal-overlay: rgba(15, 23, 42, 0.6);
        }

        .dark {
            --bg-color: #0b0f19;
            --surface-color: #111827;
            --surface-hover: #1f2937;
            --border-color: #1f2937;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
            --primary: #10b981;
            --primary-dark: #34d399;
            --primary-light: rgba(16, 185, 129, 0.15);
            --danger: #f87171;
            --danger-light: rgba(239, 68, 68, 0.15);
            --info: #38bdf8;
            --info-light: rgba(2, 132, 199, 0.15);
            --telegram-color: #38bdf8;
            --telegram-light: rgba(56, 189, 248, 0.15);
            --card-shadow: 0 4px 12px rgba(0,0,0,0.4);
            --input-bg: #1f2937;
            --modal-overlay: rgba(0, 0, 0, 0.8);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px 16px;
            transition: background-color 0.2s, color 0.2s;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }

        header {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 20px;
            box-shadow: var(--card-shadow);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }
        .brand-zone {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .brand-icon {
            width: 44px;
            height: 44px;
            background: var(--info-light);
            color: var(--info);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
        }
        .title-group h1 {
            font-size: 20px;
            font-weight: 800;
            color: var(--text-main);
            letter-spacing: -0.3px;
        }
        .title-group p {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .top-actions {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }

        .status-indicators {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .indicator {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 700;
            padding: 6px 10px;
            border-radius: 8px;
            background: var(--surface-hover);
            border: 1px solid var(--border-color);
        }
        .indicator.active { background: var(--primary-light); color: var(--primary-dark); }
        .indicator.active-telegram { background: var(--telegram-light); color: var(--telegram-color); }
        .indicator.inactive { background: var(--danger-light); color: var(--danger); }
        .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

        .btn-action {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            padding: 8px 14px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s;
            color: var(--text-main);
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
        }
        .btn-action:hover { background: var(--surface-hover); }
        .btn-primary { background: var(--primary); color: #ffffff; border-color: var(--primary-dark); }
        .btn-primary:hover { background: var(--primary-dark); }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }
        .kpi-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 18px 20px;
            box-shadow: var(--card-shadow);
        }
        .kpi-card .label {
            font-size: 11px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .kpi-card .value {
            font-size: 24px;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
            margin-top: 6px;
            color: var(--text-main);
        }
        .kpi-card .subtext { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

        .filter-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 20px;
            box-shadow: var(--card-shadow);
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            justify-content: space-between;
        }
        .search-box { flex: 1; min-width: 240px; position: relative; }
        .search-box input {
            width: 100%;
            padding: 10px 14px 10px 36px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-main);
            font-size: 13px;
            outline: none;
            transition: border 0.2s;
        }
        .search-box input:focus { border-color: var(--info); }
        .search-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-muted); font-size: 14px; }

        .filter-selects { display: flex; gap: 10px; flex-wrap: wrap; }
        .select-field {
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-main);
            font-size: 12px;
            font-weight: 600;
            outline: none;
            cursor: pointer;
        }

        .table-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: var(--card-shadow);
        }
        .table-header-title {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .table-header-title h2 { font-size: 15px; font-weight: 700; }

        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
        th {
            background: var(--surface-hover);
            padding: 12px 16px;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
        }
        td { padding: 14px 16px; border-bottom: 1px solid var(--border-color); vertical-align: top; }
        tr:hover td { background-color: var(--surface-hover); }

        .font-mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
        .font-bold { font-weight: 700; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .text-muted { color: var(--text-muted); }

        .badge { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; }
        .badge-success { background: var(--primary-light); color: var(--primary-dark); border: 1px solid rgba(16,185,129,0.3); }
        .badge-error { background: var(--danger-light); color: var(--danger); border: 1px solid rgba(239,68,68,0.3); }
        .badge-warning { background: rgba(245, 158, 11, 0.15); color: #d97706; border: 1px solid rgba(245, 158, 11, 0.3); }
        .badge-info { background: var(--info-light); color: var(--info); border: 1px solid rgba(2, 132, 199, 0.3); }

        .pagination-bar {
            padding: 14px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid var(--border-color);
            font-size: 12px;
            color: var(--text-muted);
        }

        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: var(--modal-overlay);
            backdrop-filter: blur(4px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s;
            padding: 20px;
        }
        .modal-overlay.active { opacity: 1; pointer-events: auto; }
        .modal-card {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            width: 100%;
            max-width: 750px;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            padding: 28px;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
        }
        .modal-header h2 { font-size: 18px; font-weight: 800; }
        .modal-close {
            background: var(--surface-hover);
            border: none;
            width: 32px; height: 32px;
            border-radius: 50%;
            cursor: pointer;
            color: var(--text-muted);
            font-size: 18px;
            display: flex; align-items: center; justify-content: center;
        }
        .json-pre {
            background: #0f172a;
            color: #38bdf8;
            padding: 16px;
            border-radius: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 450px;
            border: 1px solid var(--border-color);
        }

        footer {
            margin-top: 24px;
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand-zone">
                <div class="brand-icon">📜</div>
                <div class="title-group">
                    <h1>Central de Logs & Telemetria do Sistema</h1>
                    <p>Auditoria de Execuções, Erros, Chamadas Hugging Face e Webhooks</p>
                </div>
            </div>

            <div class="top-actions">
                <div class="status-indicators">
                    <div class="indicator %SHEETS_OK_CLASS%">
                        <span class="dot"></span> Sheets %SHEETS_OK_TEXT%
                    </div>
                    <div class="indicator %GEMINI_OK_CLASS%">
                        <span class="dot"></span> Hugging Face IA %GEMINI_OK_TEXT%
                    </div>
                    <div class="indicator %TELEGRAM_OK_CLASS%">
                        <span class="dot"></span> Telegram %TELEGRAM_OK_TEXT%
                    </div>
                </div>

                <a href="/" class="btn-action">
                    ⬅ Voltar ao Painel
                </a>
                <button class="btn-action" onclick="toggleTheme()" id="themeToggleBtn">
                    🌙 Tema Escuro
                </button>
                <button class="btn-action" onclick="window.location.reload()">
                    ↻ Atualizar
                </button>
            </div>
        </header>

        <!-- KPI Cards Grid -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="label">Total de Registros de Logs</div>
                <div class="value" style="color: var(--info);" id="kpiTotalLogs">%TOTAL_LOGS%</div>
                <div class="subtext">Eventos registrados em memória</div>
            </div>
            <div class="kpi-card">
                <div class="label">Sincronizados com Sucesso</div>
                <div class="value" style="color: var(--primary);" id="kpiSucessosLogs">%SUCESSOS_SHEETS%</div>
                <div class="subtext">Gravações na Planilha Google</div>
            </div>
            <div class="kpi-card">
                <div class="label">Alertas e Falhas Detectadas</div>
                <div class="value" style="color: %FALHAS_COLOR%;" id="kpiFalhasLogs">%FALHAS_LOGS%</div>
                <div class="subtext">Imagens ilegíveis ou erros de API</div>
            </div>
            <div class="kpi-card">
                <div class="label">Status API Hugging Face</div>
                <div class="value font-mono" style="font-size: 16px; margin-top: 6px;">%HF_STATUS_TEXT%</div>
                <div class="subtext">Modelo Florence-2 Inference API</div>
            </div>
        </div>

        <!-- Filtros e Barra de Ações -->
        <div class="filter-card">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" id="searchInput" placeholder="Buscar por mensagem, ID de log, usuário, erro ou estabelecimento..." oninput="onFilterChange()">
            </div>

            <div class="filter-selects">
                <select id="statusGeminiSelect" class="select-field" onchange="onFilterChange()">
                    <option value="">Status IA / HF (Todos)</option>
                    <option value="Sucesso">Sucesso</option>
                    <option value="Processando">Processando</option>
                    <option value="Ilegível">Ilegível</option>
                    <option value="Falha">Falha</option>
                    <option value="Comando">Comando</option>
                </select>

                <select id="statusSheetsSelect" class="select-field" onchange="onFilterChange()">
                    <option value="">Status Planilha (Todos)</option>
                    <option value="Enviado com Sucesso">Enviado com Sucesso</option>
                    <option value="Ignorado">Ignorado / Duplicidade</option>
                    <option value="Falha">Falha no Envio</option>
                </select>

                <button class="btn-action btn-primary" onclick="exportJSONLogs()">
                    📥 Exportar JSON
                </button>
            </div>
        </div>

        <!-- Tabela de Logs do Sistema -->
        <div class="table-card">
            <div class="table-header-title">
                <h2>Histórico Detalhado de Telemetria e Logs de Execução</h2>
                <span class="text-muted" style="font-size: 12px;" id="rowCountInfo">Mostrando 0 registro(s)</span>
            </div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Data / Hora</th>
                            <th>ID do Evento</th>
                            <th>Origem / Usuário</th>
                            <th>Status Hugging Face</th>
                            <th>Status Planilha</th>
                            <th>Estabelecimento / Erro</th>
                            <th class="text-center">Ações</th>
                        </tr>
                    </thead>
                    <tbody id="tableBody">
                        <!-- Table rows populated dynamically -->
                    </tbody>
                </table>
            </div>

            <div class="pagination-bar">
                <div id="pageInfoText">Página 1 de 1</div>
                <div style="display: flex; gap: 6px;">
                    <button class="btn-action" id="btnPrevPage" onclick="changePage(-1)">← Anterior</button>
                    <button class="btn-action" id="btnNextPage" onclick="changePage(1)">Próxima →</button>
                </div>
            </div>
        </div>

        <footer>
            <div>Auditor Fiscal AI · Central de Logs do Servidor (Node / FastAPI Pipeline)</div>
            <div>Monitoramento em tempo real</div>
        </footer>
    </div>

    <!-- Modal de JSON Completo do Log -->
    <div class="modal-overlay" id="jsonModal" onclick="if(event.target===this) closeModal()">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 id="modalLogTitle">Detalhes Brutos do Log (JSON)</h2>
                    <p class="text-muted" style="font-size: 12px; margin-top: 2px;" id="modalLogSubtitle">Objeto de telemetria retornado pelo pipeline</p>
                </div>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>

            <div>
                <pre class="json-pre" id="jsonContainer"></pre>
            </div>

            <div style="margin-top: 24px; display: flex; justify-content: flex-end;">
                <button class="btn-action" onclick="closeModal()">Fechar Visualização</button>
            </div>
        </div>
    </div>

    <script>
        const rawLogs = %RAW_LOGS_JSON%;
        let filteredLogs = [...rawLogs];
        let currentPage = 1;
        const pageSize = 15;

        function updateThemeButtonText() {
            const isDark = document.documentElement.classList.contains('dark');
            const btn = document.getElementById('themeToggleBtn');
            if (btn) {
                btn.innerHTML = isDark ? '☀️ Tema Claro' : '🌙 Tema Escuro';
            }
        }

        function toggleTheme() {
            const isDark = document.documentElement.classList.contains('dark');
            if (isDark) {
                document.documentElement.classList.remove('dark');
                localStorage.setItem('theme', 'light');
            } else {
                document.documentElement.classList.add('dark');
                localStorage.setItem('theme', 'dark');
            }
            updateThemeButtonText();
        }

        function onFilterChange() {
            const searchVal = document.getElementById('searchInput').value || '';
            const searchText = searchVal.trim().toLowerCase();
            const geminiStatus = document.getElementById('statusGeminiSelect').value;
            const sheetsStatus = document.getElementById('statusSheetsSelect').value;

            filteredLogs = rawLogs.filter(log => {
                const matchSearch = !searchText ||
                    (log.id || '').toLowerCase().includes(searchText) ||
                    (log.timestamp || '').toLowerCase().includes(searchText) ||
                    (log.username || '').toLowerCase().includes(searchText) ||
                    (log.estabelecimento || '').toLowerCase().includes(searchText) ||
                    (log.erro || '').toLowerCase().includes(searchText) ||
                    (log.detalhes || '').toLowerCase().includes(searchText) ||
                    (log.observacao || '').toLowerCase().includes(searchText);

                const matchGemini = !geminiStatus || (log.status_gemini || '').includes(geminiStatus);
                const matchSheets = !sheetsStatus || (log.status_sheets || '').includes(sheetsStatus);

                return matchSearch && matchGemini && matchSheets;
            });

            currentPage = 1;
            renderTable();
        }

        function renderTable() {
            const tbody = document.getElementById('tableBody');
            tbody.innerHTML = '';

            const totalRows = filteredLogs.length;
            document.getElementById('rowCountInfo').textContent = `${totalRows} registro(s) encontrado(s)`;

            if (totalRows === 0) {
                tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center" style="padding: 40px; color: var(--text-muted);">
                        <div style="font-size: 28px; margin-bottom: 6px;">📜</div>
                        <div style="font-weight:700;">Nenhum log corresponde aos filtros informados</div>
                        <div style="font-size:12px; margin-top:4px;">Tente alterar o termo de busca ou resetar os filtros.</div>
                    </td>
                </tr>
                `;
                document.getElementById('pageInfoText').textContent = 'Página 0 de 0';
                document.getElementById('btnPrevPage').disabled = true;
                document.getElementById('btnNextPage').disabled = true;
                return;
            }

            const maxPages = Math.ceil(totalRows / pageSize);
            if (currentPage > maxPages) currentPage = maxPages;
            if (currentPage < 1) currentPage = 1;

            const startIndex = (currentPage - 1) * pageSize;
            const pageLogs = filteredLogs.slice(startIndex, startIndex + pageSize);

            pageLogs.forEach((log) => {
                const tr = document.createElement('tr');

                let geminiBadge = '';
                const sg = log.status_gemini || '-';
                if (sg === 'Sucesso') {
                    geminiBadge = '<span class="badge badge-success">✓ Sucesso</span>';
                } else if (sg === 'Ilegível') {
                    geminiBadge = '<span class="badge badge-warning">⚠️ Ilegível</span>';
                } else if (sg === 'Processando') {
                    geminiBadge = '<span class="badge badge-info">⏳ Processando</span>';
                } else if (sg === 'Comando') {
                    geminiBadge = '<span class="badge badge-info">💬 Comando</span>';
                } else {
                    geminiBadge = `<span class="badge badge-error">✕ ${sg}</span>`;
                }

                let sheetsBadge = '';
                const ss = log.status_sheets || '-';
                if (ss === 'Enviado com Sucesso') {
                    sheetsBadge = '<span class="badge badge-success">✓ Enviado</span>';
                } else if (ss.includes('Ignorado') || ss.includes('Duplicidade')) {
                    sheetsBadge = '<span class="badge badge-warning">⚠️ Ignorado</span>';
                } else if (ss.includes('Gravando') || ss.includes('Pendente')) {
                    sheetsBadge = `<span class="badge badge-info">⏳ ${ss}</span>`;
                } else {
                    sheetsBadge = `<span class="badge badge-error">✕ ${ss}</span>`;
                }

                const erroOrInfo = log.erro ? 
                    `<div style="color:var(--danger); font-size:11px; font-weight:600; margin-top:2px;">⚠️ ${log.erro}</div>` : 
                    (log.estabelecimento !== '-' ? `<div style="font-weight:600;">${log.estabelecimento}</div>` : '');

                const userStr = log.username || log.responsavel || '-';

                tr.innerHTML = `
                    <td class="font-mono text-muted" style="font-size:12px;">${log.timestamp || '-'}</td>
                    <td class="font-mono" style="font-size:11px; color:var(--text-muted);">${log.id || '-'}</td>
                    <td><div class="font-bold">${userStr}</div><div class="text-muted" style="font-size:11px;">Chat ID: ${log.chat_id || '-'}</div></td>
                    <td>${geminiBadge}</td>
                    <td>${sheetsBadge}</td>
                    <td style="max-width:320px;">${erroOrInfo}<div class="text-muted" style="font-size:11px; max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${log.origem_foto || log.detalhes || ''}</div></td>
                    <td class="text-center">
                        <button class="btn-action" style="padding:4px 8px; font-size:11px;" onclick="openLogModal('${log.id}')">
                            📜 Ver JSON
                        </button>
                    </td>
                `;

                tbody.appendChild(tr);
            });

            document.getElementById('pageInfoText').textContent = `Página ${currentPage} de ${maxPages} (${totalRows} total)`;
            document.getElementById('btnPrevPage').disabled = currentPage === 1;
            document.getElementById('btnNextPage').disabled = currentPage === maxPages;
        }

        function changePage(delta) {
            currentPage += delta;
            renderTable();
        }

        function openLogModal(logId) {
            const log = rawLogs.find(l => l.id === logId);
            if (!log) return;

            document.getElementById('modalLogTitle').textContent = `Log #${log.id}`;
            document.getElementById('modalLogSubtitle').textContent = `Registrado em ${log.timestamp || ''} pelo usuário ${log.username || 'Sistema'}`;

            let timeHtml = '';
            if (log.metricas_tempo) {
                timeHtml = `
                <div style="margin-bottom:16px; padding:12px; background:var(--surface-hover); border-radius:10px; border:1px solid var(--border-color); font-size:12px;">
                    <div style="font-weight:700; margin-bottom:6px; color:var(--info);">⚡ MÉTRICAS DE DESEMPENHO E LATÊNCIA</div>
                    <div style="display:flex; gap:12px; flex-wrap:wrap;">
                        <div><b>📥 Download Telegram:</b> ${log.metricas_tempo.download_sec}s</div>
                        <div><b>🧠 Análise Hugging Face IA:</b> ${(log.metricas_tempo.hf_sec || log.metricas_tempo.gemini_sec || 0)}s</div>
                        <div><b>🔍 Checagem Duplicidade:</b> ${log.metricas_tempo.duplicidade_sec}s</div>
                        <div><b>✍️ Escrita Sheets:</b> ${log.metricas_tempo.sheets_write_sec}s</div>
                        <div><b>⏱️ Tempo Total:</b> <span style="color:var(--primary); font-weight:800;">${log.metricas_tempo.total_sec}s</span></div>
                    </div>
                </div>
                `;
            }

            const jsonContainer = document.getElementById('jsonContainer');
            jsonContainer.innerHTML = timeHtml + '<pre style="margin:0; background:transparent; border:none; padding:0; color:inherit;">' + JSON.stringify(log, null, 2) + '</pre>';
            document.getElementById('jsonModal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('jsonModal').classList.remove('active');
        }

        function exportJSONLogs() {
            const blob = new Blob([JSON.stringify(filteredLogs, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `system_logs_${new Date().toISOString().slice(0, 10)}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });

        window.onload = function() {
            updateThemeButtonText();
            onFilterChange();
        };
    </script>
</body>
</html>
"""

    html_content = (
        template
        .replace("%SHEETS_OK_CLASS%", 'active' if sheets_ok else 'inactive')
        .replace("%SHEETS_OK_TEXT%", 'Conectado' if sheets_ok else 'Pendente')
        .replace("%GEMINI_OK_CLASS%", 'active' if gemini_ok else 'inactive')
        .replace("%GEMINI_OK_TEXT%", 'Ativo' if gemini_ok else 'Sem Token')
        .replace("%TELEGRAM_OK_CLASS%", 'active-telegram' if telegram_ok else 'inactive')
        .replace("%TELEGRAM_OK_TEXT%", 'Pronto' if telegram_ok else 'Sem Token')
        .replace("%TOTAL_LOGS%", str(total_logs))
        .replace("%SUCESSOS_SHEETS%", str(sucessos_sheets))
        .replace("%FALHAS_LOGS%", str(falhas_count))
        .replace("%FALHAS_COLOR%", 'var(--danger)' if falhas_count > 0 else 'var(--text-main)')
        .replace("%HF_STATUS_TEXT%", 'Florence-2 (Ativo)' if gemini_ok else 'HF Token Ausente')
        .replace("%ACTIVE_KEY_INDEX%", str(active_key_idx))
        .replace("%GEMINI_KEYS_COUNT%", str(hf_keys_count))
        .replace("%RAW_LOGS_JSON%", raw_logs_json)
    )
    return HTMLResponse(content=html_content, status_code=200)



