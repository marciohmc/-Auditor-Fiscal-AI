import React, { useState, useMemo } from 'react';
import {
  Search,
  Filter,
  Download,
  Copy,
  Check,
  Trash2,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  Clock,
  ArrowUpDown,
  FileSpreadsheet
} from 'lucide-react';
import { FiscalEntry, StatusAuditoria } from '../types/finance';

interface LedgerTabProps {
  entries: FiscalEntry[];
  onDeleteEntry: (id: string) => void;
  onUpdateStatus: (id: string, newStatus: StatusAuditoria) => void;
  onViewDocument: (entry: FiscalEntry) => void;
  onNewScan: () => void;
}

export const LedgerTab: React.FC<LedgerTabProps> = ({
  entries,
  onDeleteEntry,
  onUpdateStatus,
  onViewDocument,
  onNewScan,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedTipo, setSelectedTipo] = useState<string>('all');
  const [selectedPayment, setSelectedPayment] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [sortField, setSortField] = useState<'data' | 'valor' | 'estabelecimento'>('data');
  const [sortAsc, setSortAsc] = useState(false);
  const [copiedAllJson, setCopiedAllJson] = useState(false);

  // Filtered and sorted entries
  const filteredEntries = useMemo(() => {
    return entries.filter((entry) => {
      const matchSearch =
        entry.estabelecimento.toLowerCase().includes(searchTerm.toLowerCase()) ||
        entry.categoria.toLowerCase().includes(searchTerm.toLowerCase()) ||
        entry.tipo_documento.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (entry.itens && entry.itens.some((i) => i.descricao.toLowerCase().includes(searchTerm.toLowerCase())));

      const matchCategory = selectedCategory === 'all' || entry.categoria === selectedCategory;
      const matchTipo = selectedTipo === 'all' || entry.tipo_documento === selectedTipo;
      const matchPayment = selectedPayment === 'all' || entry.pagamento === selectedPayment;
      const matchStatus = selectedStatus === 'all' || entry.status_auditoria === selectedStatus;

      return matchSearch && matchCategory && matchTipo && matchPayment && matchStatus;
    }).sort((a, b) => {
      if (sortField === 'valor') {
        return sortAsc ? a.valor - b.valor : b.valor - a.valor;
      }
      if (sortField === 'estabelecimento') {
        return sortAsc
          ? a.estabelecimento.localeCompare(b.estabelecimento)
          : b.estabelecimento.localeCompare(a.estabelecimento);
      }
      // default: data
      return sortAsc
        ? a.criado_em.localeCompare(b.criado_em)
        : b.criado_em.localeCompare(a.criado_em);
    });
  }, [entries, searchTerm, selectedCategory, selectedTipo, selectedPayment, selectedStatus, sortField, sortAsc]);

  const totalValor = useMemo(() => {
    return filteredEntries.reduce((acc, curr) => acc + curr.valor, 0);
  }, [filteredEntries]);

  const handleExportCSV = () => {
    window.location.href = '/api/export/csv';
  };

  const handleCopyAllJSON = () => {
    const jsonOutput = JSON.stringify(
      filteredEntries.map((e) => ({
        tipo_documento: e.tipo_documento,
        data: e.data,
        estabelecimento: e.estabelecimento,
        valor: e.valor,
        categoria: e.categoria,
        pagamento: e.pagamento,
      })),
      null,
      2
    );
    navigator.clipboard.writeText(jsonOutput);
    setCopiedAllJson(true);
    setTimeout(() => setCopiedAllJson(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header & KPI Summary */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight font-sans">
              Extrato Contábil & Auditoria Fiscal
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              Registro estruturado de notas fiscais, cupons e recibos processados pelo sistema
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleExportCSV}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors flex items-center gap-1.5 shadow-2xs"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
              <span>Exportar Planilha (CSV)</span>
            </button>
            <button
              onClick={handleCopyAllJSON}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors flex items-center gap-1.5 shadow-2xs"
            >
              {copiedAllJson ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-emerald-600">Copiado!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-slate-500" />
                  <span>Copiar JSON</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Aggregate KPI Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4">
          <div>
            <span className="text-xs text-slate-500 font-medium">Total Filtrado</span>
            <div className="text-xl font-bold font-mono tabular-nums text-slate-900 mt-0.5">
              R$ {totalValor.toFixed(2)}
            </div>
          </div>
          <div>
            <span className="text-xs text-slate-500 font-medium">Comprovantes</span>
            <div className="text-xl font-bold font-mono tabular-nums text-slate-900 mt-0.5">
              {filteredEntries.length} de {entries.length}
            </div>
          </div>
          <div>
            <span className="text-xs text-slate-500 font-medium">Ticket Médio</span>
            <div className="text-xl font-bold font-mono tabular-nums text-slate-900 mt-0.5">
              R$ {filteredEntries.length > 0 ? (totalValor / filteredEntries.length).toFixed(2) : '0.00'}
            </div>
          </div>
          <div>
            <span className="text-xs text-slate-500 font-medium">Status de Auditoria</span>
            <div className="text-sm font-semibold text-emerald-700 mt-1 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>
                {entries.filter((e) => e.status_auditoria === 'auditado').length} auditados
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-3">
        <div className="flex flex-col md:flex-row gap-3">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Buscar por estabelecimento, produto ou palavra-chave..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 outline-hidden transition-colors"
            />
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Categoria */}
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-2 text-slate-700 focus:ring-1 focus:ring-emerald-500 outline-hidden"
            >
              <option value="all">Todas Categorias</option>
              <option value="Alimentação">Alimentação</option>
              <option value="Transporte">Transporte</option>
              <option value="Saúde">Saúde</option>
              <option value="Lazer">Lazer</option>
              <option value="Moradia">Moradia</option>
              <option value="Veículo">Veículo</option>
              <option value="Educação">Educação</option>
              <option value="Outros">Outros</option>
            </select>

            {/* Tipo Documental */}
            <select
              value={selectedTipo}
              onChange={(e) => setSelectedTipo(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-2 text-slate-700 focus:ring-1 focus:ring-emerald-500 outline-hidden"
            >
              <option value="all">Todos Tipos</option>
              <option value="Cupom Fiscal">Cupom Fiscal</option>
              <option value="Nota Fiscal">Nota Fiscal</option>
              <option value="Recibo">Recibo</option>
            </select>

            {/* Pagamento */}
            <select
              value={selectedPayment}
              onChange={(e) => setSelectedPayment(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-2 text-slate-700 focus:ring-1 focus:ring-emerald-500 outline-hidden"
            >
              <option value="all">Formas de Pagamento</option>
              <option value="PIX">PIX</option>
              <option value="Cartão de Crédito">Cartão de Crédito</option>
              <option value="Cartão de Débito">Cartão de Débito</option>
              <option value="Dinheiro">Dinheiro</option>
              <option value="Boleto">Boleto</option>
            </select>

            {/* Status Auditoria */}
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-2 text-slate-700 focus:ring-1 focus:ring-emerald-500 outline-hidden"
            >
              <option value="all">Todos Status</option>
              <option value="auditado">Auditado</option>
              <option value="pendente">Pendente</option>
              <option value="divergencia">Divergência</option>
            </select>
          </div>
        </div>
      </div>

      {/* High-Density Data Table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        {filteredEntries.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <div className="w-12 h-12 mx-auto rounded-full bg-slate-100 text-slate-400 flex items-center justify-center">
              <Filter className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-800">
              Nenhum comprovante fiscal encontrado
            </h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Nenhum lançamento corresponde aos filtros ativos ou à pesquisa digitada.
            </p>
            <button
              onClick={onNewScan}
              className="mt-2 px-4 py-2 text-xs font-semibold text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 transition-colors"
            >
              Escanear Novo Comprovante
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold tracking-wider uppercase text-[11px]">
                  <th
                    className="py-3 px-4 cursor-pointer hover:text-slate-900"
                    onClick={() => {
                      setSortField('data');
                      setSortAsc(!sortAsc);
                    }}
                  >
                    <div className="flex items-center gap-1">
                      <span>Data</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th
                    className="py-3 px-4 cursor-pointer hover:text-slate-900"
                    onClick={() => {
                      setSortField('estabelecimento');
                      setSortAsc(!sortAsc);
                    }}
                  >
                    <div className="flex items-center gap-1">
                      <span>Estabelecimento</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th className="py-3 px-4">Tipo</th>
                  <th className="py-3 px-4">Categoria</th>
                  <th className="py-3 px-4">Pagamento</th>
                  <th
                    className="py-3 px-4 text-right cursor-pointer hover:text-slate-900"
                    onClick={() => {
                      setSortField('valor');
                      setSortAsc(!sortAsc);
                    }}
                  >
                    <div className="flex items-center justify-end gap-1">
                      <span>Valor (R$)</span>
                      <ArrowUpDown className="w-3 h-3" />
                    </div>
                  </th>
                  <th className="py-3 px-4 text-center">Auditoria</th>
                  <th className="py-3 px-4 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredEntries.map((entry) => (
                  <tr
                    key={entry.id}
                    className="hover:bg-slate-50/80 transition-colors group"
                  >
                    {/* Data */}
                    <td className="py-3.5 px-4 font-mono tabular-nums text-slate-700 whitespace-nowrap">
                      {entry.data}
                    </td>

                    {/* Estabelecimento */}
                    <td className="py-3.5 px-4 max-w-[240px]">
                      <div className="font-semibold text-slate-900 truncate">
                        {entry.estabelecimento}
                      </div>
                      {entry.pagador ? (
                        <div className="text-[10px] text-indigo-700 font-medium truncate mt-0.5">
                          Pagador: {entry.pagador}
                        </div>
                      ) : entry.responsavel ? (
                        <div className="text-[10px] text-slate-500 font-normal truncate mt-0.5">
                          Resp: {entry.responsavel}
                        </div>
                      ) : null}
                    </td>

                    {/* Tipo Documento */}
                    <td className="py-3.5 px-4 whitespace-nowrap text-slate-600">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-slate-700 font-medium">{entry.tipo_documento}</span>
                        {entry.itens && entry.itens.length > 0 && (
                          <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.2 rounded w-max">
                            <span>📦 {entry.itens.length} {entry.itens.length === 1 ? 'item' : 'itens'}</span>
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Categoria */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <span className="text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-medium">
                        {entry.categoria}
                      </span>
                    </td>

                    {/* Pagamento */}
                    <td className="py-3.5 px-4 whitespace-nowrap text-slate-600">
                      {entry.pagamento}
                    </td>

                    {/* Valor */}
                    <td className="py-3.5 px-4 text-right font-mono font-bold tabular-nums text-slate-900 whitespace-nowrap">
                      R$ {entry.valor.toFixed(2)}
                    </td>

                    {/* Status de Auditoria */}
                    <td className="py-3.5 px-4 text-center whitespace-nowrap">
                      {entry.status_auditoria === 'auditado' && (
                        <button
                          onClick={() => onUpdateStatus(entry.id, 'pendente')}
                          title="Clique para alternar para Pendente"
                          className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full hover:bg-emerald-100 transition-colors"
                        >
                          <ShieldCheck className="w-3 h-3 text-emerald-600" />
                          <span>Auditado</span>
                        </button>
                      )}
                      {entry.status_auditoria === 'pendente' && (
                        <button
                          onClick={() => onUpdateStatus(entry.id, 'auditado')}
                          title="Clique para aprovar auditoria"
                          className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full hover:bg-amber-100 transition-colors"
                        >
                          <Clock className="w-3 h-3 text-amber-600" />
                          <span>Pendente</span>
                        </button>
                      )}
                      {entry.status_auditoria === 'divergencia' && (
                        <button
                          onClick={() => onUpdateStatus(entry.id, 'auditado')}
                          className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded-full hover:bg-rose-100 transition-colors"
                        >
                          <AlertTriangle className="w-3 h-3 text-rose-600" />
                          <span>Divergência</span>
                        </button>
                      )}
                    </td>

                    {/* Ações */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => onViewDocument(entry)}
                          className="px-2.5 py-1 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-emerald-50 hover:text-emerald-700 border border-slate-200 rounded-lg transition-colors flex items-center gap-1"
                          title="Detalhes e Itens Discriminados"
                        >
                          <ExternalLink className="w-3 h-3 text-emerald-600" />
                          <span>Detalhes</span>
                        </button>
                        <button
                          onClick={() => onDeleteEntry(entry.id)}
                          className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors"
                          title="Excluir Lançamento"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Table footer with stats */}
        <div className="p-3 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
          <span>Mostrando {filteredEntries.length} comprovantes auditados</span>
          <span className="font-mono tabular-nums font-semibold text-slate-800">
            Soma dos Valores: R$ {totalValor.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
};
