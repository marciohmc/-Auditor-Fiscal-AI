import React, { useState, useEffect } from 'react';
import {
  Send,
  Bot,
  FileSpreadsheet,
  Terminal,
  Copy,
  Check,
  CheckCircle2,
  Clock,
  ArrowRight,
  RefreshCw,
  ExternalLink,
  Code
} from 'lucide-react';
import { SAMPLE_VOUCHERS, generateVoucherCanvasDataUrl } from '../utils/sampleVouchers';
import { WebhookLog, FiscalEntry } from '../types/finance';

interface TelegramPipelineTabProps {
  onEntryAddedFromWebhook: (entry: FiscalEntry) => void;
}

export const TelegramPipelineTab: React.FC<TelegramPipelineTabProps> = ({
  onEntryAddedFromWebhook,
}) => {
  const [selectedVoucherId, setSelectedVoucherId] = useState(SAMPLE_VOUCHERS[0].id);
  const [isSimulating, setIsSimulating] = useState(false);
  const [telegramReply, setTelegramReply] = useState<string | null>(null);
  const [logs, setLogs] = useState<WebhookLog[]>([]);
  const [activeCodeTab, setActiveCodeTab] = useState<'main_py' | 'requirements' | 'procfile'>('main_py');
  const [copiedCode, setCopiedCode] = useState(false);

  const fetchLogs = async () => {
    try {
      const res = await fetch('/api/logs');
      if (res.ok) {
        const data = await res.json();
        setLogs(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const handleSimulateWebhook = async () => {
    setIsSimulating(true);
    setTelegramReply(null);

    const voucher = SAMPLE_VOUCHERS.find((v) => v.id === selectedVoucherId) || SAMPLE_VOUCHERS[0];
    const imageBase64 = generateVoucherCanvasDataUrl(voucher);

    const simulatedPayload = {
      update_id: 100000000 + Math.floor(Math.random() * 900000),
      message: {
        message_id: 4892,
        from: {
          id: 84920194,
          is_bot: false,
          first_name: 'Marcio',
          username: 'marciohmc',
        },
        chat: {
          id: 84920194,
          first_name: 'Marcio',
          username: 'marciohmc',
          type: 'private',
        },
        date: Math.floor(Date.now() / 1000),
        photo: [
          {
            file_id: 'AgACAgEAAxkBAAIJE1_mock_thumb',
            file_unique_id: 'AQADmock_1',
            width: 320,
            height: 480,
          },
          {
            file_id: 'AgACAgEAAxkBAAIJE1_mock_largest',
            file_unique_id: 'AQADmock_2',
            width: 1080,
            height: 1920,
          },
        ],
      },
      simulated_image_base64: imageBase64,
    };

    try {
      const response = await fetch('/webhook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(simulatedPayload),
      });

      const resData = await response.json();
      if (resData.telegram_reply) {
        setTelegramReply(resData.telegram_reply);
      }
      if (resData.entry) {
        onEntryAddedFromWebhook(resData.entry);
      }
      await fetchLogs();
    } catch (error) {
      console.error(error);
      setTelegramReply('❌ Erro de conexão com o Webhook');
    } finally {
      setIsSimulating(false);
    }
  };

  const pythonCode = `import os
import json
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, Response, status
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

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = FastAPI()
genai_client = genai.Client(api_key=GEMINI_API_KEY)

def get_sheets_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    cred_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    credentials = Credentials.from_service_account_info(cred_dict, scopes=scopes)
    return gspread.authorize(credentials)

def analyze_receipt(image_bytes: bytes) -> Dict[str, Any]:
    system_instruction = (
        "Você é um assistente especialista em auditoria financeira e extração de dados de comprovantes fiscais. "
        "Sua tarefa é analisar imagens de notas fiscais, cupons fiscais e recibos enviados pelos usuários e retornar "
        "estritamente um JSON estruturado com os dados financeiros extraídos."
    )
    user_prompt = (
        "Analise esta imagem de comprovante/nota fiscal e extraia os dados conforme as regras:\\n"
        "1. Identifique se o documento é uma 'Nota Fiscal', 'Cupom Fiscal' ou 'Recibo'.\\n"
        "2. Extraia estritamente um JSON no formato padronizado (data, estabelecimento, valor, categoria, pagamento).\\n"
        "Não inclua texto fora do objeto JSON."
    )
    response = genai_client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            user_prompt
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text.strip())

def append_to_sheet(data: Dict[str, Any]):
    gc = get_sheets_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(0)
    row = [
        data.get("data", "Não Informado"),
        data.get("estabelecimento", "Não Informado"),
        data.get("tipo_documento", "Não Informado"),
        data.get("categoria", "Não Informado"),
        data.get("pagamento", "Não Informado"),
        float(data.get("valor", 0.0))
    ]
    worksheet.append_row(row)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    # Processa mensagens de foto enviadas ao bot Telegram
    ...`;

  const requirementsCode = `fastapi==0.115.0
uvicorn==0.32.0
python-telegram-bot==21.7
google-genai>=2.4.0
gspread==6.1.4
google-auth==2.36.0
requests==2.32.3`;

  const procfileCode = `web: uvicorn main:app --host 0.0.0.0 --port $PORT`;

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Overview Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight font-sans">
              Pipeline Telegram Bot & Google Sheets
            </h1>
            <p className="text-sm text-slate-600 mt-1 max-w-2xl">
              Integração completa que recebe fotos de comprovantes no Telegram, executa a extração contábil via Gemini AI e grava a linha formatada no Google Sheets.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono bg-slate-50 border border-slate-200 px-3 py-2 rounded-lg text-slate-600 shrink-0">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>Endpoint: /webhook (Ativo)</span>
          </div>
        </div>
      </div>

      {/* Simulator Section: Left Telegram Phone Mockup, Right Execution details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Simulator controls & Telegram Chat Mockup (lg:col-span-6) */}
        <div className="lg:col-span-6 bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">
                Simulador de Envio Telegram Bot
              </h3>
            </div>
            <span className="text-xs text-slate-400">@AuditorFiscalBot</span>
          </div>

          <div className="space-y-3">
            <label className="text-xs font-semibold text-slate-700 block">
              Selecione o Comprovante para Simular Envio ao Bot:
            </label>
            <select
              value={selectedVoucherId}
              onChange={(e) => setSelectedVoucherId(e.target.value)}
              className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-slate-800 focus:ring-1 focus:ring-emerald-500 outline-hidden font-medium"
            >
              {SAMPLE_VOUCHERS.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} (R$ {v.expectedValor.toFixed(2)} - {v.badge})
                </option>
              ))}
            </select>

            <button
              onClick={handleSimulateWebhook}
              disabled={isSimulating}
              className="w-full py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 text-white rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-2 shadow-xs cursor-pointer"
            >
              {isSimulating ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Enviando Foto & Processando Webhook...</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Disparar Webhook Telegram</span>
                </>
              )}
            </button>
          </div>

          {/* Telegram Chat Simulation Interface */}
          <div className="border border-slate-200 rounded-xl overflow-hidden bg-slate-100 mt-4">
            <div className="bg-[#24A1DE] text-white px-4 py-2.5 flex items-center justify-between text-xs font-semibold">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center">
                  <Bot className="w-3.5 h-3.5" />
                </div>
                <span>Auditor Fiscal Bot</span>
              </div>
              <span className="text-[11px] text-white/80">Online</span>
            </div>

            <div className="p-4 space-y-3 min-h-[220px] max-h-[300px] overflow-y-auto bg-[#E6EBEF] text-xs">
              {/* User message with photo */}
              <div className="flex justify-end">
                <div className="bg-[#EEFFDE] text-slate-800 p-2.5 rounded-lg rounded-tr-none shadow-xs max-w-[80%] space-y-1.5 border border-[#D5E8C4]">
                  <div className="w-48 h-24 bg-slate-200 rounded flex items-center justify-center text-slate-500 text-[11px] font-mono">
                    📷 [Foto de Comprovante Fiscal]
                  </div>
                  <div className="text-[10px] text-slate-400 text-right">14:32 ✓✓</div>
                </div>
              </div>

              {/* Bot interim processing message */}
              {isSimulating && (
                <div className="flex justify-start">
                  <div className="bg-white text-slate-800 p-2.5 rounded-lg rounded-tl-none shadow-xs max-w-[80%] text-xs flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#24A1DE]" />
                    <span>🔍 Processando comprovante fiscal com Gemini...</span>
                  </div>
                </div>
              )}

              {/* Bot reply message */}
              {telegramReply ? (
                <div className="flex justify-start">
                  <div className="bg-white text-slate-800 p-3 rounded-lg rounded-tl-none shadow-xs max-w-[85%] text-xs whitespace-pre-wrap leading-relaxed border border-slate-200 font-sans">
                    {telegramReply}
                    <div className="text-[10px] text-slate-400 text-right mt-1.5">14:33</div>
                  </div>
                </div>
              ) : (
                !isSimulating && (
                  <div className="text-center py-6 text-slate-400 text-xs">
                    Pressione "Disparar Webhook Telegram" acima para testar o fluxo.
                  </div>
                )
              )}
            </div>
          </div>
        </div>

        {/* Google Sheets Mapping & Live Row (lg:col-span-6) */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Estrutura da Planilha Google Sheets
                </h3>
              </div>
              <span className="text-xs text-slate-500 font-mono">append_row(row)</span>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Cada comprovante processado pelo webhook é automaticamente registrado como uma nova linha na planilha do Google Sheets através do método <code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded font-mono">append_to_sheet(extracted_data)</code>.
            </p>

            {/* Google Sheets Mockup Visual Table */}
            <div className="border border-slate-200 rounded-lg overflow-x-auto bg-white">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-emerald-50 text-emerald-900 font-semibold border-b border-emerald-100 text-[11px]">
                    <th className="py-2 px-3 border-r border-emerald-100 font-mono">A (Data)</th>
                    <th className="py-2 px-3 border-r border-emerald-100 font-mono">B (Estabelecimento)</th>
                    <th className="py-2 px-3 border-r border-emerald-100 font-mono">C (Documento)</th>
                    <th className="py-2 px-3 border-r border-emerald-100 font-mono">D (Categoria)</th>
                    <th className="py-2 px-3 border-r border-emerald-100 font-mono">E (Pagamento)</th>
                    <th className="py-2 px-3 font-mono text-right">F (Valor R$)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-[11px] font-sans">
                  <tr className="hover:bg-slate-50">
                    <td className="py-2 px-3 border-r border-slate-100 font-mono tabular-nums">02/11/2026</td>
                    <td className="py-2 px-3 border-r border-slate-100 font-semibold">Pão de Açúcar</td>
                    <td className="py-2 px-3 border-r border-slate-100">Cupom Fiscal</td>
                    <td className="py-2 px-3 border-r border-slate-100">Alimentação</td>
                    <td className="py-2 px-3 border-r border-slate-100">Cartão de Crédito</td>
                    <td className="py-2 px-3 font-mono text-right tabular-nums font-semibold">148.75</td>
                  </tr>
                  <tr className="hover:bg-slate-50">
                    <td className="py-2 px-3 border-r border-slate-100 font-mono tabular-nums">01/11/2026</td>
                    <td className="py-2 px-3 border-r border-slate-100 font-semibold">Auto Posto Shell</td>
                    <td className="py-2 px-3 border-r border-slate-100">Nota Fiscal</td>
                    <td className="py-2 px-3 border-r border-slate-100">Veículo</td>
                    <td className="py-2 px-3 border-r border-slate-100">PIX</td>
                    <td className="py-2 px-3 font-mono text-right tabular-nums font-semibold">265.40</td>
                  </tr>
                  <tr className="hover:bg-slate-50">
                    <td className="py-2 px-3 border-r border-slate-100 font-mono tabular-nums">30/10/2026</td>
                    <td className="py-2 px-3 border-r border-slate-100 font-semibold">Raia Drogasil</td>
                    <td className="py-2 px-3 border-r border-slate-100">Cupom Fiscal</td>
                    <td className="py-2 px-3 border-r border-slate-100">Saúde</td>
                    <td className="py-2 px-3 border-r border-slate-100">Cartão de Débito</td>
                    <td className="py-2 px-3 font-mono text-right tabular-nums font-semibold">92.40</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="p-3 bg-emerald-50/50 rounded-lg border border-emerald-100 text-xs text-emerald-800 flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <span>
                Compatibilidade 100% com a automação Python original: dados gravados em tempo real na aba principal da planilha.
              </span>
            </div>
          </div>

          {/* Webhook Logs */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-emerald-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Log de Transações do Webhook
                </h3>
              </div>
              <button
                onClick={fetchLogs}
                className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1"
              >
                <RefreshCw className="w-3 h-3" />
                <span>Atualizar</span>
              </button>
            </div>

            <div className="divide-y divide-slate-100 text-xs max-h-[160px] overflow-y-auto">
              {logs.map((log) => (
                <div key={log.id} className="py-2 flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-slate-900">{log.payload_summary}</span>
                    <p className="text-[11px] text-slate-400 font-mono">
                      Chat: {log.chat_id} · {new Date(log.timestamp).toLocaleTimeString('pt-BR')}
                    </p>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700">
                    {log.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Standalone Deployment Code Guide */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4 text-emerald-600" />
            <h3 className="text-sm font-bold text-slate-900">
              Código-Fonte do Bot Python & Arquitetura de Deploy
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg text-xs">
              <button
                onClick={() => setActiveCodeTab('main_py')}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  activeCodeTab === 'main_py'
                    ? 'bg-white text-slate-900 font-semibold shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                main.py
              </button>
              <button
                onClick={() => setActiveCodeTab('requirements')}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  activeCodeTab === 'requirements'
                    ? 'bg-white text-slate-900 font-semibold shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                requirements.txt
              </button>
              <button
                onClick={() => setActiveCodeTab('procfile')}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  activeCodeTab === 'procfile'
                    ? 'bg-white text-slate-900 font-semibold shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Procfile
              </button>
            </div>

            <button
              onClick={() => {
                const code =
                  activeCodeTab === 'main_py'
                    ? pythonCode
                    : activeCodeTab === 'requirements'
                    ? requirementsCode
                    : procfileCode;
                handleCopyCode(code);
              }}
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors flex items-center gap-1"
            >
              {copiedCode ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-emerald-600">Copiado!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copiar</span>
                </>
              )}
            </button>
          </div>
        </div>

        <pre className="p-4 bg-slate-950 text-slate-200 font-mono text-xs rounded-xl overflow-x-auto border border-slate-800 max-h-[320px] leading-relaxed">
          {activeCodeTab === 'main_py' && pythonCode}
          {activeCodeTab === 'requirements' && requirementsCode}
          {activeCodeTab === 'procfile' && procfileCode}
        </pre>
      </div>
    </div>
  );
};
