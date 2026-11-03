export interface SampleVoucher {
  id: string;
  name: string;
  badge: string;
  tipo: 'Nota Fiscal' | 'Cupom Fiscal' | 'Recibo';
  expectedEstabelecimento: string;
  expectedCategoria: string;
  expectedValor: number;
  expectedPagamento: string;
  data: string;
  description: string;
  draw: (ctx: CanvasRenderingContext2D, width: number, height: number) => void;
}

export const SAMPLE_VOUCHERS: SampleVoucher[] = [
  {
    id: 'cupom-mercado',
    name: 'Cupom Fiscal - Supermercado Pão de Açúcar',
    badge: 'Alimentação',
    tipo: 'Cupom Fiscal',
    expectedEstabelecimento: 'Pão de Açúcar',
    expectedCategoria: 'Alimentação',
    expectedValor: 148.75,
    expectedPagamento: 'Cartão de Crédito',
    data: '02/11/2026',
    description: 'Cupom SAT de compras alimentícias com café, leite, queijo e frutas',
    draw: (ctx, width, height) => {
      // Background thermal receipt paper
      ctx.fillStyle = '#fafaf9';
      ctx.fillRect(0, 0, width, height);

      // Receipt border subtle lines
      ctx.strokeStyle = '#e7e5e4';
      ctx.lineWidth = 2;
      ctx.strokeRect(10, 10, width - 20, height - 20);

      // Header
      ctx.fillStyle = '#1c1917';
      ctx.font = 'bold 24px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('COMPANHIA BRASILEIRA DE DISTRIBUICAO', width / 2, 50);
      ctx.font = 'bold 20px monospace';
      ctx.fillText('SUPERMERCADO PAO DE ACUCAR', width / 2, 78);
      
      ctx.font = '14px monospace';
      ctx.fillStyle = '#44403c';
      ctx.fillText('AV. BRIGADEIRO LUIS ANTONIO, 3126 - JD PAULISTA - SP', width / 2, 102);
      ctx.fillText('CNPJ: 47.508.411/0001-56   IE: 108.383.949.112', width / 2, 122);
      ctx.fillText('------------------------------------------------------------', width / 2, 142);

      ctx.font = 'bold 16px monospace';
      ctx.fillStyle = '#1c1917';
      ctx.fillText('EXTRATO No. 049281 - CUPOM FISCAL ELETRONICO SAT', width / 2, 168);
      ctx.fillText('------------------------------------------------------------', width / 2, 188);

      // Items table
      ctx.font = '14px monospace';
      ctx.textAlign = 'left';
      ctx.fillText('#  COD   DESCRICAO               QTD  UN   VL UNIT   TOTAL', 30, 215);
      ctx.fillText('------------------------------------------------------------', 30, 230);

      const items = [
        { code: '001', desc: 'CAFE TORRADO ESPECIAL 500G', qtd: '2', un: 'UN', unVal: '28,50', total: '57,00' },
        { code: '002', desc: 'LEITE INTEGRAL TIPO A 1L', qtd: '4', un: 'UN', unVal: '6,90', total: '27,60' },
        { code: '003', desc: 'QUEIJO MINAS FRESCAL 400G', qtd: '1', un: 'UN', unVal: '24,90', total: '24,90' },
        { code: '004', desc: 'PAO ARTESANAL FERM. NAT', qtd: '1', un: 'UN', unVal: '18,50', total: '18,50' },
        { code: '005', desc: 'MACA FUJI SELECAO KG', qtd: '1.1', un: 'KG', unVal: '18,86', total: '20,75' },
      ];

      let y = 255;
      items.forEach((item) => {
        ctx.fillText(`${item.code} 78912 ${item.desc.padEnd(25, ' ')}`, 30, y);
        ctx.fillText(`    ${item.qtd} ${item.un} x R$ ${item.unVal} = R$ ${item.total}`, 30, y + 18);
        y += 42;
      });

      ctx.fillText('------------------------------------------------------------', 30, y);
      y += 24;

      // Totals
      ctx.font = 'bold 18px monospace';
      ctx.fillText('TOTAL BRUTO:                              R$ 148,75', 30, y);
      y += 24;
      ctx.fillText('VALOR A PAGAR:                            R$ 148,75', 30, y);
      y += 28;
      ctx.font = 'bold 16px monospace';
      ctx.fillText('FORMA DE PAGAMENTO: CARTAO DE CREDITO    R$ 148,75', 30, y);
      y += 30;

      ctx.font = '13px monospace';
      ctx.fillStyle = '#57534e';
      ctx.fillText('------------------------------------------------------------', 30, y);
      y += 20;
      ctx.fillText('Tributos Totais Incidentes (Lei 12.741/2012): R$ 26,48 (17,8%)', 30, y);
      y += 20;
      ctx.fillText('DATA/HORA EMISSAO: 02/11/2026 14:32:15', 30, y);
      y += 20;
      ctx.fillText('SAT No. 000.492.812 - CHAVE DE ACESSO:', 30, y);
      y += 18;
      ctx.font = '11px monospace';
      ctx.fillText('3526 1147 5084 1100 0156 5900 0492 8121 2849 1048 2912', 30, y);

      // Mock QR code / barcode box
      y += 35;
      ctx.strokeStyle = '#1c1917';
      ctx.lineWidth = 1;
      ctx.strokeRect(width / 2 - 50, y, 100, 100);
      ctx.font = 'bold 12px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('QR-CODE SAT', width / 2, y + 55);
    }
  },
  {
    id: 'nf-combustivel',
    name: 'Nota Fiscal - Posto Shell Gasolina',
    badge: 'Veículo',
    tipo: 'Nota Fiscal',
    expectedEstabelecimento: 'Auto Posto Shell Bandeirantes Ltda',
    expectedCategoria: 'Veículo',
    expectedValor: 265.40,
    expectedPagamento: 'PIX',
    data: '01/11/2026',
    description: 'NFC-e de abastecimento combustível (Gasolina V-Power)',
    draw: (ctx, width, height) => {
      ctx.fillStyle = '#f8fafc';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = '#cbd5e1';
      ctx.lineWidth = 2;
      ctx.strokeRect(10, 10, width - 20, height - 20);

      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 22px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('AUTO POSTO SHELL BANDEIRANTES LTDA', width / 2, 50);
      ctx.font = '14px monospace';
      ctx.fillStyle = '#334155';
      ctx.fillText('RODOVIA DOS BANDEIRANTES KM 38 - CAIEIRAS - SP', width / 2, 75);
      ctx.fillText('CNPJ: 02.433.918/0003-88  INSC. ESTADUAL: 244.091.221.009', width / 2, 95);
      ctx.fillText('============================================================', width / 2, 115);

      ctx.font = 'bold 17px monospace';
      ctx.fillStyle = '#0f172a';
      ctx.fillText('DANFE NFC-e - NOTA FISCAL DE CONSUMIDOR ELETRONICA', width / 2, 140);
      ctx.font = '13px monospace';
      ctx.fillText('NAO PERMITE APROVEITAMENTO DE CREDITO DE ICMS', width / 2, 160);
      ctx.fillText('------------------------------------------------------------', width / 2, 180);

      ctx.textAlign = 'left';
      ctx.font = '14px monospace';
      ctx.fillText('ITEM  CODIGO  DESCRICAO               QTD   UN  V.UNIT  TOTAL', 30, 210);
      ctx.fillText('------------------------------------------------------------', 30, 225);

      ctx.fillText('001   320101  GASOLINA V-POWER ADIT  45,06  LT   5,89   265,40', 30, 250);
      ctx.fillText('      Bico: 04   Bomba: 02   Tanque: 01', 30, 270);

      ctx.fillText('------------------------------------------------------------', 30, 300);
      ctx.font = 'bold 18px monospace';
      ctx.fillText('QTD TOTAL DE ITENS:                                      1', 30, 325);
      ctx.fillText('VALOR TOTAL DA NOTA FISCAL:                      R$ 265,40', 30, 350);
      ctx.fillText('FORMA DE PAGAMENTO: PIX                          R$ 265,40', 30, 375);
      
      ctx.font = '13px monospace';
      ctx.fillStyle = '#475569';
      ctx.fillText('------------------------------------------------------------', 30, 405);
      ctx.fillText('EMISSAO: 01/11/2026 18:15:22 - VIA DO CONSUMIDOR', 30, 425);
      ctx.fillText('PROTOCOLO DE AUTORIZACAO: 135260948210384', 30, 445);
      ctx.fillText('CHAVE DE ACESSO NFC-E:', 30, 465);
      ctx.font = '11px monospace';
      ctx.fillText('3526 1102 4339 1800 0388 6500 1000 0392 0110 4920 1823', 30, 485);

      // QR Code box
      ctx.strokeStyle = '#0f172a';
      ctx.strokeRect(width / 2 - 50, 520, 100, 100);
      ctx.font = 'bold 12px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('QR-CODE SEFAZ', width / 2, 575);
    }
  },
  {
    id: 'cupom-farmacia',
    name: 'Cupom Fiscal - Raia Drogasil',
    badge: 'Saúde',
    tipo: 'Cupom Fiscal',
    expectedEstabelecimento: 'Raia Drogasil S.A. - Farmácia',
    expectedCategoria: 'Saúde',
    expectedValor: 92.40,
    expectedPagamento: 'Cartão de Débito',
    data: '30/10/2026',
    description: 'Cupom de farmácia com medicamentos e protetor solar',
    draw: (ctx, width, height) => {
      ctx.fillStyle = '#fffbeb';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = '#fde68a';
      ctx.lineWidth = 2;
      ctx.strokeRect(10, 10, width - 20, height - 20);

      ctx.fillStyle = '#1e293b';
      ctx.font = 'bold 22px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('RAIA DROGASIL S.A. - FARMACIA', width / 2, 50);
      ctx.font = '14px monospace';
      ctx.fillText('RUA OSCAR FREIRE, 840 - CERQUEIRA CESAR - SP', width / 2, 75);
      ctx.fillText('CNPJ: 61.585.865/0240-31', width / 2, 95);
      ctx.fillText('------------------------------------------------------------', width / 2, 115);

      ctx.font = 'bold 16px monospace';
      ctx.fillText('DOCUMENTO AUXILIAR DE CUPOM FISCAL ELETRONICO', width / 2, 140);
      ctx.fillText('------------------------------------------------------------', width / 2, 160);

      ctx.textAlign = 'left';
      ctx.font = '14px monospace';
      ctx.fillText('COD   DESCRICAO               QTD   UN   V.UNIT    TOTAL', 30, 190);
      ctx.fillText('------------------------------------------------------------', 30, 205);

      ctx.fillText('01  PROTETOR SOLAR FPS 50    1     UN   59,90     59,90', 30, 230);
      ctx.fillText('02  DIPIRONA 500MG 20 COMP   2     CX    8,50     17,00', 30, 255);
      ctx.fillText('03  VITAMINA C EFERV 10 CPR  1     TB   15,50     15,50', 30, 280);

      ctx.fillText('------------------------------------------------------------', 30, 310);
      ctx.font = 'bold 17px monospace';
      ctx.fillText('VALOR TOTAL:                                    R$ 92,40', 30, 335);
      ctx.fillText('PAGAMENTO: CARTAO DE DEBITO                    R$ 92,40', 30, 360);

      ctx.font = '13px monospace';
      ctx.fillText('------------------------------------------------------------', 30, 390);
      ctx.fillText('DATA: 30/10/2026 11:45:00', 30, 410);
      ctx.fillText('OPERADOR: 4920 - CX 02', 30, 430);
      ctx.fillText('CHAVE SAT: 3526 1061 5858 6502 4031 5900 0291 0492 1894', 30, 450);
    }
  },
  {
    id: 'recibo-servico',
    name: 'Recibo - Serviços de Manutenção & Climatização',
    badge: 'Moradia',
    tipo: 'Recibo',
    expectedEstabelecimento: 'Climatiza Serviços Técnicos de Refrigeração',
    expectedCategoria: 'Moradia',
    expectedValor: 450.00,
    expectedPagamento: 'PIX',
    data: '28/10/2026',
    description: 'Recibo profissional assinado de prestação de serviços residenciais',
    draw: (ctx, width, height) => {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = '#0284c7';
      ctx.lineWidth = 3;
      ctx.strokeRect(15, 15, width - 30, height - 30);

      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 26px serif';
      ctx.textAlign = 'center';
      ctx.fillText('RECIBO DE PRESTAÇÃO DE SERVIÇOS', width / 2, 60);
      
      ctx.font = 'bold 18px monospace';
      ctx.fillStyle = '#0369a1';
      ctx.fillText('CLIMATIZA SERVIÇOS TÉCNICOS DE REFRIGERAÇÃO', width / 2, 95);
      ctx.font = '14px monospace';
      ctx.fillStyle = '#334155';
      ctx.fillText('CNPJ: 38.120.944/0001-12 | CONTATO: (11) 98765-4321', width / 2, 120);
      
      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(30, 140);
      ctx.lineTo(width - 30, 140);
      ctx.stroke();

      ctx.textAlign = 'left';
      ctx.font = '16px monospace';
      ctx.fillText('RECIBO Nº: 2026/089                                VALOR: R$ 450,00', 40, 180);
      
      ctx.font = '15px sans-serif';
      ctx.fillStyle = '#1e293b';
      const text = 'Recebemos a quantia de R$ 450,00 (quatrocentos e cinquenta reais) referente aos serviços especializados de higienização completa e manutenção preventiva de 02 unidades de ar condicionado Split 12.000 BTUs.';
      
      // Multi-line wrap
      ctx.fillText('Recebemos a quantia de R$ 450,00 (quatrocentos e cinquenta reais)', 40, 220);
      ctx.fillText('referente aos serviços especializados de higienização completa e', 40, 245);
      ctx.fillText('manutenção preventiva de 02 unidades de ar condicionado Split.', 40, 270);

      ctx.font = 'bold 15px monospace';
      ctx.fillText('FORMA DE PAGAMENTO: PIX (CHAVE CNPJ)', 40, 315);
      ctx.fillText('DATA DO PAGAMENTO: 28/10/2026', 40, 345);

      ctx.strokeStyle = '#0f172a';
      ctx.beginPath();
      ctx.moveTo(width / 2 - 120, 420);
      ctx.lineTo(width / 2 + 120, 420);
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = '14px sans-serif';
      ctx.fillText('Assinatura do Prestador Responsável', width / 2, 440);
      ctx.font = '12px monospace';
      ctx.fillStyle = '#64748b';
      ctx.fillText('Climatiza Serviços Técnicos - Validade Fiscal / Financeira', width / 2, 465);
    }
  }
];

export function generateVoucherCanvasDataUrl(voucher: SampleVoucher): string {
  if (typeof document === 'undefined') return '';
  const canvas = document.createElement('canvas');
  canvas.width = 650;
  canvas.height = 700;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  voucher.draw(ctx, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.95);
}
