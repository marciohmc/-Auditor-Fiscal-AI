import express, { Request, Response } from 'express';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import { GoogleGenAI, Type } from '@google/genai';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const port = process.env.PORT || 3000;

// Body parsing with 25MB limit for high-res receipt photos
app.use(express.json({ limit: '25mb' }));
app.use(express.urlencoded({ extended: true, limit: '25mb' }));

// Initialize GoogleGenAI SDK (server-side only)
const ai = new GoogleGenAI({
  apiKey: process.env.GEMINI_API_KEY || '',
  httpOptions: {
    headers: {
      'User-Agent': 'aistudio-build',
    },
  },
});

// In-Memory Database for Financial Audit Entries
interface StoredFiscalEntry {
  id: string;
  tipo_documento: 'Nota Fiscal' | 'Cupom Fiscal' | 'Recibo';
  data: string;
  estabelecimento: string;
  valor: number;
  categoria: 'Alimentação' | 'Transporte' | 'Saúde' | 'Lazer' | 'Moradia' | 'Veículo' | 'Educação' | 'Outros';
  pagamento: 'PIX' | 'Cartão de Crédito' | 'Cartão de Débito' | 'Dinheiro' | 'Boleto' | 'Não Informado';
  cnpj?: string;
  itens?: Array<{
    descricao: string;
    quantidade: number;
    valor_unitario: number;
    valor_total: number;
  }>;
  status_auditoria: 'auditado' | 'pendente' | 'divergencia';
  audit_notes?: string;
  imagem_url?: string;
  raw_json?: string;
  origem: 'upload' | 'camera' | 'telegram_webhook' | 'amostra';
  criado_em: string;
}

interface WebhookLog {
  id: string;
  timestamp: string;
  chat_id: number;
  origem: string;
  file_id?: string;
  payload_summary: string;
  status: 'sucesso' | 'erro' | 'processando';
  extracted_data?: any;
  error_message?: string;
}

