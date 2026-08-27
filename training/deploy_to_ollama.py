"""
THZ Minds — Deploy para Ollama
Merge LoRA adapter + export GGUF + criar Modelfile + registrar no Ollama.
"""

import os
import sys
import subprocess
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Configuracao dos agentes
AGENT_CONFIGS = {
    "arquiteto": {
        "role": "Software Architect",
        "system_prompt": (
            "Voce e um arquiteto de software pragmatico focado em simplicidade, "
            "manutenibilidade e custo de infraestrutura (KISS / YAGNI). "
            "Defenda abordagens diretas e desafie complexidade acidental."
        ),
    },
    "sre": {
        "role": "Site Reliability Engineer",
        "system_prompt": (
            "Voce e um SRE focado em tolerancia a falhas, sistemas distribuidos, "
            "concorrencia, picos de carga e observabilidade. "
            "Identifique SPOF, locks de banco e gargalos de escalabilidade."
        ),
    },
    "devops": {
        "role": "DevOps Engineer",
        "system_prompt": (
            "Voce e um DevOps focado em CI/CD, infraestrutura como codigo, "
            "automacao, containers e monitoramento. "
            "Question complexidade de pipelines e custos de infra."
        ),
    },
    "dba": {
        "role": "Database Specialist",
        "system_prompt": (
            "Voce e um especialista em bancos de dados focado em modelagem relacional, "
            "normalizacao, performance de queries, indexes e concorrencia. "
            "Question escolhas de NoSQL quando o problema e relacional."
        ),
    },
    "security": {
        "role": "Security Specialist",
        "system_prompt": (
            "Voce e um especialista em seguranca focado em vulnerabilidades, "
            "autenticacao, autorizacao e boas praticas. "
            "Aponte riscos de injecao, exposicao de dados e autenticacao fraca."
        ),
    },
    "po": {
        "role": "Product Owner",
        "system_prompt": (
            "Voce e um Product Owner focado em valor de negocio, ROI, "
            "priorizacao e alinhamento com objetivos estrategicos. "
            "Question se a solucao tecnica atende ao usuario final."
        ),
    },
    "scrum_master": {
        "role": "Scrum Master",
        "system_prompt": (
            "Voce e um Scrum Master focado em processo, impedimentos "
            "e fluxo de trabalho. Identifique gargalos de comunicacao."
        ),
    },
    "gerente": {
        "role": "Project Manager",
        "system_prompt": (
            "Voce e um Gerente de Projeto focado em prazo, recursos, "
            "riscos e orcamento. Aponte impacto em timeline e capacidade da equipe."
        ),
    },
}

RESPECT_RULES = """
REGRAS DE RESPETTO (OBRIGATORIO):
- So responda sobre o que foi dito no turno anterior.
- Referencie o argumento anterior explicitamente quando contra-argumentar.
- NAO repita os mesmos pontos ja discutidos.
- NAO introduza topicos fora do escopo da sua area de expertise.
- NAO seja condescendente; traga numeros, hardware, limites operacionais.
- Apenas discuta nos 9 temas permitidos: programacao, arquitetura, git, SO,
  lideranca, HCI, DevOps, banco de dados, seguranca.
"""


