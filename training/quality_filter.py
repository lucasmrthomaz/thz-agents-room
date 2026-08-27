"""
THZ Minds — Quality Filter
Filtra dados de treinamento para manter apenas exemplos de alta qualidade.
"""

import json
import logging
import os
import sys
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

INPUT_DIR = "training/datasets"
OUTPUT_DIR = "training/datasets_filtered"

# Thresholds de qualidade
MIN_WORDS = 50
MAX_WORDS = 2000
MIN_ARGUMENT_LENGTH = 100


def is_high_quality(example: dict) -> bool:
    """Verifica se um exemplo e de alta qualidade."""
    try:
        conversations = example.get("conversations", [])
        if len(conversations) != 3:
            return False

        # Verificar se tem system, human, gpt
        roles = [c["from"] for c in conversations]
        if roles != ["system", "human", "gpt"]:
            return False

        # Verificar conteudo do GPT
        gpt_content = conversations[2]["value"]
        try:
            data = json.loads(gpt_content)
            argument = data.get("argument", "")
            status = data.get("status", "")

            # Verificar status valido
            if status not in ("CONTINUE", "CONSENSUS"):
                return False

            # Verificar tamanho do argumento
            word_count = len(argument.split())
            if word_count < MIN_WORDS:
                return False
            if word_count > MAX_WORDS:
                return False

            # Verificar comprimento minimo
            if len(argument) < MIN_ARGUMENT_LENGTH:
                return False

            # Verificar se nao e plagio (argumentos muito genericos)
            generic_phrases = [
                "e uma questao importante",
                "devemos considerar",
                "ha varios pontos a serem analisados",
                "e necessario uma analise mais aprofundada",
            ]
            arg_lower = argument.lower()
            if any(phrase in arg_lower for phrase in generic_phrases):
                if word_count < 100:  # Muito generico e curto
                    return False

            return True

        except (json.JSONDecodeError, KeyError):
            return False

    except Exception:
        return False


def filter_dataset(input_file: str, output_file: str) -> int:
    """Filtra um dataset mantendo apenas exemplos de alta qualidade."""
    filtered = 0
    total = 0

    with open(input_file, "r", encoding="utf-8") as f:
        examples = [json.loads(line) for line in f if line.strip()]

    total = len(examples)
    high_quality = [ex for ex in examples if is_high_quality(ex)]
    filtered = len(high_quality)

    # Salvar filtrado
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for ex in high_quality:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    return total, filtered


def main():
    """Filtra todos os datasets."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(INPUT_DIR):
        logger.error(f"[FILTER] Diretorio nao encontrado: {INPUT_DIR}")
        logger.info("[FILTER] Execute primeiro: python training/export_dataset.py")
        return

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".jsonl")]
    if not files:
        logger.error("[FILTER] Nenhum arquivo .jsonl encontrado")
        return

    for filename in files:
        input_file = os.path.join(INPUT_DIR, filename)
        output_file = os.path.join(OUTPUT_DIR, filename)

        total, filtered = filter_dataset(input_file, output_file)
        reduction = ((total - filtered) / total * 100) if total > 0 else 0

        logger.info(f"[FILTER] {filename}: {filtered}/{total} exemplos ({reduction:.1f}% removidos)")

    logger.info(f"\n[FILTER] Datasets filtrados salvos em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
