import React, { useState, useRef } from 'react';
import {
  Upload,
  Camera,
  FileText,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  RefreshCw,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Building,
  Calendar,
  CreditCard,
  Tag,
  DollarSign,
  ChevronRight
} from 'lucide-react';
import { ExtractedFiscalData, FiscalEntry } from '../types/finance';
import { SAMPLE_VOUCHERS, generateVoucherCanvasDataUrl, SampleVoucher } from '../utils/sampleVouchers';

interface ScannerTabProps {
  onEntrySaved: (entry: FiscalEntry) => void;
}

export const ScannerTab: React.FC<ScannerTabProps> = ({ onEntrySaved }) => {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractedData, setExtractedData] = useState<ExtractedFiscalData | null>(null);
  const [rawJson, setRawJson] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copiedJson, setCopiedJson] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [activeSampleId, setActiveSampleId] = useState<string | null>(null);

  // Editable fields when auditor wants to adjust
  const [editableEstabelecimento, setEditableEstabelecimento] = useState('');
  const [editableValor, setEditableValor] = useState<number>(0);
  const [editableData, setEditableData] = useState('');
  const [editableCategoria, setEditableCategoria] = useState<string>('Outros');
  const [editablePagamento, setEditablePagamento] = useState<string>('Não Informado');
  const [editableTipo, setEditableTipo] = useState<string>('Nota Fiscal');
  const [isEditing, setIsEditing] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = (file: File) => {
    if (!file.type.startsWith('image/')) {
      setErrorMessage('Por favor, selecione um arquivo de imagem válido (PNG, JPG, JPEG, WEBP).');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const base64 = e.target?.result as string;
      setSelectedImage(base64);
      setActiveSampleId(null);
      setExtractedData(null);
      setErrorMessage(null);
      setSavedSuccess(false);
      extractDataFromImage(base64, file.type);
    };
    reader.readAsDataURL(file);
  };

  const handleSampleSelect = (voucher: SampleVoucher) => {
    setActiveSampleId(voucher.id);
    const dataUrl = generateVoucherCanvasDataUrl(voucher);
    setSelectedImage(dataUrl);
    setExtractedData(null);
    setErrorMessage(null);
    setSavedSuccess(false);
    extractDataFromImage(dataUrl, 'image/jpeg');
  };

  const extractDataFromImage = async (imageBase64: string, mimeType: string) => {
    setIsExtracting(true);
    setErrorMessage(null);

    try {
      const response = await fetch('/api/extract', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          imageBase64,
          mimeType,
        }),
      });

      const result = await response.json();

      if (!response.ok || !result.success) {
        throw new Error(result.error || 'Erro ao processar a imagem do comprovante fiscal.');
      }

      if (result.extracted?.status_leitura === 'ilegivel') {
        setErrorMessage(
          result.extracted.mensagem_erro ||
            'Não consegui ler os dados com clareza pois a imagem está borrada ou muito escura. Poderia enviar uma foto mais nítida, por favor?'
        );
        setExtractedData(null);
        setRawJson(result.raw_json || JSON.stringify(result.extracted, null, 2));
        return;
      }

      setExtractedData(result.extracted);
      setRawJson(result.raw_json || JSON.stringify(result.extracted, null, 2));

      // Init editable fields
      setEditableEstabelecimento(result.extracted.estabelecimento || '');
      setEditableValor(result.extracted.valor || 0);
      setEditableData(result.extracted.data || '');
      setEditableCategoria(result.extracted.categoria || 'Outros');
      setEditablePagamento(result.extracted.pagamento || 'Não Informado');
      setEditableTipo(result.extracted.tipo_documento || 'Nota Fiscal');
    } catch (err: any) {
      console.error(err);
      setErrorMessage(err.message || 'Falha na conexão com o servidor de inteligência fiscal.');
    } finally {
      setIsExtracting(false);
    }
  };

  const handleSaveToLedger = async (statusAuditoria: 'auditado' | 'pendente' = 'auditado') => {
    if (!extractedData) return;

    const payload: Partial<FiscalEntry> = {
      tipo_documento: (isEditing ? editableTipo : extractedData.tipo_documento) as any,
      data: isEditing ? editableData : extractedData.data,
      estabelecimento: isEditing ? editableEstabelecimento : extractedData.estabelecimento,
      valor: isEditing ? Number(editableValor) : extractedData.valor,
      categoria: (isEditing ? editableCategoria : extractedData.categoria) as any,
      pagamento: (isEditing ? editablePagamento : extractedData.pagamento) as any,
      cnpj: extractedData.cnpj,
      itens: extractedData.itens || [],
      status_auditoria: statusAuditoria,
      audit_notes: statusAuditoria === 'auditado' 
        ? 'Auditado e verificado pelo assistente financeiro.' 
        : 'Pendente de validação de comprovante auxiliar.',
      origem: activeSampleId ? 'amostra' : 'upload',
      imagem_url: selectedImage || undefined,
      raw_json: rawJson,
    };

    try {
      const res = await fetch('/api/entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const saved = await res.json();
        onEntrySaved(saved);
        setSavedSuccess(true);
        setTimeout(() => setSavedSuccess(false), 4000);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(rawJson);
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  const resetAll = () => {
    setSelectedImage(null);
    setExtractedData(null);
    setRawJson('');
    setErrorMessage(null);
    setActiveSampleId(null);
    setIsEditing(false);
    setSavedSuccess(false);
  };

  return (
    <div className="space-y-6">
      {/* Introduction banner */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight font-sans">
              Extração Multimodal de Comprovantes Fiscais
            </h1>
            <p className="text-sm text-slate-600 mt-1 max-w-3xl">
              Envie fotos de Notas Fiscais (NFC-e / NF-e), Cupons Fiscais (SAT / ECF) ou Recibos. O assistente Gemini 3.8 Flash analisa visualmente os dados e retorna estritamente o JSON padronizado conforme as normas contábeis brasileiras.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-500 bg-slate-50 border border-slate-200 px-3 py-2 rounded-lg shrink-0">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>Gemini 3.8 Flash Ativo</span>
          </div>
        </div>
      </div>

      {/* Main interactive area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Upload / Image Inspector (lg:col-span-6) */}
        <div className="lg:col-span-6 space-y-4">
          {!selectedImage ? (
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-6">
              {/* Drag & Drop Box */}
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    handleFileUpload(e.dataTransfer.files[0]);
                  }
                }}
                className="border-2 border-dashed border-slate-200 hover:border-emerald-500 rounded-xl p-8 text-center transition-colors bg-slate-50/50 hover:bg-emerald-50/30 cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept="image/png, image/jpeg, image/jpg, image/webp"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileUpload(e.target.files[0]);
                    }
                  }}
                />
                <input
                  type="file"
                  ref={cameraInputRef}
                  className="hidden"
                  accept="image/*"
                  capture="environment"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileUpload(e.target.files[0]);
                    }
                  }}
                />

                <div className="w-12 h-12 mx-auto rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mb-4">
                  <Upload className="w-6 h-6" />
                </div>
                <h3 className="text-base font-semibold text-slate-900">
                  Arraste ou selecione a imagem do comprovante
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  Suporta Cupom Fiscal (SAT), Nota Fiscal (NFC-e/NF-e) ou Recibo em PNG, JPG ou WEBP
                </p>

                <div className="flex items-center justify-center gap-3 mt-5">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                    className="px-4 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors shadow-2xs"
                  >
                    Selecionar Arquivo
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      cameraInputRef.current?.click();
                    }}
                    className="px-4 py-2 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100 transition-colors flex items-center gap-1.5"
                  >
                    <Camera className="w-3.5 h-3.5" />
                    <span>Fotografar</span>
                  </button>
                </div>
              </div>

              {/* Instant Test Samples */}
              <div className="pt-2">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Amostras Oficiais Brasileiras para Teste Imediato
                  </h4>
                  <span className="text-xs text-slate-400">1 clique para extrair</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {SAMPLE_VOUCHERS.map((voucher) => (
                    <button
                      key={voucher.id}
                      onClick={() => handleSampleSelect(voucher)}
                      className="text-left p-3.5 rounded-lg border border-slate-200 hover:border-emerald-500 hover:bg-emerald-50/20 transition-all bg-white group flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-medium text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded">
                            {voucher.badge}
                          </span>
                          <span className="text-xs font-mono font-semibold text-slate-800 tabular-nums">
                            R$ {voucher.expectedValor.toFixed(2)}
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-slate-900 group-hover:text-emerald-700 transition-colors line-clamp-1">
                          {voucher.name}
                        </p>
                        <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">
                          {voucher.description}
                        </p>
                      </div>
                      <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                        <span>{voucher.data}</span>
                        <span className="text-emerald-600 font-medium group-hover:translate-x-0.5 transition-transform flex items-center gap-0.5">
                          Testar <ChevronRight className="w-3 h-3" />
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
              {/* Image Toolbar */}
              <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50/80">
                <div className="flex items-center gap-2 text-xs font-medium text-slate-700">
                  <FileText className="w-4 h-4 text-emerald-600" />
                  <span>Comprovante em Análise</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setZoomLevel((z) => Math.max(0.7, z - 0.2))}
                    className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 rounded"
                    title="Diminuir Zoom"
                  >
                    <ZoomOut className="w-4 h-4" />
                  </button>
                  <span className="text-xs font-mono text-slate-500 tabular-nums">
                    {Math.round(zoomLevel * 100)}%
                  </span>
                  <button
                    onClick={() => setZoomLevel((z) => Math.min(2.5, z + 0.2))}
                    className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 rounded"
                    title="Aumentar Zoom"
                  >
                    <ZoomIn className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setZoomLevel(1)}
                    className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 rounded"
                    title="Resetar Zoom"
                  >
                    <Maximize2 className="w-4 h-4" />
                  </button>
                  <div className="h-4 w-px bg-slate-200 mx-1"></div>
                  <button
                    onClick={resetAll}
                    className="px-2.5 py-1 text-xs text-rose-600 hover:bg-rose-50 rounded font-medium transition-colors"
                  >
                    Trocar Imagem
                  </button>
                </div>
              </div>

              {/* Image Viewport */}
              <div className="p-4 bg-slate-900/5 min-h-[420px] max-h-[560px] overflow-auto flex items-center justify-center">
                <div
                  style={{ transform: `scale(${zoomLevel})`, transformOrigin: 'center center' }}
                  className="transition-transform duration-150"
                >
                  <img
                    src={selectedImage}
                    alt="Comprovante Fiscal"
                    referrerPolicy="no-referrer"
                    className="max-h-[500px] w-auto object-contain rounded shadow-md border border-slate-200 bg-white"
                  />
                </div>
              </div>

              {/* Footer status */}
              <div className="p-3 border-t border-slate-200 bg-white flex items-center justify-between text-xs text-slate-500">
                <span>Resolução mantida para máxima precisão de OCR fiscal</span>
                {activeSampleId && (
                  <span className="text-emerald-700 font-medium">Amostra Fiscal Oficial Ativa</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Extracted Data & Strict JSON Card (lg:col-span-6) */}
        <div className="lg:col-span-6 space-y-4">
          {/* Loading state */}
          {isExtracting && (
            <div className="bg-white border border-slate-200 rounded-xl p-8 shadow-xs text-center space-y-4">
              <div className="w-12 h-12 mx-auto rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center animate-spin">
                <RefreshCw className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Auditando Comprovante com Gemini AI...
                </h3>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  Localizando estabelecimento, data DD/MM/AAAA, valor total líquido, categoria contábil e forma de pagamento.
                </p>
              </div>
              <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden max-w-xs mx-auto">
                <div className="bg-emerald-500 h-full w-2/3 animate-pulse rounded-full"></div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {errorMessage && !isExtracting && (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-5 text-rose-800 space-y-2">
              <div className="flex items-center gap-2 font-semibold text-sm">
                <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
                <span>Falha no Processamento Fiscal</span>
              </div>
              <p className="text-xs text-rose-700">{errorMessage}</p>
              <button
                onClick={() => {
                  if (selectedImage) extractDataFromImage(selectedImage, 'image/jpeg');
                }}
                className="mt-2 text-xs font-semibold px-3 py-1.5 bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors"
              >
                Tentar Novamente
              </button>
            </div>
          )}

          {/* Success Result View */}
          {extractedData && !isExtracting && (
            <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
              {/* Header */}
              <div className="px-5 py-4 border-b border-slate-200 bg-emerald-50/50 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-emerald-600 text-white flex items-center justify-center">
                    <CheckCircle2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">
                      Dados Fiscais Extraídos com Sucesso
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Classificação rigorosa em formato JSON padronizado
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setIsEditing(!isEditing)}
                    className="text-xs text-slate-600 hover:text-slate-900 font-medium px-2.5 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 transition-colors"
                  >
                    {isEditing ? 'Concluir Edição' : 'Ajustar Campos'}
                  </button>
                </div>
              </div>

              {/* Data Card Breakdown */}
              <div className="p-5 space-y-4">
                {/* Primary Financial Metric Banner */}
                <div className="p-4 bg-slate-900 text-white rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                      Valor Total Extraído
                    </span>
                    <div className="text-2xl font-bold font-mono tabular-nums text-white mt-0.5">
                      R$ {isEditing ? Number(editableValor || 0).toFixed(2) : extractedData.valor.toFixed(2)}
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                      Tipo Documental
                    </span>
                    <div className="text-sm font-semibold text-emerald-400 mt-0.5">
                      {isEditing ? editableTipo : extractedData.tipo_documento}
                    </div>
                  </div>
                </div>

                {/* Structured Fields Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-xs">
                  {/* Estabelecimento */}
                  <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/60">
                    <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                      <Building className="w-3.5 h-3.5" />
                      <span className="font-medium">Estabelecimento</span>
                    </div>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editableEstabelecimento}
                        onChange={(e) => setEditableEstabelecimento(e.target.value)}
                        className="w-full text-xs font-semibold text-slate-900 bg-white border border-slate-200 rounded px-2 py-1 focus:ring-1 focus:ring-emerald-500 outline-hidden"
                      />
                    ) : (
                      <p className="font-semibold text-slate-900 text-sm">
                        {extractedData.estabelecimento}
                      </p>
                    )}
                  </div>

                  {/* Data */}
                  <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/60">
                    <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                      <Calendar className="w-3.5 h-3.5" />
                      <span className="font-medium">Data de Emissão</span>
                    </div>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editableData}
                        onChange={(e) => setEditableData(e.target.value)}
                        placeholder="DD/MM/AAAA"
                        className="w-full text-xs font-mono font-semibold text-slate-900 bg-white border border-slate-200 rounded px-2 py-1 focus:ring-1 focus:ring-emerald-500 outline-hidden tabular-nums"
                      />
                    ) : (
                      <p className="font-mono font-semibold text-slate-900 text-sm tabular-nums">
                        {extractedData.data}
                      </p>
                    )}
                  </div>

                  {/* Categoria */}
                  <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/60">
                    <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                      <Tag className="w-3.5 h-3.5" />
                      <span className="font-medium">Categoria Contábil</span>
                    </div>
                    {isEditing ? (
                      <select
                        value={editableCategoria}
                        onChange={(e) => setEditableCategoria(e.target.value)}
                        className="w-full text-xs font-semibold text-slate-900 bg-white border border-slate-200 rounded px-2 py-1 focus:ring-1 focus:ring-emerald-500 outline-hidden"
                      >
                        {['Alimentação', 'Transporte', 'Saúde', 'Lazer', 'Moradia', 'Veículo', 'Educação', 'Outros'].map((cat) => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>
                    ) : (
                      <p className="font-semibold text-emerald-800 bg-emerald-50 inline-block px-2 py-0.5 rounded text-xs">
                        {extractedData.categoria}
                      </p>
                    )}
                  </div>

                  {/* Forma de Pagamento */}
                  <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/60">
                    <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                      <CreditCard className="w-3.5 h-3.5" />
                      <span className="font-medium">Forma de Pagamento</span>
                    </div>
                    {isEditing ? (
                      <select
                        value={editablePagamento}
                        onChange={(e) => setEditablePagamento(e.target.value)}
                        className="w-full text-xs font-semibold text-slate-900 bg-white border border-slate-200 rounded px-2 py-1 focus:ring-1 focus:ring-emerald-500 outline-hidden"
                      >
                        {['PIX', 'Cartão de Crédito', 'Cartão de Débito', 'Dinheiro', 'Boleto', 'Não Informado'].map((p) => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </select>
                    ) : (
                      <p className="font-semibold text-slate-900 text-sm">
                        {extractedData.pagamento}
                      </p>
                    )}
                  </div>
                </div>

                {/* Items breakdown if present */}
                {extractedData.itens && extractedData.itens.length > 0 && (
                  <div className="border border-slate-200 rounded-lg p-3 bg-slate-50/40">
                    <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                      Itens Identificados no Comprovante ({extractedData.itens.length})
                    </h4>
                    <div className="divide-y divide-slate-100 text-xs">
                      {extractedData.itens.map((item, idx) => (
                        <div key={idx} className="py-1.5 flex items-center justify-between">
                          <span className="text-slate-800 font-medium truncate max-w-[240px]">
                            {item.descricao}
                          </span>
                          <div className="flex items-center gap-3 font-mono tabular-nums text-slate-600">
                            <span>{item.quantidade}x</span>
                            <span className="font-semibold text-slate-900">
                              R$ {item.valor_total.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Strict JSON Output section with copy button */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Formato JSON Padronizado (Saída Estrita)</span>
                    </span>
                    <button
                      onClick={copyToClipboard}
                      className="text-xs text-slate-600 hover:text-slate-900 flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-100 transition-colors"
                    >
                      {copiedJson ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-600" />
                          <span className="text-emerald-600 font-medium">Copiado!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copiar JSON</span>
                        </>
                      )}
                    </button>
                  </div>

                  <pre className="p-3.5 bg-slate-950 text-emerald-400 font-mono text-xs rounded-lg overflow-x-auto border border-slate-800 leading-relaxed tabular-nums">
                    {rawJson}
                  </pre>
                </div>

                {/* Save Feedback */}
                {savedSuccess && (
                  <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 text-xs flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span className="font-medium">
                      Lançamento fiscal gravado com sucesso no Extrato Contábil!
                    </span>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
                  <button
                    onClick={() => handleSaveToLedger('auditado')}
                    className="w-full sm:w-auto flex-1 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-2 shadow-xs"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    <span>Salvar & Marcar como Auditado</span>
                  </button>

                  <button
                    onClick={() => handleSaveToLedger('pendente')}
                    className="w-full sm:w-auto px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors"
                  >
                    Salvar como Pendente
                  </button>

                  <button
                    onClick={resetAll}
                    className="w-full sm:w-auto px-3 py-2.5 text-slate-500 hover:text-slate-800 text-xs font-medium"
                  >
                    Novo Scanner
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Initial Helper Empty State */}
          {!selectedImage && !isExtracting && (
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-4">
              <h3 className="text-sm font-bold text-slate-900">
                Regras Estritas de Extração e Auditoria
              </h3>
              <div className="space-y-3 text-xs text-slate-600 leading-relaxed">
                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-100 text-slate-700 flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                    1
                  </div>
                  <div>
                    <strong className="text-slate-900">Classificação Documental:</strong> Identifica com precisão se o comprovante é <em>Nota Fiscal</em>, <em>Cupom Fiscal</em> ou <em>Recibo</em>.
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-100 text-slate-700 flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                    2
                  </div>
                  <div>
                    <strong className="text-slate-900">Categorização Padronizada:</strong> Mapeia em <em>Alimentação, Transporte, Saúde, Lazer, Moradia, Veículo, Educação</em> ou <em>Outros</em>.
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-100 text-slate-700 flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                    3
                  </div>
                  <div>
                    <strong className="text-slate-900">Detecção de Pagamento:</strong> Reconhece <em>PIX, Cartão de Crédito, Cartão de Débito, Dinheiro, Boleto</em> ou <em>Não Informado</em>.
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-100 text-slate-700 flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                    4
                  </div>
                  <div>
                    <strong className="text-slate-900">Formatação Numérica e Datas:</strong> Converte e valida valores em float (R$) e datas no padrão brasileiro DD/MM/AAAA.
                  </div>
                </div>
              </div>

              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 text-xs text-slate-500">
                💡 <strong>Dica do Auditor:</strong> Você pode clicar em qualquer uma das amostras ao lado para ver a extração em tempo real sem precisar tirar fotos de comprovantes físicos.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