def merge_and_export(agent_name: str, adapter_dir: str, output_dir: str) -> bool:
    """Merge LoRA adapter com modelo base e exporta GGUF."""
    try:
        logger.info(f"[DEPLOY] Merge + export para {agent_name}...")

        # Verificar se adapter existe
        if not os.path.exists(adapter_dir):
            logger.error(f"[DEPLOY] Adapter nao encontrado: {adapter_dir}")
            return False

        # Comando para merge e export
        # Nota: Requer llama.cpp instalado
        cmd = [
            sys.executable, "-m", "unsloth.save_pretrained_gguf",
            "--model", "unsloth/qwen2.5-7b-instruct-bnb-4bit",
            "--adapter", adapter_dir,
            "--output", output_dir,
            "--quantization_method", "q4_k_m",
        ]

        logger.info(f"[DEPLOY] Executando: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"[DEPLOY] Erro no merge: {result.stderr}")
            return False

        logger.info(f"[DEPLOY] GGUF exportado para: {output_dir}")
        return True

    except Exception as e:
        logger.error(f"[DEPLOY] Erro no merge: {e}")
        return False


def create_modelfile(agent_name: str, gguf_path: str, config: dict) -> str:
    """Cria Modelfile para o Ollama."""
    modelfile_content = f"""FROM {gguf_path}

SYSTEM \"\"\"{config['system_prompt']}

DIRETIVAS OBRIGATORIAS:
- Idioma: Responda EXCLUSIVAMENTE em Portugues do Brasil (pt-BR).
- Formato: Responda estritamente no esquema JSON com 'argument' e 'status'.
- PLAGIO: NAO copie trechos de outros agentes. Use suas proprias palavras.
- ORIGINALIDADE: Traga argumentos NOVOS baseados na sua expertise.

{RESPECT_RULES}\"\"\"

PARAMETER temperature 0.5
PARAMETER repeat_penalty 1.15
PARAMETER num_ctx 8192
"""
    return modelfile_content


def register_in_ollama(agent_name: str, modelfile_path: str) -> bool:
    """Registra modelo no Ollama."""
    try:
        model_name = f"thz-{agent_name}"

        cmd = ["ollama", "create", model_name, "-f", modelfile_path]
        logger.info(f"[DEPLOY] Registrando no Ollama: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"[DEPLOY] Erro ao registrar: {result.stderr}")
            return False

        logger.info(f"[DEPLOY] Modelo registrado: {model_name}")
        return True

    except FileNotFoundError:
        logger.error("[DEPLOY] Ollama nao encontrado. Instale: https://ollama.ai")
        return False
    except Exception as e:
        logger.error(f"[DEPLOY] Erro ao registrar: {e}")
        return False


def deploy_agent(agent_name: str) -> bool:
    """Deploy completo para um agente."""
    logger.info(f"\n{'='*60}")
    logger.info(f"[DEPLOY] Deploy do agente: {agent_name}")
    logger.info(f"{'='*60}")

    adapter_dir = f"training/adapters/{agent_name}"
    gguf_dir = f"training/gguf/{agent_name}"
    modelfile_dir = f"training/modelfiles"

    os.makedirs(gguf_dir, exist_ok=True)
    os.makedirs(modelfile_dir, exist_ok=True)

    # 1. Merge + Export GGUF
    if not merge_and_export(agent_name, adapter_dir, gguf_dir):
        return False

    # 2. Criar Modelfile
    gguf_files = [f for f in os.listdir(gguf_dir) if f.endswith(".gguf")]
    if not gguf_files:
        logger.error(f"[DEPLOY] Nenhum arquivo GGUF encontrado em {gguf_dir}")
        return False

    gguf_path = os.path.join(gguf_dir, gguf_files[0])
    config = AGENT_CONFIGS.get(agent_name, {"system_prompt": "Voce e um agente de debate."})
    modelfile_content = create_modelfile(agent_name, gguf_path, config)

    modelfile_path = os.path.join(modelfile_dir, f"Modelfile.{agent_name}")
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)
    logger.info(f"[DEPLOY] Modelfile criado: {modelfile_path}")

    # 3. Registrar no Ollama
    if not register_in_ollama(agent_name, modelfile_path):
        return False

    return True


def main():
    """Deploy de todos os agentes."""
    agents = list(AGENT_CONFIGS.keys())

    results = {}
    for agent in agents:
        success = deploy_agent(agent)
        results[agent] = success

    # Resumo
    logger.info("\n" + "="*60)
    logger.info("[DEPLOY] RESUMO DO DEPLOY")
    logger.info("="*60)

    for agent, success in results.items():
        status = "OK" if success else "FALHOU"
        logger.info(f"  {agent}: {status}")

    success_count = sum(results.values())
    logger.info(f"\nTotal: {success_count}/{len(agents)} agentes deployados com sucesso")

    if success_count > 0:
        logger.info("\nModelos disponiveis no Ollama:")
        for agent, success in results.items():
            if success:
                logger.info(f"  ollama run thz-{agent}")


if __name__ == "__main__":
    main()
