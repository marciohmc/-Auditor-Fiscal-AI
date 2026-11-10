import io
import re
import base64
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple

import requests
from config import OCR_SPACE_API_KEY, OCR_SPACE_API_URL, logger

# Tentativa opcional de usar Pillow para garantir que imagens fiquem < 1MB (limite do plano Free do OCR.space)
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

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

def comprimir_imagem_para_ocr_space(file_bytes: bytes, max_kb: int = 950) -> bytes:
    """
    A API gratuita do OCR.space possui limite estrito de 1024 KB (1 MB) por arquivo.
    Se a imagem exceder 950 KB e o Pillow estiver disponível, redimensiona e comprime automaticamente.
    """
    if len(file_bytes) <= max_kb * 1024 or not PIL_AVAILABLE:
        return file_bytes
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        max_dim = 1600
        if max(img.width, img.height) > max_dim:
            scale = max_dim / max(img.width, img.height)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
        for quality in [82, 72, 60, 50]:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_kb * 1024:
                logger.info(f"Imagem ajustada para limite de 1MB do OCR.space: {len(file_bytes)/1024:.1f}KB -> {len(data)/1024:.1f}KB")
                return data
        return data
    except Exception as e:
        logger.warning(f"Não foi possível comprimir imagem para OCR.space: {e}")
        return file_bytes

def extrair_texto_ocr_space(file_bytes: bytes, is_pdf: bool = False, mime_type: str = "image/jpeg") -> Tuple[str, str]:
    """
    Envia imagem ou PDF para https://api.ocr.space/parse/image seguindo a documentação oficial:
    - OCREngine=2 (melhor reconhecimento para cupons, tabelas e fontes térmicas) com fallback para OCREngine=1
    - isTable=true (extração estrita linha por linha para preservar tabelas de produtos e valores)
    - scale=true (upscaling automático para letras miúdas)
    - detectOrientation=true (rotação automática de fotos invertidas)
    - filetype=PDF ou JPG
    Retorna (texto_extraido, mensagem_erro).
    """
    if not is_pdf:
        file_bytes = comprimir_imagem_para_ocr_space(file_bytes)
        mime_prefix = "data:image/jpeg;base64,"
        filetype = "JPG"
    else:
        mime_prefix = "data:application/pdf;base64,"
        filetype = "PDF"

    # Codifica em Base64 sem quebras de linha (\n), conforme exigido pela documentação do OCR.space
    b64_clean = base64.b64encode(file_bytes).decode("utf-8").replace("\n", "").replace("\r", "")
    base64_payload = f"{mime_prefix}{b64_clean}"

    headers = {
        "apikey": OCR_SPACE_API_KEY
    }

    # Tentativa 1: OCREngine 2 (recomendado pela documentação para recibos, notas e números)
    # Tentativa 2: OCREngine 1 com language='por' (fallback rápido e estável para PDFs longos)
    engines_to_try = [
        {"OCREngine": "2", "language": "auto"},
        {"OCREngine": "1", "language": "por"}
    ]

    ultimo_erro = ""

    for cfg in engines_to_try:
        engine = cfg["OCREngine"]
        payload = {
            "base64Image": base64_payload,
            "filetype": filetype,
            "isTable": "true",
            "scale": "true",
            "detectOrientation": "true",
            "OCREngine": engine,
        }
        if cfg["language"] != "auto":
            payload["language"] = cfg["language"]

        try:
            logger.info(f"📡 Enviando {'PDF' if is_pdf else 'Imagem'} ({len(file_bytes)/1024:.1f} KB) para OCR.space API (OCREngine={engine}, isTable=true)...")
            response = requests.post(
                OCR_SPACE_API_URL,
                headers=headers,
                data=payload,
                timeout=45
            )

            if response.status_code != 200:
                ultimo_erro = f"HTTP {response.status_code} no OCR.space"
                logger.warning(f"⚠️ {ultimo_erro} com OCREngine={engine}. Tentando fallback...")
                continue

            res_json = response.json()

            # Verifica flag IsErroredOnProcessing da documentação do OCR.space
            if res_json.get("IsErroredOnProcessing"):
                err_msg = res_json.get("ErrorMessage")
                if isinstance(err_msg, list):
                    err_msg = "; ".join(str(x) for x in err_msg)
                ultimo_erro = str(err_msg or res_json.get("ErrorDetails") or "Erro no processamento OCR.space")
                logger.warning(f"⚠️ OCR.space retornou erro com OCREngine={engine}: {ultimo_erro}")
                continue

            parsed_results = res_json.get("ParsedResults") or []
            textos_paginas = []
            for page in parsed_results:
                parsed_text = page.get("ParsedText") or ""
                if parsed_text.strip():
                    textos_paginas.append(parsed_text.strip())

            texto_completo = "\n".join(textos_paginas).strip()
            if texto_completo:
                logger.info(f"✅ OCR.space (Engine {engine}) extraiu {len(texto_completo)} caracteres com sucesso.")
                return texto_completo, ""
            else:
                ultimo_erro = "Nenhum texto detectado na imagem/PDF pelo OCR.space."

        except requests.exceptions.Timeout:
            ultimo_erro = f"Timeout ao comunicar com OCR.space (OCREngine={engine})"
            logger.warning(f"⚠️ {ultimo_erro}")
        except Exception as e:
            ultimo_erro = f"Erro na chamada OCR.space: {str(e)}"
            logger.error(ultimo_erro)

    return "", ultimo_erro

