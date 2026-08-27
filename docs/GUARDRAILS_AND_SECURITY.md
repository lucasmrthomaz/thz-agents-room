# 🛡️ THZ Minds — Guardrails, Sandbox e Zero-Trust

## 1. Princípios de Segurança (Defesa em Profundidade)
O THZ Minds adota uma postura rigorosa de **Zero-Trust** para impedir qualquer comportamento danoso de modelos de linguagem, executando código e manipulando arquivos somente dentro de limites previamente estabelecidos.

---

## 2. Camada 1: Validador de Escopo Semântico (ScopeGuard)
- **Objetivo**: Impedir que agentes discutam temas fora do escopo de tecnologia e engenharia de software (ex: política, carros, imóveis, fofocas, etc.).
- **Mecanismo**:
  - Allowlist estrita de 9 domínios de tecnologia permitidos (Programação, Arquitetura, Git, SOs, Liderança Técnica, IHC/UX, DevOps, Banco de Dados, Segurança).
  - Blacklist com mais de 30 categorias não-técnicas bloqueadas imediatamente.
  - Indicadores semânticos de alta confiança para termos técnicos (astapi, postgresql, docker, pgbouncer, stride, jwt, etc.).

---

## 3. Camada 2: Scanner Estático de AST (SandboxASTScanner)
- **Objetivo**: Bloquear código Python potencialmente danoso antes de qualquer tentativa de execução.
- **Bloqueios Nativos**:
  - Módulos proibidos: os, sys, subprocess, shutil, socket, ctypes, uiltins.
  - Funções de execução dinâmica: eval(), exec(), __import__(), compile(), globals(), locals().
  - Operações de I/O não supervisionadas: open(), manipulação de sockets de rede ou processos filhos.

---

## 4. Camada 3: Path Validator com Sandbox Jail (PathValidator)
- **Objetivo**: Conter toda a escrita de arquivos estritamente dentro da pasta output/<project_id>/.
- **Regras de Isolamento**:
  - **Path Traversal Protection**: Rejeita qualquer caminho contendo .., referências absolutas fora do workspace (C:, /etc, etc.).
  - **Arquivos Protegidos**: Proíbe a sobrescrita de arquivos do sistema (server.py, gui.py, .env, .git, 
equirements.txt, bancos .db).
  - **Extensões Proibidas**: Bloqueia a criação de arquivos binários executáveis perigosos (.exe, .dll, .bat, .cmd, .vbs, .sh, .ps1).

---

## 5. Camada 4: Step Limiter & Proteção contra Loops Infinitos (SandboxExecutor)
- **Objetivo**: Evitar ataques de negação de serviço (DoS) via busy loops (while True: pass).
- **Implementação**:
  - Execução monitorada com sys.settrace contando cada instrução executada no interpretador.
  - Limite estrito de 100.000 passos de instrução com timeout máximo de 3 segundos.
  - Qualquer loop infinito é abortado em milissegundos sem congelar a thread ou o servidor.
