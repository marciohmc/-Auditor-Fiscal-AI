import re
import json
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

import gspread
try:
    from google.oauth2.service_account import Credentials
    AUTH_TYPE = "google.oauth2"
except ImportError:
    from oauth2client.service_account import ServiceAccountCredentials
    AUTH_TYPE = "oauth2client"

from config import GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, logger

sheets_lock = threading.Lock()

CABECALHO_PADRAO = [
    "Date",
    "Establishment",
    "Doc Type",
    "Category",
    "Payment",
    "Value",
    "Responsible",
    "Receipt Link",
    "Obs"
]

def get_sheets_client() -> gspread.Client:
    if not GOOGLE_CREDENTIALS_JSON:
        raise ValueError("GOOGLE_CREDENTIALS_JSON não configurada nas variáveis de ambiente.")
    
    cred_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    if AUTH_TYPE == "google.oauth2":
        credentials = Credentials.from_service_account_info(cred_dict, scopes=scopes)
        return gspread.authorize(credentials)
    else:
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scopes)
        return gspread.authorize(credentials)

def extrair_mes_ano_da_data(data_str: str) -> str:
    if data_str:
        m = re.search(r"\b\d{1,2}[/-](\d{1,2})[/-](20\d{2})\b", data_str)
        if m:
            mes = int(m.group(1))
            ano = int(m.group(2))
            if 1 <= mes <= 12:
                return f"{mes:02d}-{ano}"
    
    return datetime.now().strftime("%m-%Y")

def obter_ou_criar_aba_mensal(sh: gspread.Spreadsheet, nome_aba: str) -> gspread.Worksheet:
    try:
        ws = sh.worksheet(nome_aba)
        return ws
    except gspread.exceptions.WorksheetNotFound:
        logger.info(f"Criando nova aba mensal no Google Sheets: '{nome_aba}'...")
        ws = sh.add_worksheet(title=nome_aba, rows=1000, cols=15)
        ws.append_row(CABECALHO_PADRAO, value_input_option="USER_ENTERED")
        return ws

def verificar_duplicidade(ws: gspread.Worksheet, data_doc: str, valor: float, estabelecimento: str, receipt_link: str = "") -> bool:
    try:
        valores = ws.get_all_values()
        if len(valores) <= 1:
            return False

        estab_limpo = (estabelecimento or "").strip().lower()
        data_limpa = (data_doc or "").strip()

        for row in valores[1:]:
            if len(row) < 6:
                continue

            r_data = row[0].strip()
            r_estab = row[1].strip().lower()
            
            try:
                r_val_str = row[5].replace("R$", "").replace(" ", "").replace(",", ".").strip()
                r_val = float(r_val_str)
            except ValueError:
                r_val = -1.0

            if receipt_link and len(row) >= 8:
                r_link_cell = row[7].strip()
                if receipt_link in r_link_cell:
                    return True

            if r_data == data_limpa and abs(r_val - valor) < 0.01:
                if estab_limpo and (estab_limpo in r_estab or r_estab in estab_limpo):
                    return True

        return False
    except Exception as e:
        logger.warning(f"Aviso ao validar duplicidade no Sheets: {e}")
        return False

def registrar_transacao_planilha(dados: dict, responsavel: str = "Telegram", receipt_link: str = "", obs: str = "") -> dict:
    if not SPREADSHEET_ID or not GOOGLE_CREDENTIALS_JSON:
        return {
            "sucesso": False,
            "motivo": "SPREADSHEET_ID ou GOOGLE_CREDENTIALS_JSON não configurados."
        }

    data_doc = dados.get("data") or datetime.now().strftime("%d/%m/%Y")
    nome_aba = extrair_mes_ano_da_data(data_doc)
    estabelecimento = dados.get("estabelecimento") or dados.get("recebedor") or "Não Informado"
    tipo_doc = dados.get("tipo_documento") or "Outros"
    categoria = dados.get("categoria") or "Outros"
    pagamento = dados.get("pagamento") or "Não Informado"
    valor_float = float(dados.get("valor") or 0.0)

    # Limpeza de caracteres de escape (ex: file\_160.pdf -> file_160.pdf) e formatação do HYPERLINK no padrão Brasil (;)
    if receipt_link:
        clean_link = receipt_link.replace("\\_", "_").replace("\\", "").strip()
        link_formula = f'=HYPERLINK("{clean_link}"; "Ver Comprovante")'
    else:
        clean_link = ""
        link_formula = ""

    linha = [
        data_doc,
        estabelecimento,
        tipo_doc,
        categoria,
        pagamento,
        valor_float,
        responsavel,
        link_formula,
        obs or ""
    ]

    with sheets_lock:
        try:
            gc = get_sheets_client()
            sh = gc.open_by_key(SPREADSHEET_ID)
            ws = obter_ou_criar_aba_mensal(sh, nome_aba)

            if verificar_duplicidade(ws, data_doc, valor_float, estabelecimento, receipt_link):
                logger.warning(f"⚠️ Transação duplicada detectada na aba {nome_aba}: {estabelecimento} - R$ {valor_float}")
                return {
                    "sucesso": False,
                    "duplicado": True,
                    "aba": nome_aba,
                    "mensagem": f"Transação já cadastrada na aba {nome_aba}."
                }

            ws.append_row(linha, value_input_option="USER_ENTERED")
            logger.info(f"✅ Transação inserida com sucesso na aba [{nome_aba}]: {estabelecimento} | R$ {valor_float:.2f}")

            return {
                "sucesso": True,
                "duplicado": False,
                "aba": nome_aba,
                "data": data_doc,
                "estabelecimento": estabelecimento,
                "valor": valor_float
            }

        except Exception as e:
            logger.error(f"Erro ao registrar transação no Google Sheets: {e}")
            return {
                "sucesso": False,
                "erro": str(e)
            }
