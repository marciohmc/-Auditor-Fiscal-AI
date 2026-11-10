import React, { useState } from 'react';
import {
  X,
  ShieldCheck,
  Calendar,
  Building,
  CreditCard,
  Tag,
  DollarSign,
  Copy,
  Check,
  AlertTriangle,
  Clock,
  FileText,
  ShoppingBag
} from 'lucide-react';
import { FiscalEntry, StatusAuditoria } from '../types/finance';

interface DocumentModalProps {
  entry: FiscalEntry | null;
  onClose: () => void;
  onUpdateStatus: (id: string, status: StatusAuditoria, notes?: string) => void;
}

export const DocumentModal: React.FC<DocumentModalProps> = ({
  entry,
  onClose,
  onUpdateStatus,
}) => {
  if (!entry) return null;

  const [copied, setCopied] = useState(false);
  const [auditNotes, setAuditNotes] = useState(entry.audit_notes || '');
  const [selectedStatus, setSelectedStatus] = useState<StatusAuditoria>(entry.status_auditoria);

  const handleCopyJSON = () => {
    const jsonStr = entry.raw_json || JSON.stringify({
      tipo_documento: entry.tipo_documento,
      data: entry.data,
      estabelecimento: entry.estabelecimento,
      valor: entry.valor,
      categoria: entry.categoria,
      pagamento: entry.pagamento,
    }, null, 2);

    navigator.clipboard.writeText(jsonStr);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveAudit = () => {
    onUpdateStatus(entry.id, selectedStatus, auditNotes);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-3xl overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-600 text-white flex items-center justify-center font-bold text-xs">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 font-sans">
                {entry.estabelecimento}
              </h2>
              <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
                <span>{entry.tipo_documento}</span>
                <span>·</span>
                <span className="tabular-nums">{entry.data}</span>
                <span>·</span>
                <span className="capitalize text-slate-600">Origem: {entry.origem}</span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-xs">
          {/* Top highlight card */}
          <div className="p-4 bg-slate-900 text-white rounded-xl flex items-center justify-between">
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Valor Total Contábil
              </span>
              <div className="text-2xl font-bold font-mono tabular-nums mt-0.5 text-emerald-400">
                R$ {entry.valor.toFixed(2)}
              </div>
            </div>
            <div className="text-right">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Forma de Pagamento
              </span>
              <div className="text-sm font-semibold text-slate-200 mt-0.5">
                {entry.pagamento}
              </div>
            </div>
          </div>

          {/* Image & Key Fields */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left: Image or document placeholder */}
            <div className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50 flex items-center justify-center min-h-[220px]">
              {entry.imagem_url ? (
                <img
                  src={entry.imagem_url}
                  alt={entry.estabelecimento}
                  className="max-h-[260px] w-auto object-contain p-2"
                />
              ) : (
                <div className="text-center p-6 text-slate-400 space-y-2">
                  <FileText className="w-8 h-8 mx-auto text-slate-300" />
                  <p className="text-xs">Registro fiscal importado via integração</p>
                  <span className="text-[11px] font-mono text-slate-400">
                    ID: {entry.id}
                  </span>
                </div>
              )}
            </div>

            {/* Right: Key Details */}
            <div className="space-y-3">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-slate-400 block font-medium">Categoria</span>
                <span className="text-sm font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded inline-block mt-1">
                  {entry.categoria}
                </span>
              </div>

              {entry.pagador && (
                <div className="p-3 bg-indigo-50/60 rounded-lg border border-indigo-100">
                  <span className="text-indigo-600 block font-semibold text-[11px] uppercase tracking-wider">
                    Quem emitiu (Pagador Pix)
                  </span>
                  <span className="text-xs font-semibold text-indigo-950 mt-0.5 block">
                    {entry.pagador}
                    {entry.doc_pagador ? ` (${entry.doc_pagador})` : ''}
                  </span>
                </div>
              )}

              {entry.responsavel && (
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <span className="text-slate-400 block font-medium">Responsável na Planilha</span>
                  <span className="text-xs font-semibold text-slate-800 mt-0.5 block">
                    {entry.responsavel}
                  </span>
                </div>
              )}

              {entry.cnpj && (
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <span className="text-slate-400 block font-medium">CNPJ do Emissor</span>
                  <span className="text-xs font-mono font-semibold text-slate-800 mt-0.5 block tabular-nums">
                    {entry.cnpj}
                  </span>
                </div>
              )}

              {/* Audit Status Setting */}
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-2">
                <span className="text-slate-500 font-semibold block">
                  Status de Auditoria Contábil
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedStatus('auditado')}
                    className={`py-1.5 px-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1 border transition-colors ${
                      selectedStatus === 'auditado'
                        ? 'bg-emerald-600 text-white border-emerald-600'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Auditado</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedStatus('pendente')}
                    className={`py-1.5 px-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1 border transition-colors ${
                      selectedStatus === 'pendente'
                        ? 'bg-amber-600 text-white border-amber-600'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5" />
                    <span>Pendente</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedStatus('divergencia')}
                    className={`py-1.5 px-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1 border transition-colors ${
                      selectedStatus === 'divergencia'
                        ? 'bg-rose-600 text-white border-rose-600'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>Divergência</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Detailed items list - DADOS DO PRODUTO / SERVIÇOS */}
          <div className="border border-slate-200 rounded-xl p-3.5 bg-slate-50/80 space-y-2.5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-2">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                <ShoppingBag className="w-4 h-4 text-emerald-600" />
                <span>DADOS DO PRODUTO / SERVIÇOS — Itens Comprados / Discriminados na Nota</span>
              </h4>
              <div className="flex items-center gap-1.5 text-[11px]">
                <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-medium border border-emerald-200 flex items-center gap-1">
                  <span>Aba Planilha:</span>
                  <span className="font-mono font-bold">Produtos_{(entry.data || '').split('/')[1] || '11'}_{ (entry.data || '').split('/')[2] || '2026'}</span>
                </span>
              </div>
            </div>

            {entry.itens && entry.itens.length > 0 ? (
              <div className="overflow-x-auto max-h-[220px] overflow-y-auto border border-slate-200 rounded-lg bg-white shadow-2xs">
                <table className="w-full text-left text-[11px]">
                  <thead className="bg-slate-100 text-slate-700 font-semibold sticky top-0 border-b border-slate-200">
                    <tr>
                      <th className="py-2 px-2.5 w-8 text-center">#</th>
                      <th className="py-2 px-2.5">Descrição do Produto / Serviço</th>
                      <th className="py-2 px-2.5 text-center w-14">Qtd</th>
                      <th className="py-2 px-2.5 text-right w-24">Vlr Unit. (R$)</th>
                      <th className="py-2 px-2.5 text-right w-28">Vlr Total (R$)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-sans">
                    {entry.itens.map((item, idx) => {
                      const vUnit = item.valor_unitario ?? (item.valor_total / (item.quantidade || 1));
                      return (
                        <tr key={idx} className="hover:bg-slate-50 transition-colors">
                          <td className="py-2 px-2.5 font-mono text-slate-400 text-center">{idx + 1}</td>
                          <td className="py-2 px-2.5 font-semibold text-slate-900">{item.descricao}</td>
                          <td className="py-2 px-2.5 text-center font-mono text-slate-600">{item.quantidade}</td>
                          <td className="py-2 px-2.5 text-right font-mono text-slate-600">
                            R$ {vUnit.toFixed(2)}
                          </td>
                          <td className="py-2 px-2.5 text-right font-mono font-bold text-slate-900">
                            R$ {item.valor_total.toFixed(2)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot className="bg-slate-50 font-bold border-t border-slate-200">
                    <tr>
                      <td colSpan={4} className="py-2 px-2.5 text-right text-slate-700">Total dos Itens:</td>
                      <td className="py-2 px-2.5 text-right font-mono text-emerald-700">
                        R$ {entry.itens.reduce((acc, i) => acc + (i.valor_total || 0), 0).toFixed(2)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : (
              <div className="p-4 bg-white border border-dashed border-slate-300 rounded-lg text-center space-y-1">
                <p className="text-slate-600 font-medium text-xs">Nenhum item individual discriminado no documento original.</p>
                <p className="text-[11px] text-slate-400">
                  Os valores consolidados da Nota Fiscal foram registrados na aba principal de extrato, com resumo vinculado à aba mensal de produtos.
                </p>
              </div>
            )}
          </div>

          {/* Audit Notes Input */}
          <div className="space-y-1.5">
            <label className="font-semibold text-slate-700 block">
              Observações e Parecer de Auditoria
            </label>
            <textarea
              value={auditNotes}
              onChange={(e) => setAuditNotes(e.target.value)}
              placeholder="Digite notas fiscais, conferência de extrato ou justificativa de despesa..."
              rows={2}
              className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-emerald-500 outline-hidden"
            />
          </div>

          {/* Raw JSON View */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">JSON Estruturado Oficial</span>
              <button
                onClick={handleCopyJSON}
                className="text-xs text-slate-600 hover:text-slate-900 flex items-center gap-1"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                    <span className="text-emerald-600 font-medium">Copiado</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copiar JSON</span>
                  </>
                )}
              </button>
            </div>
            <pre className="p-3 bg-slate-950 text-emerald-400 font-mono text-xs rounded-lg overflow-x-auto border border-slate-800 max-h-[120px]">
              {entry.raw_json || JSON.stringify(entry, null, 2)}
            </pre>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg hover:bg-slate-100 transition-colors"
          >
            Fechar
          </button>
          <button
            onClick={handleSaveAudit}
            className="px-4 py-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors shadow-xs"
          >
            Salvar Parecer de Auditoria
          </button>
        </div>
      </div>
    </div>
  );
};