def extrair_data_real_documento(texto: str) -> str:
    """
    Extrai ESTRITAMENTE a data impressa no comprovante/nota fiscal:
    1. ID da Transação Pix Bacen (E2E): E + 8 dígitos ISPB + YYYYMMDDHHMM + hash
    2. Rótulos explícitos de data de pagamento/transferência/emissão
    3. Datas numéricas DD/MM/AAAA ou textuais (04 NOV 2026, 04 de nov. de 2026)
    """
    ano_atual = datetime.now().year

    # 1. ID Bacen E2E em Comprovantes Pix (fonte mais confiável e imutável)
    m_e2e = re.search(r"\bE\d{8}(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})[A-Za-z0-9]+\b", texto)
    if m_e2e:
        ano, mes, dia = int(m_e2e.group(1)), int(m_e2e.group(2)), int(m_e2e.group(3))
        if 1 <= dia <= 31 and 1 <= mes <= 12 and 2020 <= ano <= 2035:
            return f"{dia:02d}/{mes:02d}/{ano}"

    def validar_e_formatar_data( trecho: str ) -> str:
        # Formato DD/MM/AAAA ou DD.MM.AAAA ou DD-MM-AAAA
        m1 = re.search(r"\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(20\d{2})\b", trecho)
        if m1:
            d, m, a = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
            if 1 <= d <= 31 and 1 <= m <= 12 and 2020 <= a <= 2035:
                return f"{d:02d}/{m:02d}/{a}"

        # Formato por extenso: "04 NOV 2026", "04 de nov. de 2026", "04 de novembro de 2026"
        m2 = re.search(r"\b(\d{1,2})\s*(?:de\s+|[/.-])?\s*([A-Za-zÀ-ÖØ-öø-ÿ]{3,10})\.?\s*(?:de\s+|[/.-])?\s*(20\d{2})\b", trecho, re.IGNORECASE)
        if m2:
            d = int(m2.group(1))
            mes_txt = m2.group(2).lower()
            a = int(m2.group(3))
            m = MESES_TEXTO_MAP.get(mes_txt[:3]) or MESES_TEXTO_MAP.get(mes_txt)
            if m and 1 <= d <= 31 and 2020 <= a <= 2035:
                return f"{d:02d}/{m:02d}/{a}"

        # Formato curto DD/MM/AA
        m3 = re.search(r"\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2})\b", trecho)
        if m3:
            d, m, ac = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
            a = 2000 + ac
            if 1 <= d <= 31 and 1 <= m <= 12 and 2020 <= a <= 2035:
                return f"{d:02d}/{m:02d}/{a}"

        # Formato sem ano (ex: "04 NOV - 15:30")
        m4 = re.search(r"\b(\d{1,2})\s*(?:de\s+)?([A-Za-zÀ-ÖØ-öø-ÿ]{3,10})\.?(?:\s*às|\s*-|\s+\d{2}:\d{2})", trecho, re.IGNORECASE)
        if m4:
            d = int(m4.group(1))
            mes_txt = m4.group(2).lower()
            m = MESES_TEXTO_MAP.get(mes_txt[:3]) or MESES_TEXTO_MAP.get(mes_txt)
            if m and 1 <= d <= 31:
                return f"{d:02d}/{m:02d}/{ano_atual}"

        return ""

    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    # 2. Busca prioritária em linhas com rótulos de emissão/pagamento/realização
    for i, linha in enumerate(linhas):
        if re.search(r"(?:DATA\s+DA\s+EMISS[ÃA]O|DATA\s+DE\s+EMISS[ÃA]O|EMISS[ÃA]O|REALIZADO\s+EM|PAGO\s+EM|DATA\s+DO\s+PAGAMENTO|DATA\s+DA\s+TRANSA[CÇ][ÃA]O|DATA\s+E\s+HORA|QUANDO)", linha, re.IGNORECASE):
            janela = " ".join(linhas[i:i+3])
            dt = validar_e_formatar_data(janela)
            if dt:
                return dt

    # 3. Varredura geral em todas as linhas
    for linha in linhas:
        dt = validar_e_formatar_data(linha)
        if dt:
            return dt

    return datetime.now().strftime("%d/%m/%Y")

