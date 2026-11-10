import json
import logging
import time
from google import genai
from google.genai import errors
from config import GEMINI_KEYS
from ocr_service import (
    extrair_texto_ocr_space,
    estruturar_dados_do_texto_ocr,
    extrair_data_real_documento
)

logger = logging.getLogger("finance-bot")

# Lista ordenada de modelos para tentativa em caso de erro 503 ou 429
MODELOS_GEMINI = [
    "gemini-3.8-flash",
    "gemini-4-carbon",
    "gemini-4-argon",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-1.5-flash" # Fallback de segurança clássico
]

current_key_index = 0

def get_gemini_client():
    """Retorna o cliente do Gemini utilizando a chave ativa no momento."""
    global current_key_index
    if not GEMINI_KEYS:
        raise ValueError("Nenhuma chave do Gemini foi configurada nas variáveis de ambiente.")
    
    api_key = GEMINI_KEYS[current_key_index]
    return genai.Client(api_key=api_key)

def analisar_comprovante_gemini(img_bytes: bytes, is_pdf: bool = False, mime_type: str = "image/jpeg") -> dict:
    """
    Pipeline Híbrido OCR.space + Auditoria Sênior:
    1. Extrai o texto bruto do PDF ou Imagem via API oficial do OCR.space (https://api.ocr.space/parse/image)
       com OCREngine=2, isTable=true e scale=true.
    2. Estrutura os dados contábeis do texto extraído usando o Gemini (zero erro 503 de renderização de imagem/PDF
       e economia de 90% de tokens).
    3. Caso todos os modelos Gemini falhem (503/429), utiliza o extrator determinístico do OCR.space
       para garantir que nenhum comprovante deixe de ser lançado na planilha.
    """
    global current_key_index

    # ETAPA 1: Extração de texto de imagens e PDFs via OCR.space API
    texto_ocr, erro_ocr = extrair_texto_ocr_space(img_bytes, is_pdf=is_pdf, mime_type=mime_type)

    prompt_sistema = (
        "Você é um auditor financeiro sênior especialista em extração de dados de documentos fiscais e bancários brasileiros "
        "(Notas Fiscais DANFE/NFC-e, Cupons Fiscais, Recibos e Comprovantes de Pagamento/Pix).\n"
        "Regras críticas:\n"
        "1. Extraia ESTRITAMENTE a data real impressa no documento ou no ID Bacen E2E (formato DD/MM/AAAA). NUNCA use a data atual.\n"
        "2. Em comprovantes Pix, identifique 'pagador', 'doc_pagador', 'estabelecimento' (recebedor/favorecido), 'cnpj' (CPF/CNPJ do recebedor) e defina 'pagamento': 'PIX'.\n"
        "3. Em Notas e Cupons Fiscais, extraia todos os itens comprados na lista 'itens' (descricao, quantidade, valor_unitario, valor_total).\n"
        "4. Classifique 'tipo_documento' ('Nota Fiscal', 'Cupom Fiscal' ou 'Recibo') e 'categoria' ('Alimentação', 'Transporte', 'Saúde', 'Lazer', 'Moradia', 'Veículo', 'Educação' ou 'Outros').\n\n"
        "Retorne estritamente em formato JSON, sem blocos de código Markdown (sem ```json), seguindo exatamente esta estrutura:\n"
        "{\n"
        '  "status_leitura": "sucesso",\n'
        '  "mensagem_erro": null,\n'
        '  "data": "DD/MM/AAAA",\n'
        '  "pagador": null,\n'
        '  "doc_pagador": null,\n'
        '  "estabelecimento": "Nome do Recebedor ou Estabelecimento",\n'
        '  "cnpj": null,\n'
        '  "tipo_documento": "Cupom Fiscal",\n'
        '  "categoria": "Outros",\n'
        '  "pagamento": "PIX",\n'
        '  "valor": 0.0,\n'
        '  "itens": []\n'
        "}"
    )

    # Se não houver chaves Gemini configuradas, retorna diretamente a estruturação determinística do OCR.space
    if not GEMINI_KEYS:
        if texto_ocr:
            logger.info("✅ Usando extrator determinístico sobre o texto do OCR.space (sem chaves Gemini).")
            return estruturar_dados_do_texto_ocr(texto_ocr)
        return {
            "status_leitura": "ilegivel",
            "mensagem_erro": f"Falha no OCR.space ({erro_ocr}) e nenhuma chave Gemini configurada."
        }

    effective_mime = "application/pdf" if is_pdf else (mime_type or "image/jpeg")

    # ETAPA 2: Estruturação com rotação de modelos e chaves
    for modelo in MODELOS_GEMINI:
        for chave_tentativa in range(len(GEMINI_KEYS)):
            try:
                client = get_gemini_client()

                if texto_ocr and len(texto_ocr.strip()) >= 15:
                    logger.info(f"🔍 Estruturando texto extraído pelo OCR.space ({len(texto_ocr)} chars) com modelo {modelo} (Chave #{current_key_index})...")
                    conteudos = [
                        f"TEXTO EXTRAÍDO DO DOCUMENTO VIA OCR.SPACE (isTable=true):\n\n{texto_ocr[:14000]}\n\n{prompt_sistema}"
                    ]
                else:
                    logger.info(f"🔍 OCR.space sem texto suficiente ({erro_ocr}). Enviando binário direto para {modelo} (Chave #{current_key_index})...")
                    conteudos = [
                        genai.types.Part.from_bytes(data=img_bytes, mime_type=effective_mime),
                        prompt_sistema
                    ]

                response = client.models.generate_content(
                    model=modelo,
                    contents=conteudos
                )
                
                res_text = response.text.strip()
                if res_text.startswith("```json"):
                    res_text = res_text[7:-3].strip()
                elif res_text.startswith("```"):
                    res_text = res_text[3:-3].strip()
                    
                dados_json = json.loads(res_text)

                # Validação cruzada da data com o extrator Bacen E2E / OCR.space
                if texto_ocr:
                    data_extraida = str(dados_json.get("data") or "").strip()
                    if not data_extraida or data_extraida.upper() in ["NULL", "NONE", "DD/MM/AAAA"]:
                        dados_json["data"] = extrair_data_real_documento(texto_ocr)

                return dados_json

            except errors.APIError as e:
                error_str = str(e)
                if e.code == 429 or "RESOURCE_EXHAUSTED" in error_str or e.code == 503 or "UNAVAILABLE" in error_str:
                    logger.warning(f"⚠️ Modelo '{modelo}' falhou com código {e.code}. Tentando próximo recurso...")
                    if e.code == 429 or "RESOURCE_EXHAUSTED" in error_str:
                        current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"Erro na API do Gemini [{modelo}]: {error_str}")
                    continue
                    
            except Exception as e:
                logger.error(f"Erro interno no modelo {modelo}: {str(e)}")
                continue

    # ETAPA 3: Fallback Determinístico Sênior com os dados do OCR.space se todos os modelos Gemini falharem
    if texto_ocr and len(texto_ocr.strip()) >= 15:
        logger.warning("⚠️ Modelos Gemini indisponíveis no momento. Concluindo auditoria diretamente com o parser fiscal do OCR.space!")
        return estruturar_dados_do_texto_ocr(texto_ocr)

    return {
        "status_leitura": "ilegivel", 
        "mensagem_erro": f"Não foi possível extrair os dados do comprovante (OCR.space: {erro_ocr or 'sem texto'})."
    }
