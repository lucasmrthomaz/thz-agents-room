"""
Cliente CLI para THz Minds - Motor Multiagente Local
Modos: Single (sob demanda) + Autonomous (sessao noturna) + Historico
Protocolo: WebSocket (RFC 6455) / JSON (RFC 8259)

Funcionalidades equivalentes a GUI:
- Resumo de debates ao final
- Loading/progresso por turno
- Historico de debates recentes
- Base de conhecimento
- Countdown de pausa entre debates
"""

import asyncio
import argparse
import json
import sys
import time
import websockets

URI = "ws://127.0.0.1:8000/ws/debate"

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


def _c(text: str, color: str, bold: bool = False) -> str:
    """Aplica cor (e opcionalmente negrito) a um texto."""
    prefix = f"{BOLD}" if bold else ""
    return f"{prefix}{color}{text}{RESET}"


def _agent_color(agent_name: str) -> str:
    """Retorna a cor associada ao agente."""
    return AGENT_COLORS.get(agent_name, WHITE)


def _status_color(status: str) -> str:
    """Retorna a cor associada ao status."""
    return STATUS_COLORS.get(status, WHITE)


def _print_logo():
    """Exibe o logo ASCII do THZ Minds."""
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
    """Banner para modo single."""
    _print_logo()
    print(f"  {_c(ICON_TARGET, GREEN)} {_c('MODO SINGLE', BOLD + GREEN)}  {_c('— Debate sob demanda', DIM)}")
    print()
    print(f"  {_c('Topico:', BOLD)} {topic}")
    print(f"  {_c('Turnos:', BOLD)} {max_turns}")
    print(f"  {_c('Contexto:', BOLD)} {num_ctx}")
    print(f"  {_c('Modelo:', BOLD)} {model or 'auto-discovery'}")
    print(f"\n  {'━'*76}\n")


def _print_banner_autonomous(duration_hours: float, num_ctx: int, model: str):
    """Banner para modo autonomo."""
    _print_logo()
    print(f"  {_c(ICON_HOUR, YELLOW)} {_c('MODO AUTONOMO', BOLD + YELLOW)}  {_c('— Sessao noturna', DIM)}")
    print()
    print(f"  {_c('Duracao:', BOLD)} {duration_hours}h")
    print(f"  {_c('Contexto:', BOLD)} {num_ctx}")
    print(f"  {_c('Modelo:', BOLD)} {model or 'auto-discovery'}")
    print(f"  {_c('Pausa:', BOLD)} 1 min entre debates")
    print(f"\n  {'━'*76}\n")


def _print_banner_interactive():
    """Banner para modo interativo."""
    _print_logo()
    print(f"  {_c(ICON_GEAR, MAGENTA)} {_c('MODO INTERATIVO', BOLD + MAGENTA)}")
    print()
    print(f"  {_c('1', BOLD + CYAN)}  Debate sob demanda")
    print(f"  {_c('2', BOLD + YELLOW)}  Sessao autonoma (noturna)")
    print(f"  {_c('3', BOLD + GREEN)}  Ver historico de debates")
    print(f"  {_c('4', BOLD + BLUE)}  Ver base de conhecimento")
    print()


def _print_progress(current: int, total: int, agent: str):
    """Exibe barra de progresso."""
    pct = int((current / total) * 100) if total > 0 else 0
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)
    color = _agent_color(agent)
    print(f"\r  {_c(f'[{bar}]', DIM)} {_c(f'{pct}%', DIM)} Turno {_c(str(current), BOLD)}/{total}", end="", flush=True)


def _print_loading(message: str, frame: int):
    """Exibe indicador de loading."""
    icon = LOADING_FRAMES[frame % len(LOADING_FRAMES)]
    print(f"\r  {_c(icon, CYAN)} {message}...", end="", flush=True)


def _print_summary(summary: str):
    """Exibe resumo do debate formatado."""
    if not summary:
        return
    print(f"\n  {_c(ICON_BULB, YELLOW)} {_c('RESUMO DO DEBATE:', BOLD + YELLOW)}")
    for line in summary.split("\n"):
        print(f"  {_c(line, DIM)}")
    print()


def _print_debate_complete(reason: str, total_turns: int, summary: str = ""):
    """Exibe mensagem de debate encerrado com resumo."""
    if reason == "topic_exhausted":
        print(f"\n  {_c(ICON_WARNING, RED)} {_c('DEBATE ENCERRADO', BOLD + RED)}  {_c('Topico exaurido', DIM)}")
    elif reason == "consensus":
        print(f"\n  {_c(ICON_CHECK, GREEN)} {_c('DEBATE ENCERRADO', BOLD + GREEN)}  {_c('Consenso', DIM)}  {_c(f'Turnos: {total_turns}', DIM)}")
    else:
        print(f"\n  {_c(ICON_HOUR, YELLOW)} {_c('DEBATE ENCERRADO', BOLD + YELLOW)}  {_c('Timeout', DIM)}  {_c(f'Turnos: {total_turns}', DIM)}")

    _print_summary(summary)
    print(f"  {'━'*76}\n")


