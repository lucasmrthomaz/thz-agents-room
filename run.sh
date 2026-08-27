#!/usr/bin/env bash
# THz Room - Motor Multiagente Local (Shell)
#
# Uso:
#   ./run.sh                           Menu interativo
#   ./run.sh server                    Inicia o servidor
#   ./run.sh client "topico"           Debate sob demanda
#   ./run.sh autonomous [horas]        Sessao autonoma (default 8h)

set -e

# Cores
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Defaults
TURNS=48
CTX=8192
MODEL=""

banner() {
    echo ""
    echo -e "${CYAN}  ╔══════════════════════════════════════╗"
    echo -e "  ║   THz Room - Motor Multiagente       ║"
    echo -e "  ║   8 LLMs debatendo sobre tecnologia  ║"
    echo -e "  ╚══════════════════════════════════════╝${NC}"
    echo ""
}

show_help() {
    banner
    echo -e "${YELLOW}  Uso:${NC}"
    echo "    ./run.sh                              Menu interativo"
    echo "    ./run.sh server                       Inicia o servidor"
    echo "    ./run.sh client 'topico do debate'    Debate sob demanda"
    echo "    ./run.sh autonomous                   Sessao 8h"
    echo "    ./run.sh autonomous 4                 Sessao 4h"
    echo ""
    echo -e "${YELLOW}  Exemplos:${NC}"
    echo "    ./run.sh client 'Kafka vs RabbitMQ' --model qwen2.5:7b"
    echo "    ./run.sh autonomous 12 --ctx 16384"
    echo ""
}

start_server() {
    banner
    echo -e "${GREEN}  [SERVER] Iniciando FastAPI + WebSocket...${NC}"
    echo -e "${GRAY}  [SERVER] Porta: 8000${NC}"
    echo -e "${GRAY}  [SERVER] Ctrl+C para parar${NC}"
    echo ""
    python3 server.py
}

start_gui() {
    banner
    echo -e "${GREEN}  [GUI] Iniciando interface grafica...${NC}"
    echo -e "${GRAY}  [GUI] Servidor inicia automaticamente${NC}"
    echo ""
    python3 main.py
}

start_client() {
    local topic="$1"
    banner

    if [ -z "$topic" ]; then
        read -p "  Topico do debate: " topic
        if [ -z "$topic" ]; then
            echo -e "${RED}  [ERRO] Topico nao pode ser vazio.${NC}"
            return 1
        fi
    fi

    echo -e "${GREEN}  [CLIENT] Topico: $topic${NC}"
    echo -e "${GRAY}  [CLIENT] Turnos: $TURNS | Ctx: $CTX | Modelo: ${MODEL:-auto}${NC}"
    echo ""

    python3 client.py --topic "$topic" --turns "$TURNS" --ctx "$CTX" ${MODEL:+--model "$MODEL"}
}

start_autonomous() {
    local hours="${1:-}"
    banner

    if [ -z "$hours" ] || [ "$hours" -le 0 ] 2>/dev/null; then
        read -p "  Duracao em horas (default: 8): " hours
        hours="${hours:-8}"
    fi

    echo -e "${GREEN}  [AUTONOMO] Duracao: ${hours}h${NC}"
    echo -e "${GRAY}  [AUTONOMO] Turnos/debate: $TURNS | Ctx: $CTX | Modelo: ${MODEL:-auto}${NC}"
    echo -e "${GRAY}  [AUTONOMO] Pausa: 10min entre debates${NC}"
    echo -e "${GRAY}  [AUTONOMO] Ollama gera topicos automaticamente${NC}"
    echo -e "${GRAY}  [AUTONOMO] Resumo gerado ao final${NC}"
    echo -e "${YELLOW}  [AUTONOMO] Ctrl+C para parar antecipadamente${NC}"
    echo ""

    python3 client.py --autonomous --hours "$hours" --ctx "$CTX" ${MODEL:+--model "$MODEL"}
}

# === PARSE ARGS ===
ACTION="${1:-}"
ARG1="${2:-}"

# Parse flags
while [[ $# -gt 0 ]]; do
    case $1 in
        --model) MODEL="$2"; shift 2 ;;
        --turns) TURNS="$2"; shift 2 ;;
        --ctx)   CTX="$2";   shift 2 ;;
        *)       shift ;;
    esac
done

# === MAIN ===
case "$ACTION" in
    gui)
        start_gui
        ;;
    server)
        start_server
        ;;
    client)
        start_client "$ARG1"
        ;;
    autonomous)
        start_autonomous "$ARG1"
        ;;
    help|--help|-h)
        show_help
        ;;
    "")
        # Modo padrao: inicia GUI
        start_gui
        ;;
    *)
        echo -e "${RED}  Comando invalido: $ACTION${NC}"
        show_help
        ;;
esac
