"""
Cliente CLI para THz Room - Motor Multiagente Local
Modos: Single (sob demanda) + Autonomous (sessao noturna)
Protocolo: WebSocket (RFC 6455) / JSON (RFC 8259)
"""

import asyncio
import argparse
import json
import websockets

URI = "ws://127.0.0.1:8000/ws/debate"


async def run_single(topic: str, max_turns: int, num_ctx: int, model: str = None):
    """Modo single: um debate sob demanda."""
    payload = {
        "mode": "single",
        "topic": topic,
        "max_turns": max_turns,
        "num_ctx": num_ctx,
        "model": model
    }

    print(f"\n[SINGLE] Iniciando debate...")
    print(f"[TOPICO]: {topic}")
    print(f"[CONFIG]: turnos={max_turns}, ctx={num_ctx}, modelo={model or 'auto'}")
    print("=" * 80)

    await _run_session(payload)


async def run_autonomous(duration_hours: float, num_ctx: int, model: str = None):
    """Modo autonomous: sessao noturna de debates."""
    payload = {
        "mode": "autonomous",
        "duration_hours": duration_hours,
        "num_ctx": num_ctx,
        "model": model
    }

    print(f"\n[AUTONOMO] Sessao noturna iniciada!")
    print(f"[DURACAO]: {duration_hours}h")
    print(f"[CONFIG]: ctx={num_ctx}, modelo={model or 'auto'}")
    print(f"[INFO] debates consecutivos com pausa de 10min entre eles")
    print("=" * 80)

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
                        print(f"\n{'='*80}")
                        print(f"[SESSAO] {data.get('session_id')}")
                        print(f"  Duracao: {data.get('duration_hours')}h")
                        print(f"  Modelo: {data.get('model')}")
                        print(f"{'='*80}")

                    elif evt == "debate_start":
                        num = data.get("debate_num", "?")
                        print(f"\n{'─'*80}")
                        print(f"[DEBATE {num}] {data.get('topic')}")
                        print(f"{'─'*80}")

                    elif evt == "turn_start":
                        print(f"\n  [{data['agent']} - {data['role']}] Turno {data['turn']}...", flush=True)

                    elif evt == "turn_end":
                        arg = data.get("argument", "Sem conteudo.")
                        status = data.get("status", "?")
                        print(f"\n  [{data['agent']}]:")
                        print(f"  {arg}")
                        print(f"  Status: [{status}]")
                        print(f"  {'-'*70}")

                    elif evt == "debate_complete":
                        motivo = "Consenso" if data.get("reason") == "consensus" else "Timeout"
                        print(f"\n  [DEBATE ENCERRADO] {motivo} | Turnos: {data.get('total_turns')}")

                    elif evt == "session_complete":
                        print(f"\n{'='*80}")
                        print(f"[SESSAO ENCERRADA]")
                        print(f"  Total de debates: {data.get('total_debates')}")
                        print(f"  Duracao: {data.get('duration_hours')}h")
                        print(f"\n  Topicos discutidos:")
                        for i, t in enumerate(data.get("topics", []), 1):
                            print(f"    {i}. {t}")
                        print(f"\n  Resumo:")
                        print(f"  {data.get('summary', 'N/A')}")
                        print(f"{'='*80}\n")
                        break

                    elif evt == "error":
                        print(f"\n[ERRO]: {data.get('message')}")
                        break

                except websockets.exceptions.ConnectionClosed:
                    print("\n[INFO] Conexao encerrada pelo servidor.")
                    break

    except ConnectionRefusedError:
        print(f"\n[FALHA] Nao foi possivel conectar a {URI}. O server.py esta rodando?")


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
    parser.add_argument("--turns", type=int, default=18, help="Max turnos por debate (default: 18)")
    parser.add_argument("--ctx", type=int, default=8192, help="Contexto do modelo (default: 8192)")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modelo Ollama (default: auto-discovery)")

    args = parser.parse_args()

    if args.autonomous:
        asyncio.run(run_autonomous(args.hours, args.ctx, args.model))
    elif args.topic:
        asyncio.run(run_single(args.topic, args.turns, args.ctx, args.model))
    else:
        # Modo interativo
        print("\n[THz ROOM] Motor Multiagente Local")
        print("1 - Debate sob demanda")
        print("2 - Sessao autonoma (noturna)")
        choice = input("\nEscolha: ").strip()

        if choice == "2":
            hours = input("Duracao em horas (default 8): ").strip()
            hours = float(hours) if hours else 8.0
            asyncio.run(run_autonomous(hours, args.ctx, args.model))
        else:
            topic = input("Topico do debate: ").strip()
            if not topic:
                print("[ERRO] Topico nao pode ser vazio.")
                return
            asyncio.run(run_single(topic, args.turns, args.ctx, args.model))


if __name__ == "__main__":
    main()
