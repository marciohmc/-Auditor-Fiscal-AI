import React, { useMemo } from 'react';
import {
  TrendingUp,
  PieChart,
  CreditCard,
  FileCheck,
  Building,
  CheckCircle2,
  Clock,
  AlertTriangle
} from 'lucide-react';
import { FiscalEntry } from '../types/finance';

interface MetricsTabProps {
  entries: FiscalEntry[];
}

export const MetricsTab: React.FC<MetricsTabProps> = ({ entries }) => {
  const totalGasto = useMemo(() => {
    return entries.reduce((acc, curr) => acc + curr.valor, 0);
  }, [entries]);

  // Breakdown by Category
  const categoryStats = useMemo(() => {
    const map: Record<string, { total: number; count: number }> = {};
    const standardCats = ['Alimentação', 'Transporte', 'Saúde', 'Lazer', 'Moradia', 'Veículo', 'Educação', 'Outros'];
    standardCats.forEach((c) => {
      map[c] = { total: 0, count: 0 };
    });

    entries.forEach((entry) => {
      const cat = entry.categoria || 'Outros';
      if (!map[cat]) map[cat] = { total: 0, count: 0 };
      map[cat].total += entry.valor;
      map[cat].count += 1;
    });

    return Object.entries(map)
      .map(([categoria, stat]) => ({
        categoria,
        total: stat.total,
        count: stat.count,
        percentage: totalGasto > 0 ? (stat.total / totalGasto) * 100 : 0,
      }))
      .filter((s) => s.total > 0)
      .sort((a, b) => b.total - a.total);
  }, [entries, totalGasto]);

  // Breakdown by Payment Method
  const paymentStats = useMemo(() => {
    const map: Record<string, { total: number; count: number }> = {};
    entries.forEach((entry) => {
      const p = entry.pagamento || 'Não Informado';
      if (!map[p]) map[p] = { total: 0, count: 0 };
      map[p].total += entry.valor;
      map[p].count += 1;
    });

    return Object.entries(map)
      .map(([pagamento, stat]) => ({
        pagamento,
        total: stat.total,
        count: stat.count,
        percentage: totalGasto > 0 ? (stat.total / totalGasto) * 100 : 0,
      }))
      .sort((a, b) => b.total - a.total);
  }, [entries, totalGasto]);

  // Breakdown by Document Type
  const docTypeStats = useMemo(() => {
    const map: Record<string, { total: number; count: number }> = {
      'Cupom Fiscal': { total: 0, count: 0 },
      'Nota Fiscal': { total: 0, count: 0 },
      'Recibo': { total: 0, count: 0 },
    };

    entries.forEach((entry) => {
      const t = entry.tipo_documento || 'Nota Fiscal';
      if (!map[t]) map[t] = { total: 0, count: 0 };
      map[t].total += entry.valor;
      map[t].count += 1;
    });

    return Object.entries(map).map(([tipo, stat]) => ({
      tipo,
      total: stat.total,
      count: stat.count,
      percentage: totalGasto > 0 ? (stat.total / totalGasto) * 100 : 0,
    }));
  }, [entries, totalGasto]);

  // Top Establishments
  const topStores = useMemo(() => {
    const map: Record<string, { total: number; count: number }> = {};
    entries.forEach((e) => {
      const store = e.estabelecimento || 'Não Informado';
      if (!map[store]) map[store] = { total: 0, count: 0 };
      map[store].total += e.valor;
      map[store].count += 1;
    });

    return Object.entries(map)
      .map(([name, data]) => ({ name, ...data }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 5);
  }, [entries]);

  const auditadosCount = entries.filter((e) => e.status_auditoria === 'auditado').length;
  const auditComplianceRate = entries.length > 0 ? (auditadosCount / entries.length) * 100 : 100;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <h1 className="text-xl font-bold text-slate-900 tracking-tight font-sans">
          Painel de Auditoria & Inteligência Contábil
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          Distribuição analítica de gastos categorizados, conformidade fiscal e meios de pagamento
        </p>

        {/* 4-KPI Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-5 pt-4 border-t border-slate-100">
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-xs text-slate-500 font-medium">Volume Total Auditado</span>
            <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 mt-1">
              R$ {totalGasto.toFixed(2)}
            </div>
            <span className="text-[11px] text-slate-500 mt-0.5 block">
              {entries.length} comprovantes registrados
            </span>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-xs text-slate-500 font-medium">Ticket Médio Fiscal</span>
            <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 mt-1">
              R$ {entries.length > 0 ? (totalGasto / entries.length).toFixed(2) : '0.00'}
            </div>
            <span className="text-[11px] text-slate-500 mt-0.5 block">
              Média por documento
            </span>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-xs text-slate-500 font-medium">Conformidade Fiscal</span>
            <div className="text-2xl font-bold font-mono tabular-nums text-emerald-700 mt-1">
              {auditComplianceRate.toFixed(0)}%
            </div>
            <span className="text-[11px] text-emerald-600 mt-0.5 block">
              {auditadosCount} de {entries.length} documentos validados
            </span>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
            <span className="text-xs text-slate-500 font-medium">Maior Despesa Única</span>
            <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 mt-1">
              R$ {entries.length > 0 ? Math.max(...entries.map((e) => e.valor)).toFixed(2) : '0.00'}
            </div>
            <span className="text-[11px] text-slate-500 mt-0.5 block truncate">
              {entries.length > 0
                ? entries.reduce((max, e) => (e.valor > max.valor ? e : max), entries[0]).estabelecimento
                : '-'}
            </span>
          </div>
        </div>
      </div>

      {/* Analytics Grid: Category breakdown + Payment breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Category Breakdown (7 cols) */}
        <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <PieChart className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">
                Distribuição por Categoria de Gasto
              </h3>
            </div>
            <span className="text-xs font-mono text-slate-500 tabular-nums">
              {categoryStats.length} categorias ativas
            </span>
          </div>

          <div className="space-y-3.5">
            {categoryStats.map((cat) => (
              <div key={cat.categoria} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-800">{cat.categoria}</span>
                    <span className="text-slate-400">({cat.count} notas)</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-slate-500 font-mono tabular-nums">
                      {cat.percentage.toFixed(1)}%
                    </span>
                    <span className="font-bold font-mono tabular-nums text-slate-900">
                      R$ {cat.total.toFixed(2)}
                    </span>
                  </div>
                </div>
                {/* Progress bar */}
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div
                    style={{ width: `${Math.max(4, cat.percentage)}%` }}
                    className="h-full bg-emerald-600 rounded-full transition-all duration-300"
                  ></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Payment Methods Breakdown (5 cols) */}
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <CreditCard className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">
                Meios de Pagamento
              </h3>
            </div>
          </div>

          <div className="divide-y divide-slate-100">
            {paymentStats.map((pay) => (
              <div key={pay.pagamento} className="py-2.5 flex items-center justify-between text-xs">
                <div>
                  <span className="font-semibold text-slate-800">{pay.pagamento}</span>
                  <p className="text-[11px] text-slate-400">{pay.count} comprovantes</p>
                </div>
                <div className="text-right">
                  <div className="font-bold font-mono tabular-nums text-slate-900">
                    R$ {pay.total.toFixed(2)}
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono tabular-nums">
                    {pay.percentage.toFixed(1)}% do total
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Document Types */}
          <div className="pt-4 border-t border-slate-100">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2.5">
              Tipologia Documental
            </h4>
            <div className="grid grid-cols-3 gap-2">
              {docTypeStats.map((doc) => (
                <div key={doc.tipo} className="p-2.5 bg-slate-50 rounded-lg text-center border border-slate-100">
                  <span className="text-[11px] text-slate-500 block truncate">{doc.tipo}</span>
                  <span className="text-xs font-bold font-mono tabular-nums text-slate-900 mt-0.5 block">
                    {doc.count} docs
                  </span>
                  <span className="text-[10px] text-emerald-600 font-mono tabular-nums">
                    R$ {doc.total.toFixed(0)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Top Establishments Table */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Building className="w-4 h-4 text-emerald-600" />
            <h3 className="text-sm font-bold text-slate-900">
              Principais Fornecedores & Estabelecimentos
            </h3>
          </div>
          <span className="text-xs text-slate-400">Classificação por volume financeiro</span>
        </div>

        <div className="divide-y divide-slate-100 text-xs">
          {topStores.map((store, idx) => (
            <div key={idx} className="py-2.5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="w-5 text-center font-mono font-bold text-slate-400">
                  0{idx + 1}
                </span>
                <span className="font-semibold text-slate-900">{store.name}</span>
                <span className="text-slate-400">({store.count} compras)</span>
              </div>
              <div className="font-bold font-mono tabular-nums text-slate-900">
                R$ {store.total.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
