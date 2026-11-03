import React from 'react';
import { Receipt, FileSpreadsheet, PlusCircle } from 'lucide-react';

interface HeaderProps {
  activeTab: 'scanner' | 'ledger' | 'metrics' | 'pipeline';
  setActiveTab: (tab: 'scanner' | 'ledger' | 'metrics' | 'pipeline') => void;
  onNewScan: () => void;
  entriesCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  onNewScan,
  entriesCount,
}) => {
  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between gap-8 h-16">
          {/* Zone 1: Single text wordmark */}
          <div className="flex items-center gap-2.5 whitespace-nowrap shrink-0">
            <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center text-white shadow-sm">
              <Receipt className="w-4 h-4" />
            </div>
            <span className="text-lg font-bold tracking-tight text-slate-900 font-sans">
              Auditor Fiscal AI
            </span>
          </div>

          {/* Zone 2: 4 clean single-line text navigation links */}
          <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
            <button
              onClick={() => setActiveTab('scanner')}
              className={`transition-colors whitespace-nowrap shrink-0 pb-0.5 border-b-2 ${
                activeTab === 'scanner'
                  ? 'border-emerald-600 text-emerald-700 font-semibold'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              Scanner & Extração
            </button>
            <button
              onClick={() => setActiveTab('ledger')}
              className={`transition-colors whitespace-nowrap shrink-0 pb-0.5 border-b-2 flex items-center gap-1.5 ${
                activeTab === 'ledger'
                  ? 'border-emerald-600 text-emerald-700 font-semibold'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              <span>Extrato Contábil</span>
              <span className="text-xs font-mono text-slate-400">({entriesCount})</span>
            </button>
            <button
              onClick={() => setActiveTab('metrics')}
              className={`transition-colors whitespace-nowrap shrink-0 pb-0.5 border-b-2 ${
                activeTab === 'metrics'
                  ? 'border-emerald-600 text-emerald-700 font-semibold'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              Auditoria & Métricas
            </button>
            <button
              onClick={() => setActiveTab('pipeline')}
              className={`transition-colors whitespace-nowrap shrink-0 pb-0.5 border-b-2 ${
                activeTab === 'pipeline'
                  ? 'border-emerald-600 text-emerald-700 font-semibold'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              Telegram & Sheets
            </button>
          </nav>

          {/* Zone 3: 1 primary action */}
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={onNewScan}
              className="px-4 py-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors whitespace-nowrap shrink-0 flex items-center gap-2 shadow-sm"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>Novo Comprovante</span>
            </button>
          </div>
        </div>

        {/* Mobile secondary tab strip */}
        <div className="flex md:hidden items-center justify-around border-t border-slate-100 py-2.5 text-xs font-medium text-slate-600">
          <button
            onClick={() => setActiveTab('scanner')}
            className={activeTab === 'scanner' ? 'text-emerald-700 font-semibold' : ''}
          >
            Scanner
          </button>
          <button
            onClick={() => setActiveTab('ledger')}
            className={activeTab === 'ledger' ? 'text-emerald-700 font-semibold' : ''}
          >
            Extrato ({entriesCount})
          </button>
          <button
            onClick={() => setActiveTab('metrics')}
            className={activeTab === 'metrics' ? 'text-emerald-700 font-semibold' : ''}
          >
            Métricas
          </button>
          <button
            onClick={() => setActiveTab('pipeline')}
            className={activeTab === 'pipeline' ? 'text-emerald-700 font-semibold' : ''}
          >
            Telegram
          </button>
        </div>
      </div>
    </header>
  );
};