// Initial realistic Brazilian fiscal dataset
let fiscalEntries: StoredFiscalEntry[] = [
  {
    id: 'doc-001',
    tipo_documento: 'Cupom Fiscal',
    data: '02/11/2026',
    estabelecimento: 'Pão de Açúcar - Loja Jardins',
    valor: 148.75,
    categoria: 'Alimentação',
    pagamento: 'Cartão de Crédito',
    cnpj: '47.508.411/0001-56',
    itens: [
      { descricao: 'Café Torrado Especial 500g', quantidade: 2, valor_unitario: 28.50, valor_total: 57.00 },
      { descricao: 'Leite Integral Tipo A 1L', quantidade: 4, valor_unitario: 6.90, valor_total: 27.60 },
      { descricao: 'Queijo Minas Frescal 400g', quantidade: 1, valor_unitario: 24.90, valor_total: 24.90 },
      { descricao: 'Pão Artesanal Fermentação Natural', quantidade: 1, valor_unitario: 18.50, valor_total: 18.50 },
      { descricao: 'Maçã Fuji Seleção 1kg', quantidade: 1.1, valor_unitario: 18.86, valor_total: 20.75 }
    ],
    status_auditoria: 'auditado',
    audit_notes: 'Valores conferidos com extrato bancário. Itens de consumo essencial.',
    origem: 'amostra',
    criado_em: '2026-11-02T14:32:00Z',
    raw_json: JSON.stringify({
      tipo_documento: "Cupom Fiscal",
      data: "02/11/2026",
      estabelecimento: "Pão de Açúcar - Loja Jardins",
      valor: 148.75,
      categoria: "Alimentação",
      pagamento: "Cartão de Crédito"
    }, null, 2)
  },
  {
    id: 'doc-002',
    tipo_documento: 'Nota Fiscal',
    data: '01/11/2026',
    estabelecimento: 'Auto Posto Shell Bandeirantes Ltda',
    valor: 265.40,
    categoria: 'Veículo',
    pagamento: 'PIX',
    cnpj: '02.433.918/0003-88',
    itens: [
      { descricao: 'Gasolina V-Power Aditivada', quantidade: 45.06, valor_unitario: 5.89, valor_total: 265.40 }
    ],
    status_auditoria: 'auditado',
    audit_notes: 'Abastecimento veículo frota operacional.',
    origem: 'amostra',
    criado_em: '2026-11-01T18:15:00Z',
    raw_json: JSON.stringify({
      tipo_documento: "Nota Fiscal",
      data: "01/11/2026",
      estabelecimento: "Auto Posto Shell Bandeirantes Ltda",
      valor: 265.40,
      categoria: "Veículo",
      pagamento: "PIX"
    }, null, 2)
  },
  {
    id: 'doc-003',
    tipo_documento: 'Cupom Fiscal',
    data: '30/10/2026',
    estabelecimento: 'Raia Drogasil S.A. - Farmácia',
    valor: 92.40,
    categoria: 'Saúde',
    pagamento: 'Cartão de Débito',
    cnpj: '61.585.865/0240-31',
    itens: [
      { descricao: 'Protetor Solar FPS 50 200ml', quantidade: 1, valor_unitario: 59.90, valor_total: 59.90 },
      { descricao: 'Dipirona Monoidratada 500mg 20 comp', quantidade: 2, valor_unitario: 8.50, valor_total: 17.00 },
      { descricao: 'Vitamina C Efervescente 10 comp', quantidade: 1, valor_unitario: 15.50, valor_total: 15.50 }
    ],
    status_auditoria: 'auditado',
    audit_notes: 'Despesa com medicamentos e cuidados de saúde.',
    origem: 'amostra',
    criado_em: '2026-10-30T11:45:00Z',
    raw_json: JSON.stringify({
      tipo_documento: "Cupom Fiscal",
      data: "30/10/2026",
      estabelecimento: "Raia Drogasil S.A. - Farmácia",
      valor: 92.40,
      categoria: "Saúde",
      pagamento: "Cartão de Débito"
    }, null, 2)
  },
  {
    id: 'doc-004',
    tipo_documento: 'Recibo',
    data: '28/10/2026',
    estabelecimento: 'Climatiza Serviços Técnicos de Refrigeração',
    valor: 450.00,
    categoria: 'Moradia',
    pagamento: 'PIX',
    cnpj: '38.120.944/0001-12',
    itens: [
      { descricao: 'Higienização e Manutenção Preventiva Split 12000 BTUs', quantidade: 2, valor_unitario: 225.00, valor_total: 450.00 }
    ],
    status_auditoria: 'pendente',
    audit_notes: 'Aguardando nota fiscal de serviço avulsa (recibo simples fornecido).',
    origem: 'amostra',
    criado_em: '2026-10-28T16:20:00Z',
    raw_json: JSON.stringify({
      tipo_documento: "Recibo",
      data: "28/10/2026",
      estabelecimento: "Climatiza Serviços Técnicos de Refrigeração",
      valor: 450.00,
      categoria: "Moradia",
      pagamento: "PIX"
    }, null, 2)
  }
];

let webhookLogs: WebhookLog[] = [
  {
    id: 'log-001',
    timestamp: '2026-11-02T14:32:00Z',
    chat_id: 84920194,
    origem: 'Telegram Bot @AuditorFiscalBot',
    payload_summary: 'Foto recebida (file_id: AgACAgEAAxkBA...) - Cupom Pão de Açúcar',
    status: 'sucesso',
    extracted_data: {
      tipo_documento: 'Cupom Fiscal',
      data: '02/11/2026',
      estabelecimento: 'Pão de Açúcar - Loja Jardins',
      valor: 148.75,
      categoria: 'Alimentação',
      pagamento: 'Cartão de Crédito'
    }
  }
];

