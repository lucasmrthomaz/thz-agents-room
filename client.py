"""
Cliente CLI para THz Minds - Motor Multiagente Local
Modos: Single + Autonomous + Engineering + Content + Historico + Projetos + Auditoria
Protocolo: WebSocket (RFC 6455) / JSON (RFC 8259) / SSE / HTTP REST

Funcionalidades equivalentes a GUI:
- Resumo de debates ao final
- Loading/progresso por turno
- Historico de debates recentes com detalhes
- Base de conhecimento
- Countdown de pausa entre debates
- Pipeline TeamWork (Engenharia + Artigo) via SSE
- Gerador de cenarios reais
- Visualizador de projetos gerados
- Auditoria de integridade (Livro-Verdade)
- Auto-start do servidor
"""

import asyncio
import argparse
import json
import sys
import os
import time
import threading
import urllib.request
import urllib.parse
import websockets

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import settings as cfg

URI = cfg.WS_URI
BASE_URL = f"http://127.0.0.1:{cfg.PORT}"

# Cores ANSI
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

# Icones
ICON_ROCKET  = "\U0001f680"
ICON_BRAIN   = "\U0001f9e0"
ICON_BULB    = "\U0001f4a1"
ICON_GEAR    = "\u2699\ufe0f"
ICON_CHECK   = "\u2705"
ICON_X       = "\u274c"
ICON_HOUR    = "\u23f0"
ICON_TARGET  = "\U0001f3af"
ICON_SPEECH  = "\U0001f4ac"
ICON_SCROLL  = "\U0001f4dc"
ICON_STAR    = "\u2b50"
ICON_WARNING = "\u26a0\ufe0f"
ICON_LINK    = "\U0001f517"
ICON_CLOCK   = "\U0001f552"
ICON_BRAIN2  = "\U0001f4a0"
ICON_WRENCH  = "\U0001f527"
ICON_PENCIL  = "\u270f\ufe0f"
ICON_DICE   = "\U0001f3b2"
ICON_FOLDER  = "\U0001f4c2"
ICON_SHIELD  = "\U0001f6e1\ufe0f"
ICON_FILE    = "\U0001f4c4"

# Mapeamento de agentes para cores
AGENT_COLORS = {
    "Arquiteto":    CYAN,
    "SRE":          RED,
    "DevOps":       GREEN,
    "DBA":          YELLOW,
    "Security":     MAGENTA,
    "PO":           BLUE,
    "Scrum Master": WHITE,
    "Gerente":      "\033[38;5;208m",
    "Dev Senior":   "\033[38;5;75m",
}

STATUS_COLORS = {
    "CONTINUE":   YELLOW,
    "CONSENSUS":  GREEN,
    "STOP":       RED,
    "FORCE_STOP": RED,
}

# Loading frames
LOADING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# =====================================================================
# UTILITARIOS DE DISPLAY
# =====================================================================

def _c(text: str, color: str, bold: bool = False) -> str:
    prefix = f"{BOLD}" if bold else ""
    return f"{prefix}{color}{text}{RESET}"


def _agent_color(agent_name: str) -> str:
    return AGENT_COLORS.get(agent_name, WHITE)


def _status_color(status: str) -> str:
    return STATUS_COLORS.get(status, WHITE)


def _print_logo():
    logo = rf"""
{_c('  ████████╗███████╗██████╗ ███╗   ███╗', CYAN, bold=True)}
{_c('  ╚══██╔══╝██╔════╝██╔══██╗████╗ ████║', CYAN, bold=True)}
{_c('     ██║   █████╗  ██████╔╝██╔████╔██║', CYAN, bold=True)}
{_c('     ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║', CYAN, bold=True)}
{_c('     ██║   ███████╗██║  ██║██║ ╚═╝ ██║', CYAN, bold=True)}
{_c('     ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝', CYAN, bold=True)}
{_c('          MOTOR MULTIAGENTE LOCAL', DIM)}
"""
    print(logo)


def _print_banner_single(topic: str, max_turns: int, num_ctx: int, model: str):
    _print_logo()
    print(f"  {_c(ICON_TARGET, GREEN)} {_c('MODO SINGLE', BOLD + GREEN)}  {_c('— Debate sob demanda', DIM)}")
    print()
    print(f"  {_c('Topico:', BOLD)} {topic}")
    print(f"  {_c('Turnos:', BOLD)} {max_turns}")
    print(f"  {_c('Contexto:', BOLD)} {num_ctx}")
    print(f"  {_c('Modelo:', BOLD)} {model or 'auto-discovery'}")
    print(f"\n  {'━'*76}\n")


def _print_banner_autonomous(duration_hours: float, num_ctx: int, model: str):
    _print_logo()
    print(f"  {_c(ICON_HOUR, YELLOW)} {_c('MODO AUTONOMO', BOLD + YELLOW)}  {_c('— Sessao noturna', DIM)}")
    print()
    print(f"  {_c('Duracao:', BOLD)} {duration_hours}h")
    print(f"  {_c('Contexto:', BOLD)} {num_ctx}")
    print(f"  {_c('Modelo:', BOLD)} {model or 'auto-discovery'}")
    print(f"  {_c('Pausa:', BOLD)} 1 min entre debates")
    print(f"\n  {'━'*76}\n")


