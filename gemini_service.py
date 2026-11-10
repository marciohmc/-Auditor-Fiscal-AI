import json
import logging
import time
from google import genai
from google.genai import errors
from config import GEMINI_KEYS

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
    Analisa a imagem ou PDF percorrendo a lista de modelos e chaves.
    Em caso de erro 503 (sobrecarga) ou 429 (cota), alterna o modelo ou a chave automaticamente.
    """
    global current_key_index
    
    prompt_sistema = (
        "Você é um auditor financeiro sênior especialista em extração multimodal de dados de documentos fiscais e bancários brasileiros. "
        "Analise minuciosamente o documento enviado e extraia estritamente as informações financeiras em formato JSON, "
        "sem blocos de código Markdown (sem ```json), seguindo exatamente esta estrutura:\n"
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

    effective_mime = "application/pdf" if is_pdf else (mime_type or "image/jpeg")

    # Itera sobre cada modelo da lista
    for modelo in MODELOS_GEMINI:
        # Tenta com cada chave disponível para o modelo atual
        for chave_tentativa in range(len(GEMINI_KEYS)):
            try:
                client = get_gemini_client()
                logger.info(f"🔍 Enviando documento para o modelo {modelo} (Chave índice {current_key_index})...")

                response = client.models.generate_content(
                    model=modelo,
                    contents=[
                        genai.types.Part.from_bytes(data=img_bytes, mime_type=effective_mime),
                        prompt_sistema
                    ]
                )
                
                res_text = response.text.strip()
                if res_text.startswith("```json"):
                    res_text = res_text[7:-3].strip()
                elif res_text.startswith("```"):
                    res_text = res_text[3:-3].strip()
                    
                return json.loads(res_text)

            except errors.APIError as e:
                error_str = str(e)
                
                # Se for erro 429 (Cota Excedida) ou 503 (Servidor Indisponível)
                if e.code == 429 or "RESOURCE_EXHAUSTED" in error_str or e.code == 503 or "UNAVAILABLE" in error_str:
                    logger.warning(f"⚠️ Modelo '{modelo}' falhou com código {e.code}. Tentando próximo recurso...")
                    
                    # Se for 429, aproveita e alterna a chave também
                    if e.code == 429 or "RESOURCE_EXHAUSTED" in error_str:
                        current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
                        
                    time.sleep(1) # Breve pausa antes da próxima tentativa na lista
                    continue # Pula para a próxima tentativa (próxima chave ou próximo modelo)
                else:
                    logger.error(f"Erro crítico na API do Gemini [{modelo}]: {error_str}")
                    return {"status_leitura": "ilegivel", "mensagem_erro": f"Erro na API ({modelo}): {error_str}"}
                    
            except Exception as e:
                logger.error(f"Erro interno no modelo {modelo}: {str(e)}")
                # Se o erro for de modelo não encontrado ou incompatível, avança para o próximo da lista
                continue

    return {
        "status_leitura": "ilegivel", 
        "mensagem_erro": "Todos os modelos e chaves do Gemini falharam ou estão indisponíveis no momento. Tente novamente em instantes."
    }
