import os
import io
import time
import json
import logging
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

import requests
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_WEBHOOK_URL,
    TELEGRAM_API_BASE,
    SPREADSHEET_ID,
    GOOGLE_CREDENTIALS_JSON,
    GEMINI_KEYS,
    PORT,
    PASSCM,
    logger
)
from gemini_service import analisar_comprovante_gemini
from sheets_service import registrar_transacao_planilha

app = FastAPI(
    title="Sistema de Extração Multimodal e Controle Financeiro Automatizado",
    description="Bot Telegram + FastAPI (Render) + Gemini Auditoria Sênior + Google Sheets",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Controle de concorrência e deduplicação
processed_update_ids: OrderedDict[int, float] = OrderedDict()
in_progress_locks: Set[str] = set()
processing_history: List[Dict[str, Any]] = []

def send_telegram_message(chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN não configurado. Mensagem ignorada.")
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
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado.")
    res = requests.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id}, timeout=15).json()
    file_path = res.get("result", {}).get("file_path", "")
    if not file_path:
        raise ValueError(f"Não foi possível localizar o arquivo no Telegram para o ID: {file_id}")
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    file_res = requests.get(download_url, timeout=30)
    return file_res.content, download_url

def processar_comprovante_pipeline(
    chat_id: int,
    message_id: int,
    file_id: str,
    file_name: str,
    caption: str,
    sender_name: str,
    is_pdf: bool = False
):
    lock_key = f"{chat_id}:{message_id}:{file_id}"
    if lock_key in in_progress_locks:
        logger.info(f"Comprovante já em processamento: {lock_key}")
        return

    in_progress_locks.add(lock_key)
    log_entry = {
        "id": f"log-{int(time.time()*1000)}",
        "chat_id": chat_id,
        "sender": sender_name,
        "file_name": file_name,
        "timestamp": datetime.now().isoformat(),
        "status": "processando",
        "dados": None,
        "erro": None
    }
    processing_history.append(log_entry)

    try:
        send_telegram_message(chat_id, "⏳ *Recebido!* Auditando comprovante com IA...", reply_to_message_id=message_id)
        file_bytes, download_url = download_telegram_file(file_id)
        mime_type = "application/pdf" if is_pdf else "image/jpeg"

        resultado_auditoria = analisar_comprovante_gemini(file_bytes, is_pdf=is_pdf, mime_type=mime_type)

        if resultado_auditoria.get("status_leitura") == "ilegivel":
            msg_erro = resultado_auditoria.get("mensagem_erro") or "Documento ilegível ou dados cortados."
            send_telegram_message(
                chat_id,
                f"❌ *Atenção - Documento Não Auditado*\n\n{msg_erro}\n\n_Por favor, reenvie uma foto mais nítida ou o PDF original._",
                reply_to_message_id=message_id
            )
            log_entry["status"] = "ilegivel"
            log_entry["erro"] = msg_erro
            return

        sheets_res = registrar_transacao_planilha(
            dados=resultado_auditoria,
            responsavel=sender_name,
            receipt_link=download_url,
            obs=caption
        )

        log_entry["dados"] = resultado_auditoria
        log_entry["sheets"] = sheets_res

        data_doc = resultado_auditoria.get("data", "N/A")
        estab = resultado_auditoria.get("estabelecimento", "Não Identificado")
        valor = float(resultado_auditoria.get("valor") or 0.0)
        pagto = resultado_auditoria.get("pagamento", "Não Informado")
        categ = resultado_auditoria.get("categoria", "Outros")
        tipo_doc = resultado_auditoria.get("tipo_documento", "Comprovante")
        itens = resultado_auditoria.get("itens", [])

        if sheets_res.get("duplicado"):
            msg_sucesso = (
                f"⚠️ *Comprovante Auditado (Já Cadastrado)*\n\n"
                f"📅 *Data:* `{data_doc}`\n"
                f"🏢 *Estabelecimento:* `{estab}`\n"
                f"💰 *Valor:* `R$ {valor:,.2f}`\n"
                f"💳 *Pagamento:* `{pagto}`\n"
                f"📂 *Categoria:* `{categ}`\n"
                f"📊 *Aba:* `{sheets_res.get('aba')}`\n\n"
                f"_Este comprovante já constava na planilha e não foi duplicado._"
            )
            log_entry["status"] = "duplicado"
        elif sheets_res.get("sucesso"):
            msg_itens = ""
            if itens and len(itens) > 0:
                msg_itens = "\n\n🛍️ *Itens Discriminados:*\n" + "\n".join(
                    [f"• {it.get('quantidade', 1)}x {it.get('descricao', 'Item')} - R$ {it.get('valor_total', 0.0):,.2f}" for it in itens[:8]]
                )
                if len(itens) > 8:
                    msg_itens += f"\n_... e mais {len(itens)-8} itens._"

            msg_sucesso = (
                f"✅ *Auditoria Concluída e Registrada!* 📊\n\n"
                f"📅 *Data:* `{data_doc}`\n"
                f"🏢 *Estabelecimento/Favorecido:* `{estab}`\n"
                f"💰 *Valor Total:* `R$ {valor:,.2f}`\n"
                f"💳 *Forma de Pagamento:* `{pagto}`\n"
                f"📂 *Categoria:* `{categ}`\n"
                f"📄 *Documento:* `{tipo_doc}`\n"
                f"📌 *Aba Mensal:* `{sheets_res.get('aba')}`"
                f"{msg_itens}\n\n"
                f"🔗 [Ver Comprovante]({download_url})"
            )
            log_entry["status"] = "sucesso"
        else:
            msg_sucesso = (
                f"✅ *Auditoria Realizada*, porém houve erro ao gravar no Google Sheets:\n"
                f"`{sheets_res.get('motivo') or sheets_res.get('erro')}`\n\n"
                f"📅 Data: `{data_doc}` | Valor: `R$ {valor:,.2f}`"
            )
            log_entry["status"] = "erro_sheets"

        send_telegram_message(chat_id, msg_sucesso, reply_to_message_id=message_id)

    except Exception as e:
        logger.error(f"Erro no pipeline do comprovante: {e}")
        log_entry["status"] = "erro"
        log_entry["erro"] = str(e)
        send_telegram_message(
            chat_id,
            f"⚠️ *Erro durante o processamento:* {str(e)[:150]}",
            reply_to_message_id=message_id
        )
    finally:
        in_progress_locks.discard(lock_key)

