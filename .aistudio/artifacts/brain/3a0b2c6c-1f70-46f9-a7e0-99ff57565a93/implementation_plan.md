# Plano de Modernização da Interface Web — Painel de Auditoria Fiscal

Plano completo de melhoria visual, experiência do usuário (UX) e enriquecimento de dados da aplicação web do Bot de Auditoria Fiscal no Telegram, preservando 100% da lógica de negócios, webhooks, autenticação por senha (`PASSCM`) e integrações com o Google Sheets e Gemini.

## Decisões Confirmadas pelo Usuário

- **Tema Visual**: Alternador Dual Theme Auto (Tema Claro / Tema Escuro com transição suave e persistência no localStorage).
- **Indicadores e Dashboard**:
  - Gráfico de distribuição de gastos acumulados por Categoria (Barras de progresso responsivas com porcentagem).
  - Detalhamento dos Itens por Nota Fiscal / Cupom em cada registro.
  - Painel de Filtros Avançados (Busca textual por estabelecimento, responsável, categoria e forma de pagamento).
- **Recursos da Tabela Principal**:
  - Filtro por Abas Mensais da planilha (ex: `Novembro_2026`, `Outubro_2026`).
  - Tabela Interativa com Ordenação por Colunas (Data, Estabelecimento, Valor, Responsável), Paginação e Exportação para CSV.
  - Modal de Detalhes da Transação com visualizador completo dos dados extraídos e lista discriminada de produtos/serviços.

---

## 1. Visão Geral & Conceito do Produto

O objetivo é transformar o painel atual em um **Dashboard Executivo de Auditoria Fiscal de Nível SaaS**, permitindo que gestores e usuários acompanhem os comprovantes enviados pelo Telegram de forma analítica, organizada e visualmente atraente.

### Funcionalidades do Novo Painel:
1. **Header de Navegação de Nível Enterprise**:
   - Título da aplicação com ícone oficial.
   - Status de conexões ativas (Google Sheets, Gemini AI, Telegram Bot).
   - Alternador de Tema (Modo Claro / Modo Escuro).
   - Botão de logout seguro (`🚪 Sair`) integrado.
2. **Cards de KPIs e Gráficos de Gastos**:
   - **Total Registrado** (R$), **Total de Comprovantes**, **Média por Comprovante**, **Última Atualização**.
   - **Barra Visual de Categorias**: Distribuição percentual dos gastos por Categoria (Alimentação, Veículo, Saúde, Moradia, etc.).
3. **Barra de Controle de Filtros & Período**:
   - Seletor de Mês/Aba da Planilha.
   - Campo de Busca em Tempo Real (filtra estabelecimento, responsável ou observação).
   - Filtros rápidos por Categoria e Forma de Pagamento.
   - Botão para **Download de Relatório em CSV**.
4. **Tabela de Lançamentos Interativa**:
   - Ordenação clicável nos cabeçalhos das colunas (Ex: Maior Valor -> Menor Valor).
   - Visualização clara do Responsável que enviou a foto no grupo do Telegram.
   - Link direto para a foto armazenada no Telegram.
   - Botão de Ação para abrir o **Modal de Detalhes e Itens**.
5. **Modal de Detalhes da Nota Fiscal / Cupom**:
   - Exibição de todos os campos extraídos pelo Gemini.
   - Tabela de itens discriminados (Descrição, Quantidade, Valor Unitário e Valor Total do Item).
   - Link direto para abrir a imagem no servidor do Telegram.

---

## 2. Design Visual & Sistema de Temas (Dual Theme)

### Diretrizes Estéticas (SaaS Dashboard Architecture)
- **Tema Escuro (Dark Mode)**: Fundo `slate-950` (`#0F172A`), superfícies `slate-900` (`#1E293B`), bordas `slate-800`, destaques em verde esmeralda (`#10B981`) e azul telegram (`#0284C7`).
- **Tema Claro (Light Mode)**: Fundo `slate-50` (`#F8FAFC`), superfícies `white` (`#FFFFFF`), bordas `slate-200`, texto principal `slate-900`.
- **Tipografia**: `Plus Jakarta Sans` para títulos e botões, `JetBrains Mono` com números tabulares (`tabular-nums`) para valores financeiros, datas e códigos de transação.
- **Suporte Dual Theme**: Implementação com `@custom-variant dark (&:where(.dark, .dark *));` para alternância instantânea via classe CSS e salvamento no localStorage do navegador.

---

## 3. Arquitetura Técnica & Fluxo de Dados

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TELEGRAM BOT / WEBHOOK                          │
│     (Envia foto do comprovante + legenda -> Gemini AI -> Sheets)       │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI / MAIN.PY SERVER                        │
│   - Rota POST /webhook (Pública, sem autenticação)                     │
│   - Rota GET /login, POST /login, GET /logout (Segurança PASSCM)      │
│   - Rota GET /api/logs (Retorna JSON com logs e itens detalhados)      │
│   - Rota GET / (Dashboard HTML Interativo com Dual Theme & JS Client)  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       PAINEL WEB NO NAVEGADOR                          │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ Top Bar Contract: Status Indicadores | Theme Toggle | Logout   │   │
│   ├────────────────────────────────────────────────────────────────┤   │
│   │ KPI Cards: Total Gasto | Comprovantes | Média | Dist. Categoria│   │
│   ├────────────────────────────────────────────────────────────────┤   │
│   │ Control Bar: Seletor de Mês | Busca | Filtro Categoria | CSV   │   │
│   ├────────────────────────────────────────────────────────────────┤   │
│   │ Tabela Interativa: Ordenação por Colunas | Link Foto | Detalhes│   │
│   ├────────────────────────────────────────────────────────────────┤   │
│   │ Modal de Transação: Visualizador de Itens Comprados (Array)    │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Plano de Execução em Etapas

### Etapa 1: Atualização dos Schemas e JSON do Servidor (`main.py` e `src/main.py`)
- Garantir que o endpoint `GET /api/logs` envie todos os dados estruturados do Gemini (incluindo o array de `itens` com `descricao`, `quantidade` e `valor_total_item`).
- Manter a compatibilidade de rotas existentes (`/webhook`, `/api/health`, `/login`, `/logout`).

### Etapa 2: Reconstrução da Interface do Dashboard (`/`)
- Inserção do script do alternador de tema Claro/Escuro no `<head>` com sincronização do localStorage.
- Construção do componente visual de distribuição de gastos por categoria com barras de progresso dinâmicas.
- Inserção dos controles interativos no lado do cliente (busca em tempo real, ordenação por colunas e paginação).
- Criação do modal acessível de **Detalhes da Nota e Lista de Itens**.

### Etapa 3: Validação e Testes
- Execução do `python3 -m py_compile main.py src/main.py` para garantir sintaxe válida.
- Co-execução de `compile_applet` e `lint_applet` para confirmar build perfeito sem erros de TypeScript/CSS.
- Teste visual e funcional da alternância de tema e filtros no navegador.