def _print_pause_countdown(duration: int):
    """Exibe countdown da pausa."""
    print(f"\n  {_c(ICON_CLOCK, YELLOW)} {_c('PAUSA', BOLD + YELLOW)} — Proximo debate em {duration}s...")
    for remaining in range(duration, 0, -1):
        mins = remaining // 60
        secs = remaining % 60
        time_str = f"{mins:02d}:{secs:02d}" if mins > 0 else f"{secs}s"
        print(f"\r  {_c(ICON_CLOCK, YELLOW)} {_c('PAUSA', BOLD + YELLOW)} — Proximo debate em {time_str}  ", end="", flush=True)
        time.sleep(1)
    print(f"\r  {_c(ICON_CHECK, GREEN)} Iniciando proximo debate...                    ")


def _print_session_complete(data: dict):
    """Exibe resumo da sessao encerrada."""
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


async def run_single(topic: str, max_turns: int, num_ctx: int, model: str = None):
    """Modo single: um debate sob demanda."""
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
    """Modo autonomous: sessao noturna de debates."""
    payload = {
        "mode": "autonomous",
        "duration_hours": duration_hours,
        "num_ctx": num_ctx,
        "model": model
    }
    _print_banner_autonomous(duration_hours, num_ctx, model)
    await _run_session(payload)


async def _run_session(payload: dict):
    """Conecta ao WebSocket e processa eventos."""
    try:
        async with websockets.connect(URI) as ws:
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

                        # Limpar loading
                        print(f"\r{'':80}\r", end="", flush=True)

                        print(f"  {_c(ICON_BRAIN, color)} {_c(agent, BOLD + color)}:")
                        print(f"  {arg}")
                        print(f"  {_c(f'[{status}]', BOLD + scolor)}")
                        print(f"  {'─'*76}")

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
        print(f"  {_c('Dica:', DIM)} Verifique se o {_c('server.py', BOLD)} esta rodando.")


def main():
    parser = argparse.ArgumentParser(
        description="THz Minds - Cliente CLI para debates multiagente",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python client.py --topic 'Kafka vs RabbitMQ para fila de eventos'\n"
            "  python client.py --autonomous --hours 8\n"
            "  python client.py --autonomous --hours 4 --model qwen2.5:7b\n"
            "  python client.py --history\n"
        )
    )

    parser.add_argument("--topic", "-t", type=str, help="Topico para debate (modo single)")
    parser.add_argument("--autonomous", "-a", action="store_true", help="Modo autonomo (sessao noturna)")
    parser.add_argument("--hours", type=float, default=8.0, help="Duracao em horas (default: 8)")
    parser.add_argument("--turns", type=int, default=48, help="Max turnos por debate (default: 48)")
    parser.add_argument("--ctx", type=int, default=8192, help="Contexto do modelo (default: 8192)")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modelo Ollama (default: auto-discovery)")
    parser.add_argument("--history", action="store_true", help="Mostra historico de debates recentes")

    args = parser.parse_args()

    if args.history:
        asyncio.run(_show_history())
    elif args.autonomous:
        asyncio.run(run_autonomous(args.hours, args.ctx, args.model))
    elif args.topic:
        asyncio.run(run_single(args.topic, args.turns, args.ctx, args.model))
    else:
        _print_banner_interactive()
        choice = input("  Escolha: ").strip()

        if choice == "2":
            hours = input("  Duracao em horas (default 8): ").strip()
            hours = float(hours) if hours else 8.0
            asyncio.run(run_autonomous(hours, args.ctx, args.model))
        elif choice == "3":
            asyncio.run(_show_history())
        elif choice == "4":
            asyncio.run(_show_knowledge())
        else:
            topic = input("  Topico do debate: ").strip()
            if not topic:
                print(f"\n  {_c(ICON_X, RED)} {_c('Topico nao pode ser vazio.', RED)}")
                return
            asyncio.run(run_single(topic, args.turns, args.ctx, args.model))


async def _show_history():
    """Mostra historico de debates recentes."""
    # Ler direto do banco SQLite
    import aiosqlite
    try:
        async with aiosqlite.connect("data/thz-room-cortex.db") as db:
            cursor = await db.execute("""
                SELECT id, topic, created_at,
                       (SELECT COUNT(*) FROM messages WHERE conversation_id = conversations.id) as total_turns
                FROM conversations
                ORDER BY created_at DESC
                LIMIT 15
            """)
            rows = await cursor.fetchall()

            _print_logo()
            print(f"  {_c(ICON_SCROLL, CYAN)} {_c('HISTORICO DE DEBATES', BOLD + CYAN)}")
            print(f"  {'━'*76}\n")

            if not rows:
                print(f"  {_c('Nenhum debate encontrado.', DIM)}")
            else:
                for row in rows:
                    conv_id, topic, created_at, total_turns = row
                    # Formatar data
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at)
                        date_str = dt.strftime("%d/%m %H:%M")
                    except (ValueError, TypeError):
                        date_str = created_at[:16] if created_at else "?"

                    print(f"  {_c(date_str, DIM)}  {_c(topic[:60], WHITE)}  {_c(f'{total_turns} turnos', DIM)}")

            print(f"\n  {'━'*76}\n")

    except Exception as e:
        print(f"\n  {_c(ICON_X, RED)} {_c('Erro ao carregar historico:', RED)} {e}")


async def _show_knowledge():
    """Mostra base de conhecimento (topicos discutidos)."""
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


if __name__ == "__main__":
    main()