def extrair_valor_total(texto: str) -> float:
    """Extrai o valor monetário total da nota, cupom ou comprovante Pix."""
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    def parse_moeda(val_str: str) -> float:
        s = val_str.strip()
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return 0.0

    # 1. Busca próxima a rótulos explícitos de Valor Total / Valor Pago / Valor da Transferência
    padroes_rotulo = [
        r"(?:VALOR\s+TOTAL\s+DA\s+NOTA|VALOR\s+A\s+PAGAR|VALOR\s+TOTAL|TOTAL\s+R\$|VALOR\s+PAGO|VALOR\s+DA\s+TRANSFER[EÊ]NCIA|VALOR\s+DO\s+PIX|VALOR)"
    ]
    for i, linha in enumerate(linhas):
        if any(re.search(p, linha, re.IGNORECASE) for p in padroes_rotulo):
            janela = " ".join(linhas[i:i+3])
            matches = re.findall(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\b", janela)
            if matches:
                for m in matches:
                    v = parse_moeda(m)
                    if v > 0:
                        return v

    # 2. Busca qualquer valor precedido por R$
    matches_rs = re.findall(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})\b", texto)
    if matches_rs:
        valores = [parse_moeda(m) for m in matches_rs if parse_moeda(m) > 0]
        if valores:
            return max(valores)

    # 3. Fallback: maior valor decimal formato brasileiro no documento
    matches_dec = re.findall(r"\b(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})\b", texto)
    valores_dec = [parse_moeda(m) for m in matches_dec if 0 < parse_moeda(m) < 500000]
    if valores_dec:
        return max(valores_dec)

    return 0.0

def extrair_itens_tabela(texto: str) -> List[Dict[str, Any]]:
    """Extrai itens discriminados em tabelas de DANFE / NFC-e / Cupom Fiscal (geradas com isTable=true)."""
    itens = []
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    for l in linhas:
        # Ignora linhas de totais ou cabeçalhos
        if re.search(r"\b(?:VALOR\s+TOTAL|SUBTOTAL|DESCONTO|TROCO|TRIBUTOS|CHAVE\s+DE\s+ACESSO|CONSULTA|CONSUMIDOR|PROTOCOLO)\b", l, re.IGNORECASE):
            continue

        # Padrão tabular: [Código opcional] Descrição   Qtd   [Unidade]   VlrUnit   VlrTotal
        m = re.search(
            r"^(?:\d{1,14}\s+)?([A-Za-zÀ-ÖØ-öø-ÿ0-9\.\-\/\s]{3,65}?)\s+(\d+(?:[\.,]\d+)?)\s*(?:UN|KG|PC|L|CX|PCT|M|UNID)?\s+(?:x\s*|R\$\s*)?(\d+(?:[\.,]\d{2,4}))\s+(?:R\$\s*)?(\d+[\.,]\d{2})$",
            l,
            re.IGNORECASE
        )
        if m:
            desc = re.sub(r"\s+", " ", m.group(1)).strip()
            try:
                qtd = float(m.group(2).replace(",", "."))
                v_unit = float(m.group(3).replace(",", "."))
                v_tot = float(m.group(4).replace(",", "."))
                if len(desc) >= 3 and v_tot > 0:
                    itens.append({
                        "descricao": desc,
                        "quantidade": qtd,
                        "valor_unitario": v_unit,
                        "valor_total": v_tot
                    })
            except ValueError:
                pass

    return itens

