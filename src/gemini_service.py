import io
import re
import json
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

# Dependências opcionais com fallback seguro
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

from config import GEMINI_KEYS, logger

current_key_index = 0

PROMPT_SISTEMA_AUDITORIA = """
Você é um auditor financeiro sênior especialista em extração multimodal de dados de documentos fiscais e bancários brasileiros (Notas Fiscais DANFE/NFC-e, Cupons Fiscais, Recibos e Comprovantes de Pagamento/Pix).

Sua missão é analisar minuciosamente o documento enviado e extrair estritamente as informações financeiras em formato JSON, sem blocos de código Markdown (sem ```json), seguindo rigorosamente estas diretrizes:

1. VALIDAÇÃO DE LEGIBILIDADE (CRÍTICO):
- Analise a nitidez, iluminação e enquadramento.
- Se o documento estiver ilegível, rasurado ou cortado nos dados essenciais (valor total, data ou estabelecimento/favorecido), defina 'status_leitura': 'ilegivel' e forneça uma explicação clara e amigável em 'mensagem_erro'.
- Se legível, defina 'status_leitura': 'sucesso' e 'mensagem_erro': null.

2. EXTRAÇÃO DE DATA E HORA REAL DO COMPROVANTE:
- Extraia ESTRITAMENTE a data de emissão ou realização da transação impressa no próprio documento (formato DD/MM/AAAA).
- NUNCA utilize a data atual do sistema, nem a data de processamento ou envio da foto.
- Em comprovantes Pix, busque a data e hora registradas no comprovante bancário ou no ID da transação Bacen (E2E).

3. REGRA ESPECIAL PARA COMPROVANTES PIX E TRANSFERÊNCIAS:
- 'pagador': Nome completo da pessoa ou empresa que efetuou a transferência/pagamento (Origem/Débito) ou null.
- 'doc_pagador': CPF ou CNPJ de quem pagou ou null.
- 'recebedor' / 'estabelecimento': Nome da pessoa ou empresa que recebeu o valor (Destinatário/Favorecido/Crédito).
- 'doc_recebedor' / 'cnpj': CPF ou CNPJ do favorecido/recebedor ou null.
- 'pagamento': Defina estritamente como 'PIX'.

4. NOTAS FISCAIS, CUPONS E RECIBOS (ITENS DISCRIMINADOS):
- Mapeie a tabela 'DADOS DO PRODUTO / SERVIÇOS' ou lista de itens comprados no array 'itens'.
- Para cada item capture: 'descricao' (string), 'quantidade' (número), 'valor_unitario' (número) e 'valor_total' (número).
- Se o documento não discriminar itens individuais, retorne 'itens': [].

5. CLASSIFICAÇÃO DE CATEGORIA E FORMA DE PAGAMENTO:
- 'tipo_documento': 'Nota Fiscal', 'Cupom Fiscal' ou 'Recibo'.
- 'categoria': 'Alimentação', 'Transporte', 'Saúde', 'Lazer', 'Moradia', 'Veículo', 'Educação' ou 'Outros'.
- 'pagamento': 'PIX', 'Cartão de Crédito', 'Cartão de Débito', 'Dinheiro', 'Boleto' ou 'Não Informado'.
- 'valor': Valor numérico total da transação (float).

Retorne EXCLUSIVAMENTE o JSON estruturado abaixo:
{
  "status_leitura": "sucesso",
  "mensagem_erro": null,
  "data": "DD/MM/AAAA",
  "pagador": null,
  "doc_pagador": null,
  "estabelecimento": "Nome do Recebedor ou Estabelecimento",
  "cnpj": null,
  "tipo_documento": "Cupom Fiscal",
  "categoria": "Outros",
  "pagamento": "PIX",
  "valor": 0.0,
  "itens": []
}
"""

MESES_TEXTO_MAP = {
    'jan': 1, 'janeiro': 1,
    'fev': 2, 'fevereiro': 2,
    'mar': 3, 'marco': 3, 'março': 3,
    'abr': 4, 'abril': 4,
    'mai': 5, 'maio': 5,
    'jun': 6, 'junho': 6,
    'jul': 7, 'julho': 7,
    'ago': 8, 'agosto': 8,
    'set': 9, 'setembro': 9,
    'out': 10, 'outubro': 10,
    'nov': 11, 'novembro': 11,
    'dez': 12, 'dezembro': 12
}