@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corpo da requisição inválido")

    update_id = body.get("update_id")
    if update_id:
        agora = time.time()
        while processed_update_ids and (agora - next(iter(processed_update_ids.values())) > 300):
            processed_update_ids.popitem(last=False)
        if update_id in processed_update_ids:
            return JSONResponse({"ok": True, "notice": "Update duplicado ignorado"})
        processed_update_ids[update_id] = agora

    message = body.get("message") or body.get("channel_post")
    if not message:
        return JSONResponse({"ok": True})

    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    caption = message.get("caption", "").strip()
    user = message.get("from", {})
    sender_name = user.get("first_name", "") + (" " + user.get("last_name", "") if user.get("last_name") else "")
    sender_name = sender_name.strip() or user.get("username") or "Usuário Telegram"

    text = message.get("text", "").strip()
    if text.startswith("/start") or text.startswith("/ajuda"):
        msg_help = (
            "👋 *Bem-vindo ao Auditor Financeiro Inteligente!*\n\n"
            "Envie uma *Foto* ou *PDF* de:\n"
            "• Comprovante Pix ou Transferência Bancária\n"
            "• Nota Fiscal Eletrônica (DANFE / NFC-e)\n"
            "• Cupom Fiscal de Supermercado ou Restaurante\n"
            "• Recibo de Pagamento\n\n"
            "Os dados serão auditados pelo Gemini e registrados automaticamente no seu Google Sheets estruturado por mês! 🚀"
        )
        send_telegram_message(chat_id, msg_help, reply_to_message_id=message_id)
        return JSONResponse({"ok": True})

    if "photo" in message:
        photos = message["photo"]
        best_photo = photos[-1]
        file_id = best_photo["file_id"]
        background_tasks.add_task(
            processar_comprovante_pipeline,
            chat_id=chat_id,
            message_id=message_id,
            file_id=file_id,
            file_name=f"foto_{file_id[:8]}.jpg",
            caption=caption,
            sender_name=sender_name,
            is_pdf=False
        )
        return JSONResponse({"ok": True})

    if "document" in message:
        doc = message["document"]
        file_id = doc["file_id"]
        file_name = doc.get("file_name", "documento")
        mime = doc.get("mime_type", "").lower()
        is_pdf = mime == "application/pdf" or file_name.lower().endswith(".pdf")
        
        background_tasks.add_task(
            processar_comprovante_pipeline,
            chat_id=chat_id,
            message_id=message_id,
            file_id=file_id,
            file_name=file_name,
            caption=caption,
            sender_name=sender_name,
            is_pdf=is_pdf
        )
        return JSONResponse({"ok": True})

    return JSONResponse({"ok": True})