def _print_banner_teamwork(mode: str, goal: str, model: str):
    _print_logo()
    label = "ENGENHARIA" if mode == "engineering" else "ARTIGO"
    icon = ICON_WRENCH if mode == "engineering" else ICON_PENCIL
    color = GREEN if mode == "engineering" else MAGENTA
    print(f"  {_c(icon, color)} {_c(f'MODO {label}', BOLD + color)}  {_c('— TeamWork Pipeline', DIM)}")
    print()
    print(f"  {_c('Objetivo:', BOLD)} {goal}")
    print(f"  {_c('Modelo:', BOLD)} {model or 'auto-discovery'}")
    steps = 7 if mode == "engineering" else 6
    print(f"  {_c('Etapas:', BOLD)} {steps}")
    print(f"\n  {'━'*76}\n")


def _print_banner_interactive():
    _print_logo()
    print(f"  {_c(ICON_GEAR, MAGENTA)} {_c('MODO INTERATIVO', BOLD + MAGENTA)}")
    print()
    print(f"  {_c('1', BOLD + CYAN)}   Debate sob demanda")
    print(f"  {_c('2', BOLD + YELLOW)}  Sessao autonoma (noturna)")
    print(f"  {_c('3', BOLD + GREEN)}  Engenharia (TeamWork)")
    print(f"  {_c('4', BOLD + MAGENTA)} Artigo (TeamWork)")
    print(f"  {_c('5', BOLD + CYAN)}   Gerar cenario real")
    print(f"  {_c('6', BOLD + BLUE)}  Ver historico de debates")
    print(f"  {_c('7', BOLD + GREEN)}  Ver projetos gerados")
    print(f"  {_c('8', BOLD + MAGENTA)} Ver base de conhecimento")
    print(f"  {_c('9', BOLD + RED)}   Auditar integridade (Livro-Verdade)")
    print()


def _print_progress(current: int, total: int, agent: str):
    pct = int((current / total) * 100) if total > 0 else 0
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)
    print(f"\r  {_c(f'[{bar}]', DIM)} {_c(f'{pct}%', DIM)} Turno {_c(str(current), BOLD)}/{total}", end="", flush=True)


def _print_loading(message: str, frame: int):
    icon = LOADING_FRAMES[frame % len(LOADING_FRAMES)]
    print(f"\r  {_c(icon, CYAN)} {message}...", end="", flush=True)


def _clear_line():
    print(f"\r{'':80}\r", end="", flush=True)


def _print_summary(summary: str):
    if not summary:
        return
    print(f"\n  {_c(ICON_BULB, YELLOW)} {_c('RESUMO DO DEBATE:', BOLD + YELLOW)}")
    for line in summary.split("\n"):
        print(f"  {_c(line, DIM)}")
    print()


def _print_debate_complete(reason: str, total_turns: int, summary: str = ""):
    if reason == "topic_exhausted":
        print(f"\n  {_c(ICON_WARNING, RED)} {_c('DEBATE ENCERRADO', BOLD + RED)}  {_c('Topico exaurido', DIM)}")
    elif reason == "consensus":
        print(f"\n  {_c(ICON_CHECK, GREEN)} {_c('DEBATE ENCERRADO', BOLD + GREEN)}  {_c('Consenso', DIM)}  {_c(f'Turnos: {total_turns}', DIM)}")
    else:
        print(f"\n  {_c(ICON_HOUR, YELLOW)} {_c('DEBATE ENCERRADO', BOLD + YELLOW)}  {_c('Timeout', DIM)}  {_c(f'Turnos: {total_turns}', DIM)}")
    _print_summary(summary)
    print(f"  {'━'*76}\n")


def _print_pause_countdown(duration: int):
    print(f"\n  {_c(ICON_CLOCK, YELLOW)} {_c('PAUSA', BOLD + YELLOW)} — Proximo debate em {duration}s...")
    for remaining in range(duration, 0, -1):
        mins = remaining // 60
        secs = remaining % 60
        time_str = f"{mins:02d}:{secs:02d}" if mins > 0 else f"{secs}s"
        print(f"\r  {_c(ICON_CLOCK, YELLOW)} {_c('PAUSA', BOLD + YELLOW)} — Proximo debate em {time_str}  ", end="", flush=True)
        time.sleep(1)
    print(f"\r  {_c(ICON_CHECK, GREEN)} Iniciando proximo debate...                    ")


