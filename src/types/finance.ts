export type TipoDocumento = 'Nota Fiscal' | 'Cupom Fiscal' | 'Recibo';

export type CategoriaDespesa = 
  | 'Alimentação' 
  | 'Transporte' 
  | 'Saúde' 
  | 'Lazer' 
  | 'Moradia' 
  | 'Veículo' 
  | 'Educação' 
  | 'Outros';

export type FormaPagamento = 
  | 'PIX' 
  | 'Cartão de Crédito' 
  | 'Cartão de Débito' 
  | 'Dinheiro' 
  | 'Boleto' 
  | 'Não Informado';

export type StatusAuditoria = 'auditado' | 'pendente' | 'divergencia';

export interface ItemComprovante {
  descricao: string;
  quantidade: number;
  valor_unitario: number;
  valor_total: number;
}

export interface ExtractedFiscalData {
  status_leitura?: 'sucesso' | 'ilegivel';
  mensagem_erro?: string | null;
  tipo_documento: TipoDocumento;
  data: string;
  estabelecimento: string;
  valor: number;
  categoria: CategoriaDespesa;
  pagamento: FormaPagamento;
  cnpj?: string;
  pagador?: string | null;
  doc_pagador?: string | null;
  recebedor?: string | null;
  doc_recebedor?: string | null;
  responsavel?: string | null;
  observacao?: string | null;
  itens?: ItemComprovante[];
  confidence_score?: number;
  tributos_aproximados?: number;
}

export interface FiscalEntry extends ExtractedFiscalData {
  id: string;
  status_auditoria: StatusAuditoria;
  audit_notes?: string;
  imagem_url?: string;
  raw_json?: string;
  origem: 'upload' | 'camera' | 'telegram_webhook' | 'amostra';
  criado_em: string;
}

export interface WebhookLog {
  id: string;
  timestamp: string;
  chat_id: number;
  origem: string;
  file_id?: string;
  payload_summary: string;
  status: 'sucesso' | 'erro' | 'processando';
  extracted_data?: ExtractedFiscalData;
  error_message?: string;
}