// Helper: Run Gemini multimodal analysis
async function analyzeFiscalImage(base64Data: string, mimeType: string) {
  const systemInstruction = 
    "Você é um assistente especialista em auditoria financeira e extração de dados de comprovantes fiscais. " +
    "Sua tarefa é analisar imagens de notas fiscais, cupons fiscais e recibos enviados pelos usuários e retornar " +
    "estritamente um JSON estruturado com os dados financeiros extraídos.";

  const userPrompt = 
    "Analise esta imagem de documento fiscal conforme as regras abaixo:\n\n" +
    "1. VALIDAÇÃO DE LEGIBILIDADE (CRÍTICO):\n" +
    "- Se a imagem estiver borrada, muito escura, cortada ou se os dados principais (valor total, estabelecimento ou data) estiverem completamente ilegíveis, defina 'status_leitura': 'ilegivel' e forneça uma justificativa amigável em 'mensagem_erro'.\n" +
    "- Se a imagem for legível, defina 'status_leitura': 'sucesso' e 'mensagem_erro': null.\n\n" +
    "2. CLASSIFICAÇÃO DO DOCUMENTO:\n" +
    "- 'tipo_documento': 'Nota Fiscal', 'Cupom Fiscal' ou 'Recibo'.\n" +
    "- 'categoria': 'Alimentação', 'Transporte', 'Saúde', 'Lazer', 'Moradia', 'Veículo', 'Educação' ou 'Outros'.\n" +
    "- 'pagamento': 'PIX', 'Cartão de Crédito', 'Cartão de Débito', 'Dinheiro', 'Boleto' ou 'Não Informado'.\n\n" +
    "3. EXTRAÇÃO DE ITENS DETALHADOS:\n" +
    "- Extraia a lista de itens comprados no array 'itens' com 'descricao', 'quantidade' e 'valor_total_item'. Se não houver itens, retorne [].\n\n" +
    "4. FORMATAÇÃO E TIPAGEM:\n" +
    "- 'valor': float do valor total líquido (ex: 125.50).\n" +
    "- 'data': padrão DD/MM/AAAA.\n\n" +
    "Não inclua texto, explicação ou marcações markdown (como ```json) fora do objeto JSON.";

  // Resilient model invocation with retry and fallback
  const candidateModels = ['gemini-3.8-flash', 'gemini-flash-latest', 'gemini-3.1-flash-lite'];
  let lastError: any = null;
  let responseText = '';

  for (const modelName of candidateModels) {
    try {
      const response = await ai.models.generateContent({
        model: modelName,
        contents: [
          {
            inlineData: {
              mimeType: mimeType || 'image/jpeg',
              data: base64Data,
            },
          },
          {
            text: userPrompt,
          },
        ],
        config: {
          systemInstruction,
          responseMimeType: 'application/json',
          responseSchema: {
            type: Type.OBJECT,
            properties: {
              status_leitura: {
                type: Type.STRING,
                description: "'sucesso' ou 'ilegivel'",
              },
              mensagem_erro: {
                type: Type.STRING,
                description: "Mensagem amigável de erro se status_leitura for 'ilegivel', senão null",
              },
              tipo_documento: {
                type: Type.STRING,
                description: "Classificação: 'Nota Fiscal', 'Cupom Fiscal' ou 'Recibo'",
              },
              data: {
                type: Type.STRING,
                description: "Data de emissão DD/MM/AAAA ou 'Não Informado'",
              },
              estabelecimento: {
                type: Type.STRING,
                description: "Nome do fornecedor, loja ou prestador de serviço",
              },
              valor: {
                type: Type.NUMBER,
                description: "Valor total líquido do comprovante (ex: 45.90)",
              },
              categoria: {
                type: Type.STRING,
                description: "Categoria do gasto: Alimentação, Transporte, Saúde, Lazer, Moradia, Veículo, Educação ou Outros",
              },
              pagamento: {
                type: Type.STRING,
                description: "Forma de pagamento: PIX, Cartão de Crédito, Cartão de Débito, Dinheiro, Boleto ou Não Informado",
              },
              cnpj: {
                type: Type.STRING,
                description: "CNPJ do estabelecimento se identificado, senão 'Não Informado'",
              },
              itens: {
                type: Type.ARRAY,
                description: "Itens comprados listados no cupom/nota fiscal",
                items: {
                  type: Type.OBJECT,
                  properties: {
                    descricao: { type: Type.STRING },
                    quantidade: { type: Type.NUMBER },
                    valor_unitario: { type: Type.NUMBER },
                    valor_total: { type: Type.NUMBER },
                  },
                },
              },
            },
            required: [
              'status_leitura',
            ],
          },
        },
      });

      responseText = (response.text ?? '').trim();
      if (responseText) {
        break; // Success
      }
    } catch (err: any) {
      console.warn(`Tentativa com ${modelName} falhou:`, err?.message || err);
      lastError = err;
      // Brief pause before trying fallback model
      await new Promise((res) => setTimeout(res, 600));
    }
  }

  if (!responseText) {
    throw lastError || new Error('Não foi possível obter resposta do modelo de IA.');
  }

  const rawText = responseText;
  let cleaned = rawText;
  if (cleaned.startsWith('```json')) {
    cleaned = cleaned.substring(7);
  }
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.substring(3);
  }
  if (cleaned.endsWith('```')) {
    cleaned = cleaned.substring(0, cleaned.length - 3);
  }

  const parsed = JSON.parse(cleaned.trim());

  // Strict normalization fallback
  const validTipos = ['Nota Fiscal', 'Cupom Fiscal', 'Recibo'];
  if (!validTipos.includes(parsed.tipo_documento)) {
    parsed.tipo_documento = 'Nota Fiscal';
  }

  const validCategorias = ['Alimentação', 'Transporte', 'Saúde', 'Lazer', 'Moradia', 'Veículo', 'Educação', 'Outros'];
  if (!validCategorias.includes(parsed.categoria)) {
    parsed.categoria = 'Outros';
  }

  const validPagamentos = ['PIX', 'Cartão de Crédito', 'Cartão de Débito', 'Dinheiro', 'Boleto', 'Não Informado'];
  if (!validPagamentos.includes(parsed.pagamento)) {
    parsed.pagamento = 'Não Informado';
  }

  parsed.valor = typeof parsed.valor === 'number' ? Number(parsed.valor.toFixed(2)) : 0.0;
  if (!parsed.data) parsed.data = 'Não Informado';
  if (!parsed.estabelecimento) parsed.estabelecimento = 'Não Informado';

  return {
    parsed,
    rawText: cleaned.trim(),
  };
}

