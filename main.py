import os
import json
import logging
import time
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Any, List, Set

from fastapi import FastAPI, Request, Response, BackgroundTasks, status
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

def analyze_receipt(image_bytes: bytes) -> Dict[str, Any]:
    system_instruction = (
        "Você é um auditor financeiro e especialista em extração multimodal de dados de documentos fiscais "
        "(notas fiscais, cupons fiscais e recibos). Sua tarefa é analisar a imagem enviada e extrair com precisão "
        "os dados financeiros e a lista de itens comprados, se houver, retornando estritamente um JSON padronizado."
    )
    
    user_prompt = (
        "Analise esta imagem de documento fiscal conforme as regras abaixo:\n\n"
        "1. VALIDAÇÃO DE LEGIBILIDADE (CRÍTICO):\n"
        "- Se a imagem estiver borrada, muito escura, cortada ou se os dados principais (valor total, estabelecimento ou data) "
        "estiverem completamente ilegíveis, defina 'status_leitura': 'ilegivel' e forneça uma justificativa amigável em 'mensagem_erro'.\n"
        "- Se a imagem for legível, defina 'status_leitura': 'sucesso' e 'mensagem_erro': null.\n\n"
        "2. CLASSIFICAÇÃO DO DOCUMENTO:\n"
        "- 'tipo_documento': 'Nota Fiscal', 'Cupom Fiscal' ou 'Recibo'.\n"
        "- 'categoria': 'Alimentação', 'Transporte', 'Saúde', 'Lazer', 'Moradia', 'Veículo', 'Educação' ou 'Outros'.\n"
        "- 'pagamento': 'PIX', 'Cartão de Crédito', 'Cartão de Débito', 'Dinheiro', 'Boleto' ou 'Não Informado'.\n\n"
        "3. EXTRAÇÃO DE ITENS DETALHADOS:\n"
        "- Extraia a lista de itens comprados no array 'itens' com 'descricao', 'quantidade' (float/int) e 'valor_total_item' (float).\n"
        "- Se a nota não discriminar itens individuais, retorne lista vazia [].\n\n"
        "4. FORMATAÇÃO E TIPAGEM:\n"
        "- 'valor': float do valor total líquido (ex: 125.50).\n"
        "- 'data': padrão DD/MM/AAAA.\n\n"
        "Estrutura JSON esperada:\n"
        "{\n"
        '  "status_leitura": "sucesso",\n'
        '  "mensagem_erro": null,\n'
        '  "tipo_documento": "Nota Fiscal / Cupom Fiscal / Recibo",\n'
        '  "data": "DD/MM/AAAA",\n'
        '  "estabelecimento": "Nome do Estabelecimento",\n'
        '  "valor": 0.00,\n'
        '  "categoria": "Alimentação / Transporte / Saúde / Lazer / Moradia / Veículo / Educação / Outros",\n'
        '  "pagamento": "PIX / Cartão de Crédito / Cartão de Débito / Dinheiro / Boleto / Não Informado",\n'
        '  "itens": [\n'
        '    {"descricao": "Item 1", "quantidade": 1, "valor_total_item": 10.00}\n'
        '  ]\n'
        "}\n\n"
        "Retorne estritamente o JSON sem markdown fora do objeto."
    )

    # Modelos ativos recomendados pela Google AI API
    candidate_models = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
    last_err = None

    for model_name in candidate_models:
        for attempt in range(1, 4):
            try:
                logger.info(f"Tentativa {attempt}/3 com modelo {model_name}...")
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
                logger.info(f"Extração bem sucedida com {model_name} na tentativa {attempt}")
                return parsed
            except Exception as err:
                err_str = str(err)
                last_err = err
                logger.warning(f"Tentativa {attempt} com {model_name} falhou: {err_str}")

                if "404" in err_str or "NOTFOUND" in err_str or "no longer available" in err_str:
                    logger.info(f"Modelo {model_name} descontinuado ou não encontrado. Pulando para o próximo...")
                    break
                
                if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str or "429" in err_str:
                    wait_time = attempt * 2.0
                    logger.info(f"Alta demanda temporária da Google detectada. Aguardando {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    break

    raise last_err or RuntimeError("Falha ao analisar imagem com Gemini AI após múltiplas tentativas.")

def verificar_duplicidade(dados_extraidos: dict, limite_registros: int = 20) -> bool:
    """
    Verifica se os dados extraídos já existem nos registros recentes ou na planilha do Google Sheets.
    Retorna True se for duplicado e False se for um lançamento novo.
    """
    data_nova = str(dados_extraidos.get("data", "")).strip()
    estab_novo = str(dados_extraidos.get("estabelecimento", "")).strip().lower()
    valor_novo = float(dados_extraidos.get("valor", 0.0))

    # 1. Checagem em memória no histórico recente de logs (evita concorrência e gravações simultâneas)
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

    # 2. Checagem direta na planilha do Google Sheets (na aba mensal correspondente)
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
                # Ordem das colunas: [Data, Estabelecimento, Documento, Categoria, Pagamento, Valor, Comprovante]
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

def append_to_sheet_aba_mensal(data: dict, file_id: str, url_direta: str = "") -> tuple[int, str]:
    """
    Grava o lançamento na aba mensal correspondente (ex: Novembro_2026).
    Se a aba não existir, cria automaticamente com cabeçalho formatado.
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
            worksheet = sh.add_worksheet(title=nome_aba, rows=100, cols=10)
            cabecalho = ["Data", "Estabelecimento", "Tipo Documento", "Categoria", "Forma Pagamento", "Valor (R$)", "Comprovante"]
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

    row = [
        str(data.get("data", "Não Informado")),
        str(data.get("estabelecimento", "Não Informado")),
        str(data.get("tipo_documento", "Não Informado")),
        str(data.get("categoria", "Não Informado")),
        str(data.get("pagamento", "Não Informado")),
        float(data.get("valor", 0.0)),
        formula_link
    ]

    try:
        worksheet.append_row(row, value_input_option='USER_ENTERED')
    except Exception as e_user_entered:
        logger.warning(f"Tentativa com USER_ENTERED falhou ({e_user_entered}). Tentando formato compatível...")
        if url_direta_imagem.startswith("http"):
            row[6] = f'=HYPERLINK("{url_direta_imagem}", "Ver Imagem")'
            try:
                worksheet.append_row(row, value_input_option='USER_ENTERED')
            except Exception:
                row[6] = url_direta_imagem
                worksheet.append_row(row)
        else:
            worksheet.append_row(row)

    total_linhas = len(worksheet.get_all_values())
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

def process_receipt_photo_task(chat_id: int, message_id: int, chat_user: str, file_id: str, lock_key: str):
    """
    Executado em segundo plano (BackgroundTasks).
    Permite responder HTTP 200 ao Telegram em milissegundos e processar
    análise de IA e inserção no Sheets de forma assíncrona, eliminando timeouts.
    """
    timestamp_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log_entry: Dict[str, Any] = {
        "id": f"log-{int(datetime.now().timestamp() * 1000)}",
        "timestamp": timestamp_str,
        "chat_id": str(chat_id),
        "username": str(chat_user),
        "status_gemini": "Processando",
        "status_sheets": "Pendente",
        "estabelecimento": "-",
        "tipo_documento": "-",
        "categoria": "-",
        "pagamento": "-",
        "valor": 0.0,
        "origem_foto": f"Telegram ID: {file_id[:10]}...",
        "erro": None,
        "detalhes": ""
    }
    processing_logs.insert(0, log_entry)

    try:
        # 1. Envia aviso inicial amigável ao usuário
        send_telegram_message(chat_id, "🔍 Processando comprovante fiscal com Gemini...", message_id)

        # 2. Download da imagem do Telegram e Análise com Gemini
        try:
            img_bytes, url_direta_imagem = download_telegram_file(file_id)
            extracted_data = analyze_receipt(img_bytes)

            # 3. Verificação do status de leitura (se ilegível, notifica e encerra sem gravar)
            if extracted_data.get("status_leitura") == "ilegivel":
                mensagem_usuario = extracted_data.get(
                    "mensagem_erro",
                    "Não consegui ler os dados com clareza pois a imagem está borrada ou muito escura. Poderia enviar uma foto mais nítida, por favor?"
                )
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
            log_entry["detalhes"] = json.dumps(extracted_data, ensure_ascii=False)

        except Exception as e_gemini:
            err_str = str(e_gemini)
            log_entry["status_gemini"] = "Falha"
            log_entry["status_sheets"] = "Cancelado (Erro Gemini)"
            log_entry["erro"] = f"Erro no Gemini: {err_str}"

            if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str:
                friendly_error = (
                    "⏳ *Servidores do Google com Alta Demanda Temporária*\n\n"
                    "A API do Gemini está momentaneamente sobrecarregada (Status 503).\n"
                    "Por favor, aguarde 15 a 30 segundos e **envie a foto novamente**."
                )
            else:
                friendly_error = f"⚠️ Não foi possível analisar o comprovante: {err_str}"

            send_telegram_message(chat_id, friendly_error, message_id)
            return

        # 4. Verificação de Duplicidade e Gravação com Thread Lock Exclusivo
        with sheets_write_lock:
            if verificar_duplicidade(extracted_data):
                alerta_duplicado = (
                    "⚠️ *Atenção: Comprovante Duplicado Detectado!*\n\n"
                    f"Já existe um registro recente para *{extracted_data.get('estabelecimento')}* "
                    f"no valor de *R$ {float(extracted_data.get('valor', 0)):.2f}* na data *{extracted_data.get('data')}*.\n\n"
                    "O lançamento foi ignorado para evitar duplicidade na planilha."
                )
                log_entry["status_sheets"] = "Ignorado (Duplicidade)"
                log_entry["erro"] = "Comprovante idêntico já cadastrado recentemente"
                send_telegram_message(chat_id, alerta_duplicado, message_id)
                return

            # Marca o status de gravação antes de iniciar o append para bloquear requisições paralelas
            log_entry["status_sheets"] = "Gravando na Planilha..."

            # 5. Salva na planilha na aba mensal correspondente com o link direto da imagem
            try:
                log_entry["link_telegram"] = url_direta_imagem
                
                total_linhas, nome_aba = append_to_sheet_aba_mensal(extracted_data, file_id, url_direta_imagem)
                log_entry["status_sheets"] = "Enviado com Sucesso"
                log_entry["aba_planilha"] = nome_aba
                log_entry["detalhes"] += f" | Aba: {nome_aba} | Linha: {total_linhas} | Imagem Direta: OK"
            except Exception as e_sheets:
                log_entry["status_sheets"] = "Falha no Envio"
                log_entry["erro"] = f"Erro Google Sheets: {str(e_sheets)}"
                logger.error(f"Erro ao salvar na planilha Google: {e_sheets}")
                send_telegram_message(chat_id, f"⚠️ Dados extraídos, mas falhou ao gravar na Planilha Google: {str(e_sheets)}", message_id)
                return

        # 6. Mensagem de sucesso limpa no grupo do Telegram
        success_msg = (
            "✅ *Lançamento Registrado com Sucesso!*\n\n"
            f"• *Data:* {extracted_data.get('data')}\n"
            f"• *Estabelecimento:* {extracted_data.get('estabelecimento')}\n"
            f"• *Categoria:* {extracted_data.get('categoria')}\n"
            f"• *Pagamento:* {extracted_data.get('pagamento')}\n"
            f"• *Valor:* R$ {float(extracted_data.get('valor', 0)):.2f}\n"
            f"• *Aba Mensal:* `{nome_aba}`\n\n"
            "📊 *Gravado na Planilha do Google Sheets!*"
        )
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

        # 3. Se houver foto, agenda em background e responde IMEDIATAMENTE HTTP 200 OK
        if "photo" in message:
            largest_photo = message["photo"][-1]
            file_id = largest_photo["file_id"]
            lock_key = f"{chat_id}:{message_id}:{file_id}"

            if lock_key in in_progress_locks:
                logger.info(f"Mensagem {lock_key} já está em andamento. Ignorando chamada concorrente.")
                return Response(status_code=status.HTTP_200_OK)

            in_progress_locks.add(lock_key)

            # Executa o processamento em background (o Telegram recebe 200 OK em menos de 20ms)
            background_tasks.add_task(
                process_receipt_photo_task,
                chat_id=chat_id,
                message_id=message_id,
                chat_user=str(chat_user),
                file_id=file_id,
                lock_key=lock_key
            )

        return Response(status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Erro ao receber webhook: {str(e)}", exc_info=True)
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
            <td colspan="8" class="empty-state">
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
            st = log.get("status_sheets", "")
            is_success = st == "Enviado com Sucesso"
            is_dup = "Duplicidade" in st or "Ignorado" in st
            is_processing = "Gravando" in st or "Processando" in st or "Pendente" in st

            if is_success:
                status_badge = '<span class="badge badge-success">✓ Gravado na Planilha</span>'
            elif is_dup:
                status_badge = '<span class="badge badge-warning">⚠️ Ignorado (Duplicado)</span>'
            elif is_processing:
                status_badge = f'<span class="badge badge-info">⏳ {st}</span>'
            else:
                status_badge = f'<span class="badge badge-error">✕ {st}</span>'

            erro_html = f'<div class="error-msg">{log.get("erro")}</div>' if log.get("erro") else ""

            # Referência ou Link direto da foto no Telegram
            link_tg = log.get("link_telegram")
            if link_tg and link_tg.startswith("http"):
                origem_html = f'<a href="{link_tg}" target="_blank" rel="noopener noreferrer" class="badge-telegram" style="color:#0284c7; text-decoration:none; font-weight:700;">🖼️ Ver Imagem</a>'
            else:
                ref_origem = log.get("origem_foto", "Telegram")
                origem_html = f'<span class="badge-telegram">💬 {ref_origem}</span>'

            aba_nome = log.get("aba_planilha") or "Mensal"
            aba_badge = f'<span class="pill-category" style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; font-weight:700;">{aba_nome}</span>'

            rows_html += f"""
            <tr>
                <td class="font-mono text-muted">{log.get("timestamp")}</td>
                <td class="font-bold">{log.get("estabelecimento")}</td>
                <td><span class="pill-category">{log.get("categoria")}</span></td>
                <td>{log.get("tipo_documento")} / {log.get("pagamento")}</td>
                <td class="text-center">{aba_badge}</td>
                <td class="font-mono font-bold text-right">R$ {log.get("valor", 0.0):.2f}</td>
                <td class="text-center">{origem_html}</td>
                <td class="text-center">{status_badge}{erro_html}</td>
                <td class="text-muted font-mono">{log.get("username")}</td>
            </tr>
            """

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
            --info: #0284c7;
            --info-light: #f0f9ff;
            --telegram-color: #229ED9;
            --telegram-light: #e6f6fd;
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
            max-width: 1250px;
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
            gap: 10px;
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
        .indicator.active-telegram {{
            background: var(--telegram-light);
            color: var(--telegram-color);
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
            font-size: 11px;
            font-weight: 700;
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
            padding: 12px 16px;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 14px 16px;
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
        .badge-warning {{
            background: #fffbeb;
            color: #b45309;
            border: 1px solid #fde68a;
        }}
        .badge-info {{
            background: var(--info-light);
            color: var(--info);
            border: 1px solid #bae6fd;
        }}
        .badge-telegram {{
            display: inline-block;
            background: var(--telegram-light);
            color: #0369a1;
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid #bae6fd;
            font-family: 'JetBrains Mono', monospace;
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
                    <span class="dot"></span> Sheets {'Conectado' if sheets_ok else 'Pendente'}
                </div>
                <div class="indicator {'active' if gemini_ok else 'inactive'}">
                    <span class="dot"></span> Gemini AI {'Ativo' if gemini_ok else 'Sem Chave'}
                </div>
                <div class="indicator {'active-telegram' if telegram_ok else 'inactive'}">
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
                <div class="label">Planilha Conectada</div>
                <div class="value font-mono" style="font-size: 14px; margin-top: 8px;">{sheet_id_display}</div>
                <div class="subtext">Abas Mensais Automáticas</div>
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
                            <th class="text-center">Aba Mensal</th>
                            <th class="text-right">Valor</th>
                            <th class="text-center">Comprovante</th>
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
            <div>Auditor Fiscal AI · Telegram + Google Sheets (Armazenamento Nativo no Telegram)</div>
            <div>Atualização automática a cada 15 segundos</div>
        </footer>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content, status_code=200)
