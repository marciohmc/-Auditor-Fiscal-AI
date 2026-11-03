import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { ScannerTab } from './components/ScannerTab';
import { LedgerTab } from './components/LedgerTab';
import { MetricsTab } from './components/MetricsTab';
import { TelegramPipelineTab } from './components/TelegramPipelineTab';
import { DocumentModal } from './components/DocumentModal';
import { FiscalEntry, StatusAuditoria } from './types/finance';

export default function App() {
  const [activeTab, setActiveTab] = useState<'scanner' | 'ledger' | 'metrics' | 'pipeline'>('scanner');
  const [entries, setEntries] = useState<FiscalEntry[]>([]);
  const [isLoadingEntries, setIsLoadingEntries] = useState(true);
  const [inspectingEntry, setInspectingEntry] = useState<FiscalEntry | null>(null);

  // Fetch entries from backend
  const fetchEntries = async () => {
    try {
      const response = await fetch('/api/entries');
      if (response.ok) {
        const data = await response.json();
        setEntries(data);
      }
    } catch (error) {
      console.error('Erro ao carregar lançamentos fiscais:', error);
    } finally {
      setIsLoadingEntries(false);
    }
  };

  useEffect(() => {
    fetchEntries();
  }, []);

  const handleEntrySaved = (newEntry: FiscalEntry) => {
    setEntries((prev) => [newEntry, ...prev.filter((e) => e.id !== newEntry.id)]);
  };

  const handleDeleteEntry = async (id: string) => {
    try {
      const res = await fetch(`/api/entries/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setEntries((prev) => prev.filter((e) => e.id !== id));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleUpdateStatus = async (id: string, newStatus: StatusAuditoria, notes?: string) => {
    try {
      const body: any = { status_auditoria: newStatus };
      if (notes !== undefined) body.audit_notes = notes;

      const res = await fetch(`/api/entries/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        const updated = await res.json();
        setEntries((prev) => prev.map((e) => (e.id === id ? updated : e)));
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col text-slate-900 font-sans selection:bg-emerald-500/20 selection:text-emerald-900">
      {/* Top Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onNewScan={() => setActiveTab('scanner')}
        entriesCount={entries.length}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'scanner' && (
          <ScannerTab
            onEntrySaved={(entry) => {
              handleEntrySaved(entry);
              // Option to stay on scanner or notify
            }}
          />
        )}

        {activeTab === 'ledger' && (
          <LedgerTab
            entries={entries}
            onDeleteEntry={handleDeleteEntry}
            onUpdateStatus={handleUpdateStatus}
            onViewDocument={(entry) => setInspectingEntry(entry)}
            onNewScan={() => setActiveTab('scanner')}
          />
        )}

        {activeTab === 'metrics' && <MetricsTab entries={entries} />}

        {activeTab === 'pipeline' && (
          <TelegramPipelineTab
            onEntryAddedFromWebhook={(entry) => {
              handleEntrySaved(entry);
            }}
          />
        )}
      </main>

      {/* Inspection Modal */}
      {inspectingEntry && (
        <DocumentModal
          entry={inspectingEntry}
          onClose={() => setInspectingEntry(null)}
          onUpdateStatus={handleUpdateStatus}
        />
      )}

      {/* Quiet Footer */}
      <footer className="mt-auto border-t border-slate-200 bg-white py-6 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-700">Auditor Fiscal AI</span>
            <span>·</span>
            <span>Extração Multimodal de Notas Fiscais, Cupons SAT e Recibos</span>
          </div>
          <div className="flex items-center gap-4 text-slate-400">
            <span>Formato JSON Padronizado</span>
            <span>·</span>
            <span>Conformidade SEFAZ / NFC-e / SAT</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