// ----------------------------------------------------
// API Endpoints
// ----------------------------------------------------

// Health Check
app.get('/api/health', (_req: Request, res: Response) => {
  res.json({
    status: 'ok',
    service: 'finance-bot',
    geminiConfigured: !!process.env.GEMINI_API_KEY,
    totalEntries: fiscalEntries.length,
    timestamp: new Date().toISOString(),
  });
});

// Extraction Endpoint (receives Base64 image)
app.post('/api/extract', async (req: Request, res: Response) => {
  try {
    const { imageBase64, mimeType } = req.body;

    if (!imageBase64) {
      return res.status(400).json({ error: 'Nenhuma imagem foi fornecida para extração.' });
    }

    if (!process.env.GEMINI_API_KEY) {
      return res.status(500).json({
        error: 'Chave GEMINI_API_KEY não configurada no ambiente. Adicione a chave no painel Secrets.',
      });
    }

    // Clean base64 data
    let base64Data = imageBase64;
    let detectedMime = mimeType || 'image/jpeg';

    if (imageBase64.includes(';base64,')) {
      const parts = imageBase64.split(';base64,');
      const mimeMatch = parts[0].match(/:(.*?)$/);
      if (mimeMatch) detectedMime = mimeMatch[1];
      base64Data = parts[1];
    }

    const { parsed, rawText } = await analyzeFiscalImage(base64Data, detectedMime);

    return res.json({
      success: true,
      extracted: parsed,
      raw_json: rawText,
    });
  } catch (error: any) {
    let userMsg = error.message || 'Falha ao processar e extrair dados da imagem fiscal.';
    try {
      if (typeof userMsg === 'string' && (userMsg.includes('503') || userMsg.includes('UNAVAILABLE') || userMsg.includes('high demand'))) {
        userMsg = 'O serviço de inteligência fiscal está momentaneamente com alta demanda na API Gemini. Por favor, tente novamente em alguns instantes.';
      }
    } catch (_) {}

    return res.status(500).json({
      success: false,
      error: userMsg,
    });
  }
});

// Telegram Deduplication Set for Webhook updates
const processedUpdateIds = new Set<number>();

