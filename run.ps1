# THz Room - Motor Multiagente Local (PowerShell)
#
# Uso:
#   .\run.ps1                           Menu interativo
#   .\run.ps1 server                    Inicia o servidor
#   .\run.ps1 client "topico"           Debate sob demanda
#   .\run.ps1 autonomous [horas]        Sessao autonoma (default 8h)

param(
    [Parameter(Position=0)]
    [ValidateSet("server", "client", "autonomous", "help", "")]
    [string]$Action = "",

    [Parameter(Position=1)]
    [string]$Arg1 = "",

    [string]$Model = "",
    [int]$Turns = 18,
    [int]$Ctx = 8192
)

$ErrorActionPreference = "Stop"

function Show-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║   THz Room - Motor Multiagente       ║" -ForegroundColor Cyan
    Write-Host "  ║   8 LLMs debatendo sobre tecnologia  ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Help {
    Show-Banner
    Write-Host "  Uso:" -ForegroundColor Yellow
    Write-Host "    .\run.ps1                              Menu interativo"
    Write-Host "    .\run.ps1 server                       Inicia o servidor"
    Write-Host "    .\run.ps1 client 'topico do debate'    Debate sob demanda"
    Write-Host "    .\run.ps1 autonomous                   Sessao 8h"
    Write-Host "    .\run.ps1 autonomous 4                 Sessao 4h"
    Write-Host ""
    Write-Host "  Opcoes:" -ForegroundColor Yellow
    Write-Host "    -Model 'qwen2.5:7b'                   Modelo Ollama especifico"
    Write-Host "    -Turns 18                              Max turnos por debate"
    Write-Host "    -Ctx 8192                              Tamanho do contexto"
    Write-Host ""
    Write-Host "  Exemplos:" -ForegroundColor Yellow
    Write-Host "    .\run.ps1 client 'Kafka vs RabbitMQ' -Model 'qwen2.5:7b'"
    Write-Host "    .\run.ps1 autonomous 12 -Ctx 16384"
    Write-Host ""
}

function Start-Server {
    Show-Banner
    Write-Host "  [SERVER] Iniciando FastAPI + WebSocket..." -ForegroundColor Green
    Write-Host "  [SERVER] Porta: 8000" -ForegroundColor Gray
    Write-Host "  [SERVER] Ctrl+C para parar" -ForegroundColor Gray
    Write-Host ""
    python server.py
}

function Start-Client {
    param([string]$Topic)

    Show-Banner

    if (-not $Topic) {
        $Topic = Read-Host "  Topico do debate"
        if (-not $Topic) {
            Write-Host "  [ERRO] Topico nao pode ser vazio." -ForegroundColor Red
            return
        }
    }

    Write-Host "  [CLIENT] Topico: $Topic" -ForegroundColor Green
    Write-Host "  [CLIENT] Turnos: $Turns | Ctx: $Ctx | Modelo: $(if ($Model) { $Model } else { 'auto' })" -ForegroundColor Gray
    Write-Host ""

    $args = @("client.py", "--topic", $Topic, "--turns", $Turns, "--ctx", $Ctx)
    if ($Model) { $args += "--model"; $args += $Model }
    python @args
}

function Start-Autonomous {
    param([int]$Hours)

    Show-Banner

    if ($Hours -le 0) {
        $input = Read-Host "  Duracao em horas (default: 8)"
        $Hours = if ($input) { [int]$input } else { 8 }
    }

    Write-Host "  [AUTONOMO] Duracao: ${Hours}h" -ForegroundColor Green
    Write-Host "  [AUTONOMO] Turnos/debate: $Turns | Ctx: $Ctx | Modelo: $(if ($Model) { $Model } else { 'auto' })" -ForegroundColor Gray
    Write-Host "  [AUTONOMO] Pausa: 10min entre debates" -ForegroundColor Gray
    Write-Host "  [AUTONOMO] Ollama gera topicos automaticamente" -ForegroundColor Gray
    Write-Host "  [AUTONOMO] Resumo gerado ao final" -ForegroundColor Gray
    Write-Host "  [AUTONOMO] Ctrl+C para parar antecipadamente" -ForegroundColor Yellow
    Write-Host ""

    $args = @("client.py", "--autonomous", "--hours", $Hours, "--ctx", $Ctx)
    if ($Model) { $args += "--model"; $args += $Model }
    python @args
}

# === MAIN ===

switch ($Action) {
    "server"     { Start-Server }
    "client"     { Start-Client -Topic $Arg1 }
    "autonomous" {
        $hours = if ($Arg1) { [int]$Arg1 } else { 0 }
        Start-Autonomous -Hours $hours
    }
    "help"       { Show-Help }
    ""           {
        # Menu interativo
        Show-Banner
        Write-Host "  Escolha o modo:" -ForegroundColor Yellow
        Write-Host "    1 - Servidor (inicia o backend)"
        Write-Host "    2 - Cliente (debate sob demanda)"
        Write-Host "    3 - Autonomo (sessao de debates)"
        Write-Host "    0 - Sair"
        Write-Host ""

        $choice = Read-Host "  Opcao"

        switch ($choice) {
            "1" { Start-Server }
            "2" { Start-Client -Topic "" }
            "3" { Start-Autonomous -Hours 0 }
            "0" { Write-Host "  Adeus!" -ForegroundColor Cyan }
            default { Write-Host "  Opcao invalida." -ForegroundColor Red }
        }
    }
}
