"""
THZ Minds — Train QLoRA
Script de treinamento fine-tuning por agente usando QLoRA.
"""

import os
import sys
import json
import logging
import yaml
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Configuracao padrao (pode ser sobrescrita por config.yaml)
DEFAULT_CONFIG = {
    "base_model": "unsloth/qwen2.5-7b-instruct-bnb-4bit",
    "max_seq_length": 1024,
    "lora_rank": 8,
    "lora_alpha": 16,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "training_args": {
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "num_train_epochs": 3,
        "learning_rate": 2e-4,
        "fp16": True,
        "bf16": False,
        "optim": "adamw_8bit",
        "save_strategy": "epoch",
        "output_dir": "training/outputs",
        "logging_steps": 10,
        "warmup_steps": 5,
    },
    "max_examples": 1000,
    "min_words": 50,
}


def load_config(config_path: str = None) -> dict:
    """Carrega configuracao de treinamento."""
    config = DEFAULT_CONFIG.copy()

    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f)
            if user_config:
                config.update(user_config)
                logger.info(f"[CONFIG] Configuracao carregada de {config_path}")

    return config


def check_requirements():
    """Verifica dependencias necessarias."""
    missing = []
    try:
        import torch
        logger.info(f"[CHECK] PyTorch {torch.__version__}")
        if not torch.cuda.is_available():
            logger.warning("[CHECK] CUDA nao disponivel! Treinamento sera muito lento.")
    except ImportError:
        missing.append("torch")

    try:
        import unsloth
        logger.info(f"[CHECK] Unsloth {unsloth.__version__}")
    except ImportError:
        missing.append("unsloth")

    try:
        import trl
        logger.info(f"[CHECK] TRL {trl.__version__}")
    except ImportError:
        missing.append("trl")

    try:
        import peft
        logger.info(f"[CHECK] PEFT {peft.__version__}")
    except ImportError:
        missing.append("peft")

    try:
        import datasets
        logger.info(f"[CHECK] Datasets {datasets.__version__}")
    except ImportError:
        missing.append("datasets")

    if missing:
        logger.error(f"[CHECK] Dependencias faltando: {', '.join(missing)}")
        logger.info("[CHECK] Instale com: pip install " + " ".join(missing))
        return False

    return True


def train_agent(agent_name: str, config: dict) -> bool:
    """Treina fine-tuning para um agente especifico."""
    try:
        import torch
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset

        logger.info(f"\n{'='*60}")
        logger.info(f"[TRAIN] Treinando agente: {agent_name}")
        logger.info(f"{'='*60}")

        # Carregar modelo
        logger.info(f"[TRAIN] Carregando modelo: {config['base_model']}")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=config["base_model"],
            max_seq_length=config["max_seq_length"],
            dtype=None,
            load_in_4bit=True,
        )

        # Configurar LoRA
        logger.info(f"[TRAIN] Configurando LoRA (rank={config['lora_rank']})")
        model = FastLanguageModel.get_peft_model(
            model,
            r=config["lora_rank"],
            target_modules=config["target_modules"],
            lora_alpha=config["lora_alpha"],
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=3407,
        )

        # Carregar dataset
        dataset_file = f"training/datasets/{agent_name.lower().replace(' ', '_')}.jsonl"
        if not os.path.exists(dataset_file):
            logger.error(f"[TRAIN] Dataset nao encontrado: {dataset_file}")
            logger.info("[TRAIN] Execute primeiro: python training/export_dataset.py")
            return False

        logger.info(f"[TRAIN] Carregando dataset: {dataset_file}")
        dataset = load_dataset("json", data_files=dataset_file, split="train")

        # Limitar exemplos
        if len(dataset) > config.get("max_examples", 1000):
            dataset = dataset.shuffle(seed=42).select(range(config["max_examples"]))
            logger.info(f"[TRAIN] Dataset limitado a {config['max_examples']} exemplos")

        # Configurar treinamento
        training_config = config["training_args"].copy()
        training_config["output_dir"] = f"training/outputs/{agent_name.lower().replace(' ', '_')}"

        os.makedirs(training_config["output_dir"], exist_ok=True)

        args = TrainingArguments(**training_config)

        # Criar trainer
        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            dataset_text_field="conversations",
            max_seq_length=config["max_seq_length"],
            args=args,
        )

        # Treinar
        logger.info(f"[TRAIN] Iniciando treinamento ({len(dataset)} exemplos)...")
        trainer.train()

        # Salvar adapter
        adapter_dir = f"training/adapters/{agent_name.lower().replace(' ', '_')}"
        os.makedirs(adapter_dir, exist_ok=True)
        model.save_pretrained(adapter_dir)
        tokenizer.save_pretrained(adapter_dir)
        logger.info(f"[TRAIN] Adapter salvo em: {adapter_dir}")

        return True

    except Exception as e:
        logger.error(f"[TRAIN] Erro ao treinar {agent_name}: {e}")
        return False


def main():
    """Treina fine-tuning para todos os agentes."""
    if not check_requirements():
        sys.exit(1)

    # Carregar configuracao
    config_path = "training/config.yaml"
    config = load_config(config_path)

    # Agentes para treinar
    agents = ["Arquiteto", "SRE", "DevOps", "DBA", "Security", "PO", "Scrum Master", "Gerente"]

    results = {}
    for agent in agents:
        success = train_agent(agent, config)
        results[agent] = success

    # Resumo
    logger.info("\n" + "="*60)
    logger.info("[TRAIN] RESUMO DO TREINAMENTO")
    logger.info("="*60)

    for agent, success in results.items():
        status = "OK" if success else "FALHOU"
        logger.info(f"  {agent}: {status}")

    success_count = sum(results.values())
    logger.info(f"\nTotal: {success_count}/{len(agents)} agentes treinados com sucesso")


if __name__ == "__main__":
    main()