// Telegram Webhook Endpoint (compatible with user's Python FastAPI Telegram Webhook)
app.post('/webhook', async (req: Request, res: Response) => {
  const logId = 'log-' + Date.now();
  try {
    const update = req.body;
    const updateId = update?.update_id;

    if (updateId) {
      if (processedUpdateIds.has(updateId)) {
        console.log(`Update ${updateId} duplicado ignorado.`);
        return res.status(200).json({ status: 'ignored_duplicate_update', update_id: updateId });
      }
      processedUpdateIds.add(updateId);
      if (processedUpdateIds.size > 1000) {
        const first = processedUpdateIds.values().next().value;
        if (first !== undefined) processedUpdateIds.delete(first);
      }
    }

    const message = update?.message || update?.channel_post;

    if (!message) {
      return res.status(200).json({ status: 'ignored_no_message' });
    }

    const chatId = message.chat?.id || 0;
    const messageId = message.message_id;

    // Process photo or direct base64 simulation
    let base64Data = req.body.simulated_image_base64;
    let mimeType = 'image/jpeg';

    if (message.photo && Array.isArray(message.photo) && !base64Data) {
      // Real Telegram bot would download via Telegram API token
      // If simulated or token provided, process
      console.log(`Telegram webhook received photo from chat ${chatId}`);
    }

    if (base64Data) {
      if (base64Data.includes(';base64,')) {
        const parts = base64Data.split(';base64,');
        const mimeMatch = parts[0].match(/:(.*?)$/);
        if (mimeMatch) mimeType = mimeMatch[1];
        base64Data = parts[1];
      }

      const { parsed, rawText } = await analyzeFiscalImage(base64Data, mimeType);

      // Verificação de legibilidade do comprovante
      if (parsed.status_leitura === 'ilegivel') {
        const mensagemUsuario = parsed.mensagem_erro || 'Não foi possível ler a foto. Envie uma foto mais nítida.';
        webhookLogs.unshift({
          id: logId,
          timestamp: new Date().toISOString(),
          chat_id: chatId,
          origem: 'Telegram Webhook',
          payload_summary: `Foto ilegível rejeitada: ${mensagemUsuario}`,
          status: 'erro',
          extracted_data: parsed,
          error_message: mensagemUsuario,
        });

        return res.status(200).json({
          status: 'ok',
          telegram_reply: `⚠️ ${mensagemUsuario}`,
          is_ilegivel: true,
        });
      }

      // Verificação de duplicidade (Data, Estabelecimento e Valor)
      const isDuplicado = fiscalEntries.slice(0, 20).some((entry) => {
        const dataNova = (parsed.data || '').trim();
        const dataExistente = (entry.data || '').trim();
        const estabNovo = (parsed.estabelecimento || '').trim().toLowerCase();
        const estabExistente = (entry.estabelecimento || '').trim().toLowerCase();
        const valorNovo = Number(parsed.valor) || 0;
        const valorExistente = Number(entry.valor) || 0;

        return (
          dataNova === dataExistente &&
          estabNovo === estabExistente &&
          Math.abs(valorNovo - valorExistente) < 0.01
        );
      });

      if (isDuplicado) {
        const alertaDuplicado =
          `⚠️ *Atenção: Comprovante Duplicado Detectado!*\n\n` +
          `Já existe um registro recente para *${parsed.estabelecimento}* no valor de *R$ ${Number(parsed.valor).toFixed(2)}* na data *${parsed.data}*.\n\n` +
          `O lançamento foi ignorado para evitar duplicidade na planilha.`;

        webhookLogs.unshift({
          id: logId,
          timestamp: new Date().toISOString(),
          chat_id: chatId,
          origem: 'Telegram Webhook',
          payload_summary: `Ignorado (Duplicado): ${parsed.estabelecimento} - R$ ${parsed.valor.toFixed(2)}`,
          status: 'erro',
          extracted_data: parsed,
          error_message: 'Comprovante idêntico já cadastrado recentemente',
        });

        return res.status(200).json({
          status: 'ok',
          telegram_reply: alertaDuplicado,
          is_duplicado: true,
        });
      }

      // Create new fiscal entry matching user's append_to_sheet pipeline
      const newEntry: StoredFiscalEntry = {
        id: 'doc-' + Date.now(),
        tipo_documento: parsed.tipo_documento,
        data: parsed.data,
        estabelecimento: parsed.estabelecimento,
        valor: parsed.valor,
        categoria: parsed.categoria,
        pagamento: parsed.pagamento,
        cnpj: parsed.cnpj,
        itens: parsed.itens,
        status_auditoria: 'auditado',
        audit_notes: `Lançamento automático via Telegram Webhook (Chat ID: ${chatId})`,
        origem: 'telegram_webhook',
        criado_em: new Date().toISOString(),
        raw_json: rawText,
      };

      fiscalEntries.unshift(newEntry);

      webhookLogs.unshift({
        id: logId,
        timestamp: new Date().toISOString(),
        chat_id: chatId,
        origem: 'Telegram Webhook',
        payload_summary: `Foto processada com sucesso: ${parsed.estabelecimento} - R$ ${parsed.valor.toFixed(2)}`,
        status: 'sucesso',
        extracted_data: parsed,
      });

      const confirmationText = 
        `✅ *Lançamento Registrado com Sucesso!*\n\n` +
        `• *Data:* ${parsed.data}\n` +
        `• *Estabelecimento:* ${parsed.estabelecimento}\n` +
        `• *Documento:* ${parsed.tipo_documento}\n` +
        `• *Categoria:* ${parsed.categoria}\n` +
        `• *Pagamento:* ${parsed.pagamento}\n` +
        `• *Valor:* R$ ${Number(parsed.valor).toFixed(2)}`;

      return res.status(200).json({
        status: 'ok',
        telegram_reply: confirmationText,
        entry: newEntry,
      });
    }

    // Default 200 OK acknowledgment
    webhookLogs.unshift({
      id: logId,
      timestamp: new Date().toISOString(),
      chat_id: chatId,
      origem: 'Telegram Webhook',
      payload_summary: 'Webhook recebido (ping / texto)',
      status: 'sucesso',
    });

    return res.status(200).json({ status: 'ok', received: true });
  } catch (error: any) {
    console.error('Erro no webhook:', error);
    webhookLogs.unshift({
      id: logId,
      timestamp: new Date().toISOString(),
      chat_id: req.body?.message?.chat?.id || 0,
      origem: 'Telegram Webhook',
      payload_summary: 'Falha no processamento',
      status: 'erro',
      error_message: error.message,
    });
    return res.status(200).json({ status: 'error_handled', error: error.message });
  }
});

