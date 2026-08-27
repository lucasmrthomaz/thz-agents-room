"""
THZ Minds — Export Dataset
Exporta dados de treinamento do SQLite para formato ShareGPT.
"""

import asyncio
import aiosqlite
import json
import logging
import os
import sys
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import create_agents, RESPECT_RULES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

DB_PATH = "data/thz-room-cortex.db"
OUTPUT_DIR = "training/datasets"


async def get_agent_messages(agent_name: str, min_words: int = 50) -> List[Dict]:
    """Busca mensagens de um agente especifico."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT m.content, m.status, m.turn, c.topic, c.id as conv_id
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.agent_name = ?
            ORDER BY c.created_at DESC, m.turn ASC
        """, (agent_name,))
        rows = await cursor.fetchall()

        messages = []
        for row in rows:
            content, status, turn, topic, conv_id = row
            word_count = len(content.split())
            if word_count >= min_words:
                messages.append({
                    "content": content,
                    "status": status,
                    "turn": turn,
                    "topic": topic,
                    "conversation_id": conv_id,
                })
        return messages


async def get_debate_transcript(conv_id: str, up_to_turn: int) -> List[Dict]:
    """Busca transcript de um debate ate um turno especifico."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT agent_name, content, turn
            FROM messages
            WHERE conversation_id = ? AND turn <= ?
            ORDER BY turn ASC
        """, (conv_id, up_to_turn))
        rows = await cursor.fetchall()
        return [{"author": r[0], "content": r[1], "turn": r[2]} for r in rows]


def get_system_prompt(agent_name: str) -> str:
    """Retorna o system prompt de um agente."""
    agents = create_agents("dummy")
    for agent in agents:
        if agent.name == agent_name:
            return agent.system_prompt
    return ""


def format_transcript_for_prompt(transcript: List[Dict]) -> str:
    """Formata transcript para o prompt do usuario."""
    if not transcript:
        return "Inicio do debate."
    return "\n".join(f"[{h['author']} - Turno {h['turn']}]: {h['content']}" for h in transcript)


async def export_agent_dataset(agent_name: str, max_examples: int = 1000) -> int:
    """Exporta dataset de um agente especifico."""
    messages = await get_agent_messages(agent_name, min_words=50)
    if not messages:
        logger.warning(f"[EXPORT] Nenhuma mensagem encontrada para {agent_name}")
        return 0

    # Limitar exemplos
    messages = messages[:max_examples]

    system_prompt = get_system_prompt(agent_name)
    dataset = []

    for msg in messages:
        # Buscar transcript anterior ao turno atual
        transcript = await get_debate_transcript(msg["conversation_id"], msg["turn"] - 1)

        # Montar prompt do usuario
        user_content = (
            f"Topico da Discusao: {msg['topic']}\n\n"
            f"Historico:\n{format_transcript_for_prompt(transcript)}\n\n"
            f"Analise o argumento do turno anterior e responda de forma critica, "
            f"apontando pros/contras e trazendo dados concretos. "
            f"IMPORTANTE: NAO copie trechos de outros agentes. Use suas proprias palavras.\n"
            f"Status: 'CONTINUE' para contra-argumentar; 'CONSENSUS' apenas se houver concordancia total."
        )

        # Montar resposta do agente
        assistant_content = json.dumps({
            "argument": msg["content"],
            "status": msg["status"]
        }, ensure_ascii=False)

        # Formato ShareGPT
        example = {
            "conversations": [
                {"from": "system", "value": system_prompt},
                {"from": "human", "value": user_content},
                {"from": "gpt", "value": assistant_content}
            ]
        }
        dataset.append(example)

    # Salvar JSONL
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"{agent_name.lower().replace(' ', '_')}.jsonl")

    with open(output_file, "w", encoding="utf-8") as f:
        for example in dataset:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    logger.info(f"[EXPORT] {agent_name}: {len(dataset)} exemplos exportados para {output_file}")
    return len(dataset)


async def main():
    """Exporta datasets para todos os agentes."""
    agents = ["Arquiteto", "SRE", "DevOps", "DBA", "Security", "PO", "Scrum Master", "Gerente"]
    total = 0

    for agent in agents:
        count = await export_agent_dataset(agent)
        total += count

    logger.info(f"[EXPORT] Total: {total} exemplos exportados")


if __name__ == "__main__":
    asyncio.run(main())
