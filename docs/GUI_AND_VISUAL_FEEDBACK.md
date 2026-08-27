# 🖥️ THZ Minds — Interface Gráfica & Feedback Visual

## 1. Estrutura do Layout (2 Linhas + Split Pane)
- **Janela Padrão**: 1260x860 (redimensionável, mínimo 920x620).
- **Linha 1 (Superior)**:
  - Seletores de Modo: 💬 Debate | ⚙️ Engenharia | ✍️ Artigo | 🌙 Noturno.
  - Parâmetros: Modelo: [auto], Turnos: [48], Duração: [8h].
  - Botões de Ação: ▶ Iniciar, ■ Parar, 📂 Pasta output/.
- **Linha 2 (Tópico)**:
  - Campo de entrada Tópico / Desafio com 100% de largura horizontal.
  - Botão 🎲 Gerar Cenário Real para injetar casos de teste de produção.

---

## 2. Barra Lateral com 3 Abas (	tk.Notebook)
1. 💬 **Debates**: Histórico de debates do conselho com filtros e turnos.
2. 📦 **Projetos (Fábrica output/)**:
   - Lista todos os projetos de Engenharia e Artigos gerados.
   - Lista interativa de arquivos com autor e tamanho.
   - **Visualizador de Código Integrado**: Clique em qualquer arquivo para inspecionar o código na tela principal com botões para **Copiar Código**, **Abrir Pasta** e **Fechar**.
3. 🧠 **Conhecimento**: Base de tópicos discutidos e grafo de conhecimento acumulado.

---

## 3. Verbosidade & Cronômetro de Pensamento em Tempo Real
- **Cronômetro Ativo**: Indicador animado ⠋ [Tech Lead] pensando... (⏱ 14s) exibindo os segundos decorridos enquanto a LLM processa.
- **Avisos de Início**: Notificações imediatas no chat quando um novo especialista entra na linha de produção.
- **Streaming de Entregas**: Exibição imediata das contribuições e arquivos criados por etapa.