// Entries CRUD
app.get('/api/entries', (_req: Request, res: Response) => {
  res.json(fiscalEntries);
});

app.post('/api/entries', (req: Request, res: Response) => {
  const newEntry: StoredFiscalEntry = {
    id: 'doc-' + Date.now(),
    tipo_documento: req.body.tipo_documento || 'Nota Fiscal',
    data: req.body.data || 'Não Informado',
    estabelecimento: req.body.estabelecimento || 'Não Informado',
    valor: Number(req.body.valor) || 0.0,
    categoria: req.body.categoria || 'Outros',
    pagamento: req.body.pagamento || 'Não Informado',
    cnpj: req.body.cnpj,
    itens: req.body.itens || [],
    status_auditoria: req.body.status_auditoria || 'auditado',
    audit_notes: req.body.audit_notes || '',
    imagem_url: req.body.imagem_url,
    raw_json: req.body.raw_json,
    origem: req.body.origem || 'upload',
    criado_em: new Date().toISOString(),
  };

  fiscalEntries.unshift(newEntry);
  res.status(201).json(newEntry);
});

app.patch('/api/entries/:id', (req: Request, res: Response) => {
  const { id } = req.params;
  const index = fiscalEntries.findIndex((e) => e.id === id);
  if (index === -1) {
    return res.status(404).json({ error: 'Comprovante não encontrado' });
  }

  fiscalEntries[index] = {
    ...fiscalEntries[index],
    ...req.body,
  };

  res.json(fiscalEntries[index]);
});

app.delete('/api/entries/:id', (req: Request, res: Response) => {
  const { id } = req.params;
  const initialLength = fiscalEntries.length;
  fiscalEntries = fiscalEntries.filter((e) => e.id !== id);

  if (fiscalEntries.length === initialLength) {
    return res.status(404).json({ error: 'Comprovante não encontrado' });
  }

  res.json({ success: true, id });
});

// Webhook Logs
app.get('/api/logs', (_req: Request, res: Response) => {
  res.json(webhookLogs);
});

// Export CSV Endpoint (Formatted for Google Sheets / Excel PT-BR)
app.get('/api/export/csv', (_req: Request, res: Response) => {
  // Brazilian standard: Semicolon separator, UTF-8 BOM
  let csvContent = '\uFEFF';
  csvContent += 'Data;Estabelecimento;Tipo de Documento;Categoria;Forma de Pagamento;Valor (R$);Status Auditoria;Observações\n';

  fiscalEntries.forEach((entry) => {
    const row = [
      `"${entry.data.replace(/"/g, '""')}"`,
      `"${entry.estabelecimento.replace(/"/g, '""')}"`,
      `"${entry.tipo_documento.replace(/"/g, '""')}"`,
      `"${entry.categoria.replace(/"/g, '""')}"`,
      `"${entry.pagamento.replace(/"/g, '""')}"`,
      entry.valor.toFixed(2).replace('.', ','),
      `"${entry.status_auditoria}"`,
      `"${(entry.audit_notes || '').replace(/"/g, '""')}"`,
    ];
    csvContent += row.join(';') + '\n';
  });

  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', 'attachment; filename="auditoria_fiscal_extrato.csv"');
  res.send(csvContent);
});

// Vite middleware / Static file serving
async function setupServer() {
  const isProduction = process.env.NODE_ENV === 'production';

  if (!isProduction) {
    const { createServer } = await import('vite');
    const vite = await createServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (_req: Request, res: Response) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(port, () => {
    console.log(`Server running at http://0.0.0.0:${port}`);
  });
}

setupServer().catch((err) => {
  console.error('Failed to start server:', err);
});
