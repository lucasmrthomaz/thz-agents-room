"""
Cliente CLI para THz Room - Motor Multiagente Local
Modos: Single (sob demanda) + Autonomous (sessao noturna)
Protocolo: WebSocket (RFC 6455) / JSON (RFC 8259)
"""

import asyncio
import argparse
import json
import sys
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
BG_DARK = "\033[48;5;236m"

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

# Mapeamento de agentes para cores
AGENT_COLORS = {
    "Arquiteto":  CYAN,
    "SRE":        RED,
    "DevOps":     GREEN,
    "DBA":        YELLOW,
    "Security":   MAGENTA,
    "PO":         BLUE,
    "Scrum Master": WHITE,
    "Gerente":    "\033[38;5;208m",  # laranja
}

STATUS_COLORS = {
    "CONTINUE":   YELLOW,
    "CONSENSUS":  GREEN,
    "STOP":       RED,
}


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
    """Exibe o logo ASCII do THz Room."""
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
    print()


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
                        role = data.get('role', '?')
                        turn = data.get('turn', '?')
                        color = _agent_color(agent)
                        print(f"\n  {_c(f'Turno {turn}', DIM)} — {_c(agent, BOLD + color)}...", flush=True)

                    elif evt == "turn_end":
                        agent = data.get('agent', '?')
                        arg = data.get("argument", "Sem conteudo.")
                        status = data.get("status", "?")
                        color = _agent_color(agent)
                        scolor = _status_color(status)
                        print(f"\n  {_c(ICON_BRAIN, color)} {_c(agent, BOLD + color)}:")
                        print(f"  {arg}")
                        print(f"  {_c(f'[{status}]', BOLD + scolor)}")
                        print(f"  {'─'*76}")

                    elif evt == "debate_complete":
                        motivo = "Consenso" if data.get("reason") == "consensus" else "Timeout"
                        icon = ICON_CHECK if data.get("reason") == "consensus" else ICON_HOUR
                        color = GREEN if data.get("reason") == "consensus" else YELLOW
                        turns = data.get('total_turns', '?')
                        print(f"\n  {_c(icon, color)} {_c('DEBATE ENCERRADO', BOLD + color)}  {_c(f'{motivo}', DIM)}  {_c(f'Turnos: {turns}', DIM)}")
                        print(f"  {'━'*76}\n")

                    elif evt == "session_complete":
                        print(f"\n  {_c(ICON_STAR, YELLOW)} {_c('SESSAO ENCERRADA', BOLD + YELLOW)}")
                        print(f"  {_c('Total de debates:', BOLD)} {data.get('total_debates')}")
                        print(f"  {_c('Duracao:', BOLD)} {data.get('duration_hours')}h")
                        print(f"\n  {_c('Topicos discutidos:', BOLD)}")
                        for i, t in enumerate(data.get("topics", []), 1):
                            print(f"    {_c(str(i), CYAN)}. {t}")
                        print(f"\n  {_c('Resumo:', BOLD)}")
                        summary = data.get('summary', 'N/A')
                        for line in summary.split('\n'):
                            print(f"    {DIM}{line}{RESET}")
                        print(f"\n  {'━'*76}\n")
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
        description="THz Room - Cliente CLI para debates multiagente",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python client.py --topic 'Kafka vs RabbitMQ para fila de eventos'\n"
            "  python client.py --autonomous --hours 8\n"
            "  python client.py --autonomous --hours 4 --model qwen2.5:7b\n"
        )
    )

    parser.add_argument("--topic", "-t", type=str, help="Topico para debate (modo single)")
    parser.add_argument("--autonomous", "-a", action="store_true", help="Modo autonomo (sessao noturna)")
    parser.add_argument("--hours", type=float, default=8.0, help="Duracao em horas (default: 8)")
    parser.add_argument("--turns", type=int, default=48, help="Max turnos por debate (default: 48)")
    parser.add_argument("--ctx", type=int, default=8192, help="Contexto do modelo (default: 8192)")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modelo Ollama (default: auto-discovery)")

    args = parser.parse_args()

    if args.autonomous:
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
        else:
            topic = input("  Topico do debate: ").strip()
            if not topic:
                print(f"\n  {_c(ICON_X, RED)} {_c('Topico nao pode ser vazio.', RED)}")
                return
            asyncio.run(run_single(topic, args.turns, args.ctx, args.model))


if __name__ == "__main__":
    main()