def extrair_data_e_hora_seguranca(texto: str) -> tuple[str, str]:
    data_encontrada = ""
    hora_encontrada = ""
    
    m_e2e = re.search(r"\bE\d{8}(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})[A-Za-z0-9]+\b", texto)
    if m_e2e:
        ano, mes, dia, hh, mm = int(m_e2e.group(1)), int(m_e2e.group(2)), int(m_e2e.group(3)), m_e2e.group(4), m_e2e.group(5)
        if 1 <= dia <= 31 and 1 <= mes <= 12 and 2020 <= ano <= 2035:
            return f"{dia:02d}/{mes:02d}/{ano}", f"{hh}:{mm}"

    m_data = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.](20\d{2})\b", texto)
    if m_data:
        dia, mes, ano = int(m_data.group(1)), int(m_data.group(2)), int(m_data.group(3))
        if 1 <= dia <= 31 and 1 <= mes <= 12 and 2020 <= ano <= 2035:
            data_encontrada = f"{dia:02d}/{mes:02d}/{ano}"

    if not data_encontrada:
        m_txt = re.search(r"\b(\d{1,2})\s*(?:de\s+|[/.-])?\s*([A-Za-zÀ-ÖØ-öø-ÿ]{3,10})\.?\s*(?:de\s+|[/.-])?\s*(20\d{2})\b", texto, re.IGNORECASE)
        if m_txt:
            dia = int(m_txt.group(1))
            mes_txt = m_txt.group(2).lower()
            ano = int(m_txt.group(3))
            mes_num = MESES_TEXTO_MAP.get(mes_txt[:3]) or MESES_TEXTO_MAP.get(mes_txt)
            if mes_num and 1 <= dia <= 31 and 2020 <= ano <= 2035:
                data_encontrada = f"{dia:02d}/{mes_num:02d}/{ano}"

    m_hora = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b", texto)
    if m_hora:
        hora_encontrada = m_hora.group(0).strip()

    return data_encontrada, hora_encontrada

def otimizar_imagem_se_necessario(img_bytes: bytes, max_dim: int = 1600, quality: int = 82) -> bytes:
    if not PIL_AVAILABLE or len(img_bytes) <= 500 * 1024:
        return img_bytes
    try:
        img = Image.open(io.BytesIO(img_bytes))
        if max(img.width, img.height) > max_dim:
            scale = max_dim / max(img.width, img.height)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        otimizado = buf.getvalue()
        logger.info(f"Imagem otimizada: {len(img_bytes)/1024:.1f} KB -> {len(otimizado)/1024:.1f} KB")
        return otimizado
    except Exception as e:
        logger.warning(f"Aviso na otimização de imagem: {e}")
        return img_bytes

def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    if not PYPDF_AVAILABLE:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texto_acumulado = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texto_acumulado.append(t)
        return "\n".join(texto_acumulado).strip()
    except Exception as e:
        logger.warning(f"Aviso na extração direta de PDF: {e}")
        return ""

def get_active_gemini_key() -> str:
    global current_key_index
    if not GEMINI_KEYS:
        raise ValueError("Nenhuma chave (GEMINI_API_KEY ou GEMINI_API_KEY_1) configurada no ambiente.")
    return GEMINI_KEYS[current_key_index % len(GEMINI_KEYS)]

def alternar_chave_gemini():
    global current_key_index
    if len(GEMINI_KEYS) > 1:
        prev = current_key_index % len(GEMINI_KEYS)
        current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
        nxt = current_key_index % len(GEMINI_KEYS)
        logger.warning(f"⚠️ Chave Gemini [{prev}] esgotada (429). Alternando para chave [{nxt}]...")
    else:
        logger.warning("⚠️ Limite de cota atingido e apenas 1 chave Gemini está configurada.")