def _print_session_complete(data: dict):
    print(f"\n  {'━'*76}")
    print(f"\n  {_c(ICON_STAR, YELLOW)} {_c('SESSAO ENCERRADA', BOLD + YELLOW)}")
    print(f"  {_c('Total de debates:', BOLD)} {data.get('total_debates', '?')}")
    print(f"  {_c('Duracao:', BOLD)} {data.get('duration_hours', '?')}h")
    topics = data.get("topics", [])
    if topics:
        print(f"\n  {_c('Topicos discutidos:', BOLD)}")
        for i, t in enumerate(topics, 1):
            if isinstance(t, dict):
                topic_name = t.get("topic", str(t))
                consensus = t.get("consensus", False)
                icon = ICON_CHECK if consensus else ICON_X
                status_text = "consenso" if consensus else "sem consenso"
                print(f"    {_c(str(i), CYAN)}. {topic_name} {_c(f'[{status_text}]', DIM)}")
            else:
                print(f"    {_c(str(i), CYAN)}. {t}")
    summary = data.get("summary", "")
    if summary:
        print(f"\n  {_c('Resumo da sessao:', BOLD)}")
        for line in summary.split("\n"):
            print(f"    {DIM}{line}{RESET}")
    print(f"\n  {'━'*76}\n")


# =====================================================================
# SERVER AUTO-START
# =====================================================================

def _ensure_server_running():
    """Verifica se o servidor esta rodando. Se nao, inicia em background e aguarda."""
    if _check_server_ready():
        return True

    print(f"  {_c(ICON_GEAR, CYAN)} {_c('Iniciando servidor em background...', DIM)}")
    try:
        import uvicorn
        from server import app

        def run_server():
            uvicorn.run(app, host="127.0.0.1", port=cfg.PORT, log_level="warning")

        t = threading.Thread(target=run_server, daemon=True)
        t.start()
    except ImportError:
        print(f"  {_c(ICON_X, RED)} {_c('ERRO:', BOLD + RED)} uvicorn nao encontrado. Instale com: pip install uvicorn")
        return False

    for i in range(30):
        time.sleep(1)
        if _check_server_ready():
            print(f"  {_c(ICON_CHECK, GREEN)} Servidor online na porta {cfg.PORT}")
            return True
        print(f"\r  {_c(LOADING_FRAMES[i % len(LOADING_FRAMES)], CYAN)} Aguardando servidor... ({i+1}s)", end="", flush=True)

    _clear_line()
    print(f"  {_c(ICON_X, RED)} {_c('TIMEOUT:', BOLD + RED)} Servidor nao respondeu em 30s.")
    return False


def _check_server_ready() -> bool:
    try:
        req = urllib.request.urlopen(f"{BASE_URL}/docs", timeout=2)
        return req.status == 200
    except Exception:
        return False


# =====================================================================
# WEBSOCKET: DEBATES (SINGLE + AUTONOMOUS)
# =====================================================================

async def run_single(topic: str, max_turns: int, num_ctx: int, model: str = None):
    payload = {
        "mode": "single",
        "topic": topic,
        "max_turns": max_turns,
        "num_ctx": num_ctx,
        "model": model
    }
    _print_banner_single(topic, max_turns, num_ctx, model)
    await _run_session(payload)


async def run_autonomous(duration_hours: float, num_ctx: int, model: str = None):
    payload = {
        "mode": "autonomous",
        "duration_hours": duration_hours,
        "num_ctx": num_ctx,
        "model": model
    }
    _print_banner_autonomous(duration_hours, num_ctx, model)
    await _run_session(payload)


async def _run_session(payload: dict):
    try:
        async with websockets.connect(URI, ping_timeout=120, close_timeout=10) as ws:
            await ws.send(json.dumps(payload))
            loading_frame = 0
            current_turn = 0
            max_turns = payload.get("max_turns", 48)

            while True:
                try:
                    raw = await ws.recv()
                    event = json.loads(raw)
                    evt = event.get("event")
                    data = event.get("data", {})

                    if evt == "session_start":
                        sid = data.get('session_id', '?')
                        dur = data.get('duration_hours', '?')
                        mdl = data.get('model', '?')
                        print(f"\n  {_c(ICON_LINK, BLUE)} {_c('SESSAO INICIADA', BOLD + BLUE)}")
                        print(f"  {_c('ID:', BOLD)} {sid}")
                        print(f"  {_c('Duracao:', BOLD)} {dur}h")
                        print(f"  {_c('Modelo:', BOLD)} {mdl}")
                        print(f"\n  {'━'*76}\n")

                    elif evt == "debate_start":
                        num = data.get("debate_num", "?")
                        topic = data.get("topic", "?")
                        print(f"  {_c(ICON_SPEECH, CYAN)} {_c(f'DEBATE {num}', BOLD + CYAN)}  {_c(topic, DIM)}")
                        print(f"  {'─'*76}")

                    elif evt == "turn_start":
                        agent = data.get('agent', '?')
                        turn = data.get('turn', '?')
                        current_turn = turn
                        _print_progress(current_turn, max_turns, agent)
                        _print_loading(f"{agent} analisando", loading_frame)
                        loading_frame += 1

                    elif evt == "turn_end":
                        agent = data.get('agent', '?')
                        arg = data.get("argument", "Sem conteudo.")
                        status = data.get("status", "?")
                        color = _agent_color(agent)
                        scolor = _status_color(status)
                        _clear_line()
                        print(f"  {_c(ICON_BRAIN, color)} {_c(agent, BOLD + color)}:")
                        print(f"  {arg}")
                        print(f"  {_c(f'[{status}]', BOLD + scolor)}")
                        print(f"  {'─'*76}")

                    elif evt == "ping":
                        pass

                    elif evt == "debate_paused":
                        duration = data.get("duration_seconds", 60)
                        _print_pause_countdown(duration)

                    elif evt == "debate_complete":
                        motivo = data.get("reason", "?")
                        total_turns = data.get('total_turns', 0)
                        summary = data.get("summary", "")
                        _print_debate_complete(motivo, total_turns, summary)

                    elif evt == "session_complete":
                        _print_session_complete(data)
                        break

                    elif evt == "error":
                        print(f"\n  {_c(ICON_X, RED)} {_c('ERRO:', BOLD + RED)} {data.get('message')}")
                        break

                except websockets.exceptions.ConnectionClosed:
                    print(f"\n  {_c(ICON_WARNING, YELLOW)} {_c('Conexao encerrada pelo servidor.', YELLOW)}")
                    break

    except ConnectionRefusedError:
        print(f"\n  {_c(ICON_X, RED)} {_c('FALHA:', BOLD + RED)} Nao foi possivel conectar a {URI}")
        print(f"  {_c('Dica:', DIM)} Use sem --no-server para iniciar automaticamente.")