@app.get("/setup-webhook")
def setup_webhook():
    if not TELEGRAM_BOT_TOKEN:
        return {"sucesso": False, "erro": "TELEGRAM_BOT_TOKEN não configurado."}
    if not TELEGRAM_WEBHOOK_URL:
        return {"sucesso": False, "erro": "TELEGRAM_WEBHOOK_URL não configurado."}

    target_url = TELEGRAM_WEBHOOK_URL.rstrip("/")
    if not target_url.endswith("/webhook"):
        target_url += "/webhook"

    api_url = f"{TELEGRAM_API_BASE}/setWebhook"
    try:
        res = requests.post(api_url, json={"url": target_url, "drop_pending_updates": False}, timeout=15)
        return res.json()
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

@app.get("/webhook-info")
def webhook_info():
    if not TELEGRAM_BOT_TOKEN:
        return {"sucesso": False, "erro": "TELEGRAM_BOT_TOKEN não configurado."}
    try:
        res = requests.get(f"{TELEGRAM_API_BASE}/getWebhookInfo", timeout=10)
        return res.json()
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

@app.get("/health")
def health():
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "telegram_token_presente": bool(TELEGRAM_BOT_TOKEN),
            "webhook_url": TELEGRAM_WEBHOOK_URL,
            "google_sheets_presente": bool(GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID),
            "spreadsheet_id": SPREADSHEET_ID[:8] + "..." if SPREADSHEET_ID else None,
            "gemini_keys_count": len(GEMINI_KEYS)
        }
    }

@app.get("/api/logs")
def get_logs():
    return {"logs": list(reversed(processing_history[-50:]))}

@app.get("/", response_class=HTMLResponse)
def index_page():
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Auditor Financeiro AI - Bot & Google Sheets</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #f3f4f6; padding: 40px; margin: 0; }}
            .card {{ max-width: 700px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            h1 {{ color: #10b981; margin-top: 0; }}
            .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: bold; background: #065f46; color: #6ee7b7; }}
            .item {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #1f2937; }}
            a.btn {{ display: inline-block; background: #10b981; color: #fff; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 20px; }}
            a.btn:hover {{ background: #059669; }}
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">SISTEMA ATIVO</span>
            <h1>Auditor Financeiro Multimodal</h1>
            <p>Servidor FastAPI ativo com suporte a Telegram Webhook, Gemini AI e Google Sheets.</p>
            <div class="item"><span>Telegram Bot:</span> <b>{'Configurado' if TELEGRAM_BOT_TOKEN else 'Pendente'}</b></div>
            <div class="item"><span>Google Sheets:</span> <b>{'Conectado' if (SPREADSHEET_ID and GOOGLE_CREDENTIALS_JSON) else 'Pendente'}</b></div>
            <div class="item"><span>Chaves Gemini Ativas:</span> <b>{len(GEMINI_KEYS)} chave(s)</b></div>
            <div class="item"><span>Endpoint Webhook:</span> <code>/webhook</code></div>
            <a href="/setup-webhook" class="btn">⚡ Configurar Webhook no Telegram</a>
            <a href="/webhook-info" class="btn" style="background: #374151; margin-left: 10px;">ℹ️ Ver Info do Webhook</a>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main.py:app", host="0.0.0.0", port=PORT, reload=False)