def analisar_comprovante_gemini(arquivo_bytes: bytes, is_pdf: bool = False, mime_type: str = "image/jpeg") -> dict:
    import base64
    import requests

    if not GEMINI_KEYS:
        return {
            "status_leitura": "ilegivel",
            "mensagem_erro": "Nenhuma chave GEMINI_API_KEY configurada no ambiente."
        }

    texto_pdf = ""
    if is_pdf:
        texto_pdf = extrair_texto_pdf(arquivo_bytes)

    if not is_pdf and (mime_type.startswith("image/") or mime_type == "application/octet-stream"):
        arquivo_bytes = otimizar_imagem_se_necessario(arquivo_bytes)
        mime_type = "image/jpeg"

    if texto_pdf and len(texto_pdf) >= 40:
        logger.info(f"📄 PDF com texto digital extraído ({len(texto_pdf)} caracteres). Modo texto de alta velocidade ativado.")
        parts = [
            {
                "text": f"DADOS DISCRIMINADOS DO DOCUMENTO FISCAL / COMPROVANTE (PDF):\n\n{texto_pdf[:14000]}\n\n"
            },
            {
                "text": PROMPT_SISTEMA_AUDITORIA
            }
        ]
    else:
        b64_data = base64.b64encode(arquivo_bytes).decode("utf-8")
        parts = [
            {
                "inline_data": {
                    "mime_type": "application/pdf" if is_pdf else mime_type,
                    "data": b64_data
                }
            },
            {
                "text": PROMPT_SISTEMA_AUDITORIA
            }
        ]

    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generation_config": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    modelos_candidatos = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.8-flash"]
    ultimo_erro = None

    for model_name in modelos_candidatos:
        for _ in range(len(GEMINI_KEYS)):
            api_key = get_active_gemini_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

            try:
                logger.info(f"Auditando documento com Gemini [{model_name}] | Chave [{current_key_index % len(GEMINI_KEYS)}]...")
                res = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "finance-bot"},
                    timeout=60
                )

                if res.status_code == 429:
                    logger.warning(f"⚠️ Cota 429 atingida na chave [{current_key_index % len(GEMINI_KEYS)}]. Alternando...")
                    alternar_chave_gemini()
                    time.sleep(1.0)
                    continue

                if res.status_code == 503:
                    logger.warning(f"⚠️ Modelo {model_name} em sobrecarga (503). Alternando modelo...")
                    ultimo_erro = f"Modelo {model_name} sobrecarregado (503)"
                    time.sleep(1.5)
                    break

                if res.status_code != 200:
                    logger.error(f"Erro na API Gemini ({res.status_code}): {res.text[:200]}")
                    ultimo_erro = f"Erro na API Gemini ({res.status_code})"
                    time.sleep(1.0)
                    continue

                resp_json = res.json()
                candidates = resp_json.get("candidates", [])
                if not candidates:
                    return {"status_leitura": "ilegivel", "mensagem_erro": "Nenhum candidato retornado pelo modelo."}

                raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:-3].strip()
                elif raw_text.startswith("```"):
                    raw_text = raw_text[3:-3].strip()

                parsed = json.loads(raw_text)

                data_gemini = str(parsed.get("data") or "").strip()
                if not data_gemini or data_gemini.upper() in ["NULL", "NONE", "NÃO INFORMADA"]:
                    if texto_pdf:
                        d_seg, _ = extrair_data_e_hora_seguranca(texto_pdf)
                        if d_seg:
                            parsed["data"] = d_seg

                if "status_leitura" not in parsed:
                    parsed["status_leitura"] = "sucesso"
                if "itens" not in parsed or not isinstance(parsed["itens"], list):
                    parsed["itens"] = []

                logger.info(f"✅ Auditoria concluída com sucesso: {parsed.get('estabelecimento')} - R$ {parsed.get('valor')} ({parsed.get('data')})")
                return parsed

            except requests.exceptions.Timeout:
                logger.warning(f"⚠️ Timeout (>60s) ao chamar {model_name}. Tentando próximo modelo...")
                ultimo_erro = "Timeout na API Gemini (>60s)"
                break
            except json.JSONDecodeError as e_json:
                logger.error(f"Erro ao decodificar JSON retornado pelo Gemini: {e_json} | Texto: {raw_text[:200]}")
                ultimo_erro = f"JSON inválido retornado: {str(e_json)}"
            except Exception as e_gen:
                logger.error(f"Erro geral ao processar com Gemini: {e_gen}")
                ultimo_erro = str(e_gen)

    return {
        "status_leitura": "ilegivel",
        "mensagem_erro": f"Não foi possível processar o comprovante: {ultimo_erro or 'Falha na comunicação com o Gemini'}"
    }