# =====================================================================
# TEAMWORK PIPELINE (ENGINEERING + CONTENT) VIA SSE
# =====================================================================

async def run_teamwork(mode: str, goal: str, model: str = None):
    """Executa pipeline TeamWork via SSE streaming."""
    _print_banner_teamwork(mode, goal, model)

    req_data = json.dumps({
        "mode": mode,
        "goal": goal,
        "model": None if model == "auto" else model
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/api/teamwork/stream",
        data=req_data,
        headers={"Content-Type": "application/json"}
    )

    total_steps = 7 if mode == "engineering" else 6
    step_start = time.time()

    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                json_str = line[5:].strip()
                if not json_str:
                    continue
                evt = json.loads(json_str)

                evt_type = evt.get("type", "")
                status = evt.get("status", "")
                msg = evt.get("message", "")
                step_data = evt.get("step_data") or {}

                if status == "started":
                    print(f"  {_c(ICON_ROCKET, GREEN)} {_c(msg, DIM)}")

                elif status == "model_fallback":
                    print(f"\n  {_c(ICON_WARNING, YELLOW)} {_c('[CIRCUIT BREAKER]', BOLD + YELLOW)} {msg}")

                elif status == "running":
                    role = evt.get("role", "")
                    elapsed = int(time.time() - step_start)
                    print(f"\r  {_c(LOADING_FRAMES[0], CYAN)} {role}: {msg} ({elapsed}s)   ", end="", flush=True)

                elif status == "completed" and evt.get("stage") not in ["completed", "COMPLETED"]:
                    _clear_line()
                    role = evt.get("role", "Especialista")
                    role_title = step_data.get("role_title", role)
                    stage = evt.get("stage", "")
                    contrib = step_data.get("contribution", "")
                    files = step_data.get("files", [])
                    step_num = step_data.get("step_number")
                    pct = int((step_num / total_steps) * 100) if step_num else 0

                    print(f"  {_c(ICON_CHECK, GREEN)} {_c(f'Etapa {step_num}/{total_steps}', BOLD + GREEN)} ({pct}%) — {_c(role_title, BOLD)}")
                    if contrib:
                        preview = contrib[:200] + ("..." if len(contrib) > 200 else "")
                        print(f"    {DIM}{preview}{RESET}")
                    if files:
                        print(f"    {_c('Arquivos:', DIM)}")
                        for f in files:
                            print(f"      {_c(ICON_FILE, CYAN)} {f}")
                    print(f"  {'─'*76}")
                    step_start = time.time()

                elif status == "pipeline_finished" or evt.get("stage") in ["completed", "COMPLETED"] or evt_type == "teamwork_complete":
                    res = evt.get("result") or {}
                    out_dir = res.get("output_directory", "")
                    summary = res.get("executive_summary") or step_data.get("contribution") or msg

                    print(f"\n  {'━'*76}")
                    print(f"  {_c(ICON_CHECK, GREEN)} {_c('TEAMWORK CONCLUIDO!', BOLD + GREEN)} ({total_steps}/{total_steps} etapas)")
                    if summary:
                        print(f"  {summary}")
                    if out_dir:
                        print(f"\n  {_c(ICON_FOLDER, CYAN)} Arquivos salvos em: {out_dir}")
                    print(f"  {'━'*76}\n")

                elif evt_type == "error":
                    print(f"\n  {_c(ICON_X, RED)} {_c('ERRO:', BOLD + RED)} {msg}")
                    return

    except Exception as e:
        print(f"\n  {_c(ICON_X, RED)} {_c('ERRO DE CONEXAO:', BOLD + RED)} {e}")


# =====================================================================
# CENARIO ALEATORIO
# =====================================================================

async def _fill_random_scenario(mode: str = "engineering") -> str:
    """Busca um cenario real da API e retorna o prompt/topico."""
    endpoint = "/api/scenarios/content" if mode == "content" else "/api/scenarios/engineering"
    try:
        with urllib.request.urlopen(f"{BASE_URL}{endpoint}", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if mode == "content":
                return data.get("topic", "")
            else:
                print(f"\n  {_c(ICON_BULB, CYAN)} {_c('CENARIO DE ENGENHARIA:', BOLD + CYAN)}")
                print(f"  {_c('Titulo:', BOLD)} {data.get('title', '?')}")
                print(f"  {_c('Categoria:', BOLD)} {data.get('category', '?')}")
                print(f"  {_c('Escala:', BOLD)} {data.get('scale', '?')}")
                print(f"  {_c('SLA:', BOLD)} {data.get('sla_target', '?')}")
                constraints = data.get("constraints", [])
                if constraints:
                    print(f"  {_c('Restricoes:', BOLD)}")
                    for c in constraints:
                        print(f"    • {c}")
                stack = data.get("tech_stack", [])
                if stack:
                    print(f"  {_c('Stack:', BOLD)} {', '.join(stack)}")
                print()
                return data.get("prompt", "")
    except Exception as e:
        print(f"  {_c(ICON_X, RED)} {_c('Erro ao buscar cenario:', RED)} {e}")
        return ""


# =====================================================================
# PROJETOS GERADOS
# =====================================================================

async def _show_projects():
    """Lista projetos gerados pelo TeamWork."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/teamwork/projects", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            projects = data.get("projects", [])
    except Exception as e:
        print(f"\n  {_c(ICON_X, RED)} {_c('Erro ao carregar projetos:', RED)} {e}")
        return

    _print_logo()
    print(f"  {_c(ICON_FOLDER, GREEN)} {_c('PROJETOS GERADOS', BOLD + GREEN)}")
    print(f"  {'━'*76}\n")

    if not projects:
        print(f"  {_c('Nenhum projeto gerado ainda.', DIM)}")
        print(f"  {_c('Dica:', DIM)} Use --engineering ou --content para criar projetos.")
        print(f"\n  {'━'*76}\n")
        return

    for i, p in enumerate(projects, 1):
        p_name = p.get("project_name", p.get("session_id", "Projeto"))
        mode = p.get("mode", "engineering")
        goal = p.get("goal", "")
        files = p.get("files", [])
        date_str = p.get("created_at", "")[:16].replace("T", " ")
        icon = ICON_WRENCH if mode == "engineering" else ICON_PENCIL
        color = GREEN if mode == "engineering" else MAGENTA

        print(f"  {_c(str(i), BOLD + CYAN)}. {_c(icon + ' ' + p_name, BOLD + color)}")
        if goal:
            print(f"      {_c(goal[:60], DIM)}")
        print(f"      {_c(date_str, DIM)} | {_c(f'{len(files)} arquivo(s)', DIM)}")
        if files:
            for f in files:
                f_path = f.get("path") if isinstance(f, dict) else str(f)
                print(f"        {_c(ICON_FILE, CYAN)} {f_path}")
        print(f"  {'─'*76}")

    print(f"\n  {_c('Use:', DIM)} {_c('--view-file <projeto> <arquivo>', BOLD)} {_c('para ver conteudo', DIM)}")
    print(f"  {'━'*76}\n")


async def _view_file(project_id: str, file_path: str):
    """Exibe o conteudo de um arquivo de projeto."""
    params = urllib.parse.urlencode({"project_id": project_id, "file_path": file_path})
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/teamwork/file?{params}", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("content", "")
    except Exception as e:
        print(f"\n  {_c(ICON_X, RED)} {_c('Erro ao abrir arquivo:', RED)} {e}")
        return

    print(f"\n  {'━'*76}")
    print(f"  {_c(ICON_FILE, CYAN)} {_c(f'{project_id} / {file_path}', BOLD + CYAN)}")
    print(f"  {'━'*76}\n")
    print(content)
    print(f"\n  {'━'*76}\n")


# =====================================================================
# AUDITORIA DE INTEGRIDADE
# =====================================================================

async def _run_audit():
    """Executa auditoria de integridade (Livro-Verdade)."""
    _print_logo()
    print(f"  {_c(ICON_SHIELD, RED)} {_c('AUDITORIA DE INTEGRIDADE', BOLD + RED)}  {_c('— Livro-Verdade (SSOT)', DIM)}")
    print(f"  {'━'*76}\n")
    print(f"  {_c(LOADING_FRAMES[0], CYAN)} Auditando Cortex + Manifestos + Disco...", end="", flush=True)

    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/integrity/audit", timeout=60) as resp:
            report = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _clear_line()
        print(f"  {_c(ICON_X, RED)} {_c('Erro na auditoria:', RED)} {e}")
        return

    _clear_line()

    score = report.get("integrity_score_pct", 0)
    status = report.get("status", "?")
    status_color = GREEN if status == "HEALTHY" else YELLOW

    print(f"  {'='*76}")
    print(f"  {_c(ICON_SHIELD, status_color)} {_c('RELATORIO DE AUDITORIA', BOLD + status_color)}")
    print(f"  Status: {_c(status, BOLD + status_color)}  |  Score: {_c(f'{score}%', BOLD)}")
    print(f"  {'='*76}\n")

    summary = report.get("summary", {})
    print(f"  {_c('RESUMO:', BOLD)}")
    print(f"    Total rastreado no SQLite:  {_c(str(summary.get('total_tracked_in_db', 0)), BOLD)}")
    print(f"    Integros (SHA-256):         {_c(str(summary.get('verified_intact', 0)), GREEN)}")

    missing = summary.get('missing_on_disk', 0)
    tampered = summary.get('tampered_or_modified', 0)
    orphans = summary.get('orphans_on_disk', 0)

    print(f"    Faltantes no disco:         {_c(str(missing), YELLOW if missing else WHITE)}")
    print(f"    Modificados/adulterados:    {_c(str(tampered), RED if tampered else WHITE)}")
    print(f"    Orfaos no disco:            {_c(str(orphans), DIM)}")
    print()

    details = report.get("details", {})

    if details.get("missing_files"):
        print(f"  {_c(ICON_WARNING, YELLOW)} {_c('ARQUIVOS FALTANTES:', BOLD + YELLOW)}")
        for m in details["missing_files"]:
            sha_preview = m.get('expected_sha256', '')[:12] if m.get('expected_sha256') else 'N/A'
            print(f"    • [{m.get('project_name', '?')}] {m.get('file_path', '?')} (SHA: {sha_preview})")
        print()

    if details.get("sample_verified"):
        print(f"  {_c(ICON_CHECK, GREEN)} {_c('AMOSTRA VERIFICADOS:', BOLD + GREEN)}")
        for v in details["sample_verified"][:5]:
            sha_preview = v.get('sha256_hash', '')[:16]
            print(f"    • [{v.get('project_name', '?')}] {v.get('file_path', '?')} ({v.get('size_bytes', 0)} bytes) -> {sha_preview}...")
        print()

    print(f"  {'━'*76}\n")


# =====================================================================
# HISTORICO COM DETALHES
# =====================================================================

async def _show_history(detail_index: int = None):
    """Mostra historico de debates. Se detail_index for fornecido, mostra detalhes."""
    import aiosqlite
    try:
        async with aiosqlite.connect("data/thz-room-cortex.db") as db:
            cursor = await db.execute("""
                SELECT
                    c.id,
                    c.topic,
                    c.created_at,
                    COUNT(m.id) as total_turns,
                    MAX(m.status) as last_status
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                GROUP BY c.id
                ORDER BY c.created_at DESC
                LIMIT 20
            """)
            rows = await cursor.fetchall()

            _print_logo()
            print(f"  {_c(ICON_SCROLL, CYAN)} {_c('HISTORICO DE DEBATES', BOLD + CYAN)}")
            print(f"  {'━'*76}\n")

            if not rows:
                print(f"  {_c('Nenhum debate encontrado.', DIM)}")
                print(f"\n  {'━'*76}\n")
                return

            debates = []
            for i, row in enumerate(rows):
                conv_id, topic, created_at, total_turns, last_status = row

                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_at)
                    date_str = dt.strftime("%d/%m %H:%M")
                except (ValueError, TypeError):
                    date_str = created_at[:16] if created_at else "?"

                if last_status == "CONSENSUS":
                    icon = ICON_CHECK
                    scolor = GREEN
                elif last_status == "CONTINUE":
                    icon = "..."
                    scolor = YELLOW
                else:
                    icon = "•"
                    scolor = DIM

                debates.append({
                    "id": conv_id, "topic": topic, "date": date_str,
                    "turns": total_turns, "status": last_status
                })

                marker = f" {_c('<<', BOLD + RED)}" if detail_index is not None and i == detail_index else ""
                print(f"  {_c(str(i+1), BOLD + CYAN)}. {_c(icon, scolor)} {_c(topic[:55], WHITE)}  {_c(f'{total_turns}t', DIM)}  {_c(date_str, DIM)}{marker}")

            print(f"\n  {'━'*76}")

            if detail_index is not None:
                if detail_index < 0 or detail_index >= len(debates):
                    print(f"\n  {_c(ICON_X, RED)} Indice invalido. Use 1-{len(debates)}")
                    return

                debate = debates[detail_index]
                print(f"\n  {_c(ICON_SPEECH, CYAN)} {_c('DEBATE:', BOLD + CYAN)} {debate['topic']}")
                print(f"  {_c('Data:', BOLD)} {debate['date']}  |  {_c('Turnos:', BOLD)} {debate['turns']}  |  {_c('Status:', BOLD)} {debate['status']}")
                print(f"  {'─'*76}\n")

                cursor2 = await db.execute("""
                    SELECT agent_name, content, status, turn
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY turn
                """, (debate["id"],))
                messages = await cursor2.fetchall()

                for agent, content, status, turn in messages:
                    color = _agent_color(agent)
                    scolor = _status_color(status)
                    print(f"  {_c(f'Turno {turn}', DIM)} — {_c(agent, BOLD + color)}:")
                    print(f"  {content}")
                    print(f"  {_c(f'[{status}]', BOLD + scolor)}")
                    print(f"  {'─'*76}")

            print(f"\n  {'━'*76}\n")

    except Exception as e:
        print(f"\n  {_c(ICON_X, RED)} {_c('Erro ao carregar historico:', RED)} {e}")


# =====================================================================
# BASE DE CONHECIMENTO
# =====================================================================

async def _show_knowledge():
    import aiosqlite
    try:
        async with aiosqlite.connect("data/thz-room-cortex.db") as db:
            cursor = await db.execute("""
                SELECT topic, times_discussed, last_consensus, last_discussed_at
                FROM topic_memory
                ORDER BY times_discussed DESC
                LIMIT 20
            """)
            rows = await cursor.fetchall()

            _print_logo()
            print(f"  {_c(ICON_BRAIN2, BLUE)} {_c('BASE DE CONHECIMENTO', BOLD + BLUE)}")
            print(f"  {'━'*76}\n")

            if not rows:
                print(f"  {_c('Nenhum topico discutido ainda.', DIM)}")
            else:
                for row in rows:
                    topic, times, consensus, last_at = row
                    icon = ICON_CHECK if consensus else ICON_X
                    status = "consenso" if consensus else "sem consenso"
                    print(f"  {_c(icon, GREEN if consensus else YELLOW)} {_c(topic[:50], WHITE)}  {_c(f'({times}x)', DIM)}  {_c(status, DIM)}")

            print(f"\n  {'━'*76}\n")

    except Exception as e:
        print(f"\n  {_c(ICON_X, RED)} {_c('Erro ao carregar base de conhecimento:', RED)} {e}")


# =====================================================================
# MAIN
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="THz Minds - Cliente CLI para debates multiagente e TeamWork",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python client.py --topic 'Kafka vs RabbitMQ para fila de eventos'\n"
            "  python client.py --autonomous --hours 8\n"
            "  python client.py --engineering --goal 'Sistema de pagamentos'\n"
            "  python client.py --content --goal 'Artigo sobre K8s'\n"
            "  python client.py --scenario --engineering\n"
            "  python client.py --projects\n"
            "  python client.py --view-file project_eng_001 docker-compose.yml\n"
            "  python client.py --history\n"
            "  python client.py --history 3\n"
            "  python client.py --audit\n"
        )
    )

    # Debates
    parser.add_argument("--topic", "-t", type=str, help="Topico para debate (modo single)")
    parser.add_argument("--autonomous", "-a", action="store_true", help="Modo autonomo (sessao noturna)")
    parser.add_argument("--hours", type=float, default=8.0, help="Duracao em horas (default: 8)")
    parser.add_argument("--turns", type=int, default=48, help="Max turnos por debate (default: 48)")

    # TeamWork
    parser.add_argument("--engineering", "-e", action="store_true", help="Modo Engenharia (TeamWork pipeline)")
    parser.add_argument("--content", "-c", action="store_true", help="Modo Artigo (TeamWork pipeline)")
    parser.add_argument("--goal", "-g", type=str, help="Objetivo para pipeline TeamWork")

    # Cenarios
    parser.add_argument("--scenario", "-s", action="store_true", help="Gerar cenario real (preenche goal automaticamente)")

    # Projetos
    parser.add_argument("--projects", "-p", action="store_true", help="Lista projetos gerados")
    parser.add_argument("--view-file", nargs=2, metavar=("PROJETO", "ARQUIVO"), help="Exibe conteudo de arquivo de projeto")

    # Historico
    parser.add_argument("--history", nargs="?", const="list", default=None, help="Historico de debates (sem args: lista; com numero: detalhes)")

    # Conhecimento
    parser.add_argument("--knowledge", "-k", action="store_true", help="Mostra base de conhecimento")

    # Auditoria
    parser.add_argument("--audit", action="store_true", help="Auditoria de integridade (Livro-Verdade)")

    # Servidor
    parser.add_argument("--no-server", action="store_true", help="Nao iniciar servidor automaticamente")

    # Parametros do modelo
    parser.add_argument("--ctx", type=int, default=8192, help="Contexto do modelo (default: 8192)")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modelo Ollama (default: auto-discovery)")

    args = parser.parse_args()

    # Auto-start do servidor (se necessario e permitido)
    needs_server = any([args.topic, args.autonomous, args.engineering, args.content,
                        args.scenario, args.projects, args.view_file, args.audit])
    if needs_server and not args.no_server:
        if not _ensure_server_running():
            return

    # --- Comandos standalone (nao precisam de WebSocket) ---

    if args.history is not None:
        if args.history == "list":
            asyncio.run(_show_history())
        else:
            try:
                idx = int(args.history) - 1
                asyncio.run(_show_history(detail_index=idx))
            except ValueError:
                print(f"  {_c(ICON_X, RED)} Indice invalido: {args.history}")
        return

    if args.knowledge:
        asyncio.run(_show_knowledge())
        return

    if args.projects:
        asyncio.run(_show_projects())
        return

    if args.view_file:
        asyncio.run(_view_file(args.view_file[0], args.view_file[1]))
        return

    if args.audit:
        asyncio.run(_run_audit())
        return

    # --- Modos que precisam de WebSocket ou HTTP ---

    if args.scenario:
        mode = "content" if args.content else "engineering"
        goal = asyncio.run(_fill_random_scenario(mode))
        if not goal:
            return
        if args.engineering or args.content:
            asyncio.run(run_teamwork(mode, goal, args.model))
            return
        # Se so --scenario sem modo, perguntar o que fazer
        print(f"  {_c('Topico gerado:', BOLD)} {goal[:80]}")
        print()
        print(f"  {_c('1', BOLD + GREEN)}  Iniciar debate sobre este topico")
        print(f"  {_c('2', BOLD + GREEN)}  Iniciar Engenharia (TeamWork)")
        print(f"  {_c('3', BOLD + MAGENTA)} Iniciar Artigo (TeamWork)")
        print()
        choice = input("  Escolha: ").strip()
        if choice == "2":
            asyncio.run(run_teamwork("engineering", goal, args.model))
        elif choice == "3":
            asyncio.run(run_teamwork("content", goal, args.model))
        else:
            asyncio.run(run_single(goal, args.turns, args.ctx, args.model))
        return

    if args.engineering:
        goal = args.goal
        if not goal:
            goal = input("  Objetivo da engenharia: ").strip()
        if not goal:
            print(f"  {_c(ICON_X, RED)} Objetivo nao pode ser vazio.")
            return
        asyncio.run(run_teamwork("engineering", goal, args.model))
        return

    if args.content:
        goal = args.goal
        if not goal:
            goal = input("  Tema do artigo: ").strip()
        if not goal:
            print(f"  {_c(ICON_X, RED)} Tema nao pode ser vazio.")
            return
        asyncio.run(run_teamwork("content", goal, args.model))
        return

    if args.autonomous:
        asyncio.run(run_autonomous(args.hours, args.ctx, args.model))
        return

    if args.topic:
        asyncio.run(run_single(args.topic, args.turns, args.ctx, args.model))
        return

    # --- Modo interativo ---

    _print_banner_interactive()
    choice = input("  Escolha: ").strip()

    if choice == "1":
        topic = input("  Topico do debate: ").strip()
        if not topic:
            print(f"\n  {_c(ICON_X, RED)} Topico nao pode ser vazio.")
            return
        asyncio.run(run_single(topic, args.turns, args.ctx, args.model))

    elif choice == "2":
        hours = input("  Duracao em horas (default 8): ").strip()
        hours = float(hours) if hours else 8.0
        asyncio.run(run_autonomous(hours, args.ctx, args.model))

    elif choice == "3":
        goal = input("  Objetivo da engenharia: ").strip()
        if not goal:
            print(f"\n  {_c(ICON_X, RED)} Objetivo nao pode ser vazio.")
            return
        asyncio.run(run_teamwork("engineering", goal, args.model))

    elif choice == "4":
        goal = input("  Tema do artigo: ").strip()
        if not goal:
            print(f"\n  {_c(ICON_X, RED)} Tema nao pode ser vazio.")
            return
        asyncio.run(run_teamwork("content", goal, args.model))

    elif choice == "5":
        mode = input("  Modo (1=Engenharia, 2=Artigo) [1]: ").strip()
        mode = "content" if mode == "2" else "engineering"
        goal = asyncio.run(_fill_random_scenario(mode))
        if goal:
            print(f"\n  {_c('Topico:', BOLD)} {goal[:80]}")
            run = input("  Iniciar? (s/n): ").strip().lower()
            if run in ("s", "sim", "y", "yes", ""):
                asyncio.run(run_teamwork(mode, goal, args.model))

    elif choice == "6":
        asyncio.run(_show_history())

    elif choice == "7":
        asyncio.run(_show_projects())

    elif choice == "8":
        asyncio.run(_show_knowledge())

    elif choice == "9":
        asyncio.run(_run_audit())

    else:
        topic = choice
        asyncio.run(run_single(topic, args.turns, args.ctx, args.model))


if __name__ == "__main__":
    main()