def estruturar_dados_do_texto_ocr(texto: str) -> Dict[str, Any]:
    """
    Analisa o texto extraído pelo OCR.space e constrói o JSON padronizado de Auditoria Financeira.
    Atua como motor determinístico ou fallback imediato caso o LLM não esteja disponível.
    """
    if not texto or len(texto.strip()) < 10:
        return {
            "status_leitura": "ilegivel",
            "mensagem_erro": "O OCR.space não conseguiu identificar texto legível no documento enviado."
        }

    texto_upper = texto.upper()
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    # 1. Data e Valor
    data_doc = extrair_data_real_documento(texto)
    valor_total = extrair_valor_total(texto)

    # 2. Identificação do Tipo de Documento e Forma de Pagamento
    is_pix = any(k in texto_upper for k in ["PIX", "COMPROVANTE DE TRANSFER", "ID DA TRANSA", "CHAVE PIX", "INSTITUICAO RECEBEDORA", "E00"])
    if "DANFE" in texto_upper or "NF-E" in texto_upper or "NOTA FISCAL" in texto_upper:
        tipo_documento = "Nota Fiscal"
    elif "CUPOM FISCAL" in texto_upper or "NFC-E" in texto_upper or "SAT" in texto_upper or "EXTRATO" in texto_upper:
        tipo_documento = "Cupom Fiscal"
    else:
        tipo_documento = "Recibo"

    if is_pix or "PIX" in texto_upper:
        pagamento = "PIX"
    elif "CREDITO" in texto_upper or "CRÉDITO" in texto_upper:
        pagamento = "Cartão de Crédito"
    elif "DEBITO" in texto_upper or "DÉBITO" in texto_upper:
        pagamento = "Cartão de Débito"
    elif "BOLETO" in texto_upper:
        pagamento = "Boleto"
    elif "DINHEIRO" in texto_upper or "ESPECIE" in texto_upper:
        pagamento = "Dinheiro"
    else:
        pagamento = "Não Informado"

    # 3. Extração de CNPJ / CPF
    cnpjs = re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", texto)
    cpfs = re.findall(r"\b(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\*{3}\.\d{3}\.\d{3}-\*{2})\b", texto)
    cnpj_principal = cnpjs[0] if cnpjs else (cpfs[0] if cpfs else None)

    # 4. Extração de Recebedor / Estabelecimento e Pagador
    estabelecimento = None
    pagador = None

    for i, l in enumerate(linhas):
        # Procura favorecido/recebedor em comprovante Pix
        if re.search(r"^(?:PARA|DESTINAT[ÁA]RIO|FAVORECIDO|RECEBEDOR|NOME\s+DO\s+FAVORECIDO|QUEM\s+RECEBEU):?$", l, re.IGNORECASE):
            if i + 1 < len(linhas):
                estabelecimento = linhas[i + 1].strip()
        elif re.search(r"^(?:PARA|DESTINAT[ÁA]RIO|FAVORECIDO|RECEBEDOR):\s*(.+)$", l, re.IGNORECASE):
            m_rec = re.search(r"^(?:PARA|DESTINAT[ÁA]RIO|FAVORECIDO|RECEBEDOR):\s*(.+)$", l, re.IGNORECASE)
            if m_rec:
                estabelecimento = m_rec.group(1).strip()

        # Procura pagador em comprovante Pix
        if re.search(r"^(?:DE|PAGADOR|ORIGEM|QUEM\s+PAGOU|NOME\s+DO\s+PAGADOR):?$", l, re.IGNORECASE):
            if i + 1 < len(linhas):
                pagador = linhas[i + 1].strip()
        elif re.search(r"^(?:DE|PAGADOR|ORIGEM):\s*(.+)$", l, re.IGNORECASE):
            m_pag = re.search(r"^(?:DE|PAGADOR|ORIGEM):\s*(.+)$", l, re.IGNORECASE)
            if m_pag:
                pagador = m_pag.group(1).strip()

    # Se não achou por rótulo Pix, pega a primeira linha de razão social / cabeçalho da nota
    if not estabelecimento:
        ignorar = ["COMPROVANTE", "DOCUMENTO AUXILIAR", "DANFE", "CUPOM FISCAL", "NOTA FISCAL", "PIX", "TRANSFERENCIA", "BANCO", "NUBANK", "ITAU", "BRADESCO", "SANTANDER", "INTER", "CAIXA", "BB"]
        for l in linhas[:8]:
            l_clean = l.replace("\t", " ").strip()
            if len(l_clean) >= 4 and not re.match(r"^[\d\s/.-]+$", l_clean):
                if not any(ig in l_clean.upper() for ig in ignorar):
                    estabelecimento = l_clean[:70]
                    break

    if not estabelecimento:
        estabelecimento = "Estabelecimento Auditado"

    # 5. Classificação inteligente de Categoria
    if any(k in texto_upper for k in ["RESTAURANTE", "MERCADO", "SUPERMERCADO", "PADARIA", "LANCHONETE", "IFOOD", "CAFE", "ALIMENT", "ATACADAO", "ASSAI", "PAO DE ACUCAR", "CARREFOUR"]):
        categoria = "Alimentação"
    elif any(k in texto_upper for k in ["COMBUSTIVEL", "GASOLINA", "ETANOL", "DIESEL", "POSTO", "AUTO POSTO", "ESTACIONAMENTO", "PEDAGIO", "OFICINA", "PNEU"]):
        categoria = "Veículo"
    elif any(k in texto_upper for k in ["UBER", "99POP", "TAXI", "PASSAGEM", "ONIBUS", "METRO", "TRANSPORTE", "LATAM", "GOL", "AZUL"]):
        categoria = "Transporte"
    elif any(k in texto_upper for k in ["FARMACIA", "DROGARIA", "DROGASIL", "RAIA", "PAGUE MENOS", "CLINICA", "HOSPITAL", "MEDICO", "EXAME", "LABORATORIO"]):
        categoria = "Saúde"
    elif any(k in texto_upper for k in ["ENERGIA", "ELETRICA", "AGUA", "SANEAMENTO", "CONDOMINIO", "ALUGUEL", "INTERNET", "CLARO", "VIVO", "TIM", "GAS"]):
        categoria = "Moradia"
    elif any(k in texto_upper for k in ["ESCOLA", "FACULDADE", "UNIVERSIDADE", "CURSO", "LIVRARIA", "EDUCACAO"]):
        categoria = "Educação"
    elif any(k in texto_upper for k in ["CINEMA", "INGRESSO", "SHOW", "TEATRO", "NETFLIX", "SPOTIFY", "HOTEL", "LAZER"]):
        categoria = "Lazer"
    else:
        categoria = "Outros"

    # 6. Itens discriminados
    itens = extrair_itens_tabela(texto)

    if valor_total <= 0:
        return {
            "status_leitura": "ilegivel",
            "mensagem_erro": "Não foi possível identificar o valor total da transação no documento lido pelo OCR.space."
        }

    return {
        "status_leitura": "sucesso",
        "mensagem_erro": None,
        "data": data_doc,
        "pagador": pagador,
        "doc_pagador": cpfs[1] if len(cpfs) > 1 else None,
        "estabelecimento": estabelecimento,
        "cnpj": cnpj_principal,
        "tipo_documento": tipo_documento,
        "categoria": categoria,
        "pagamento": pagamento,
        "valor": valor_total,
        "itens": itens,
        "ocr_engine": "ocr.space"
    }
