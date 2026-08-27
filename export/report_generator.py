"""
THZ Minds — Gerador de Relatórios Executivos e Técnicos
Exporta debates e dados de inteligência para formatos Markdown, JSON e HTML.
"""

import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = WORKSPACE_ROOT / "data" / "thz-room-cortex.db"


class ReportGenerator:
    """Gera relatórios de debates e histórico de inteligência."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    async def _fetch_debate_data(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Busca todas as informações pertinentes a um debate."""
        if not self.db_path.exists():
            return None

        async with aiosqlite.connect(self.db_path) as db:
            # Dados da conversa
            cursor = await db.execute(
                "SELECT id, topic, session_id, summary_short, summary_full, created_at FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            conv_row = await cursor.fetchone()
            if not conv_row:
                return None

            conv_id, topic, session_id, summary_short, summary_full, created_at = conv_row

            # Mensagens
            msg_rows = await db.execute_fetchall(
                "SELECT agent_name, content, status, turn, created_at FROM messages WHERE conversation_id = ? ORDER BY turn ASC",
                (conversation_id,)
            )
            messages = [
                {"agent": r[0], "content": r[1], "status": r[2], "turn": r[3], "timestamp": r[4]}
                for r in msg_rows
            ]

            # Scores (se houver)
            score_rows = await db.execute_fetchall(
                "SELECT agent_name, quality_score, novelty_score, expertise_alignment, overall_score FROM argument_scores WHERE conversation_id = ?",
                (conversation_id,)
            )
            scores = [
                {"agent": r[0], "quality": r[1], "novelty": r[2], "expertise": r[3], "overall": r[4]}
                for r in score_rows
            ]

            return {
                "id": conv_id,
                "topic": topic,
                "session_id": session_id,
                "summary_short": summary_short or "Nenhum resumo curto gerado.",
                "summary_full": summary_full or summary_short or "Nenhum resumo completo gerado.",
                "created_at": created_at,
                "total_turns": len(messages),
                "messages": messages,
                "scores": scores,
                "final_status": messages[-1]["status"] if messages else "N/A"
            }

    async def generate_markdown(self, conversation_id: str) -> str:
        """Gera relatório completo em formato Markdown."""
        data = await self._fetch_debate_data(conversation_id)
        if not data:
            return f"# Erro\nDebate `{conversation_id}` não encontrado no banco de dados."

        lines = [
            f"# 🧠 Relatório de Debate Técnico: {data['topic']}",
            "",
            f"- **ID da Conversa:** `{data['id']}`",
            f"- **Data:** {data['created_at']}",
            f"- **Total de Turnos:** {data['total_turns']}",
            f"- **Status Final:** `{data['final_status']}`",
            f"- **Sessão:** `{data['session_id'] or 'Single Mode'}`",
            "",
            "---",
            "",
            "## 📋 Resumo Executivo",
            "",
            data['summary_short'],
            "",
            "## 📖 Resumo Completo e Contextual",
            "",
            data['summary_full'],
            "",
            "---",
            "",
            "## 💬 Transcrição Detalhada dos Turnos",
            ""
        ]

        for m in data['messages']:
            lines.append(f"### Turno {m['turn']}: {m['agent']} `[{m['status']}]`")
            lines.append(f"*{m['timestamp']}*\n")
            lines.append(m['content'])
            lines.append("\n---\n")

        if data['scores']:
            lines.append("## 📊 Métricas de Qualidade dos Argumentos")
            lines.append("")
            lines.append("| Agente | Qualidade | Inovação | Alinhamento de Expertise | Score Geral |")
            lines.append("| :--- | :---: | :---: | :---: | :---: |")
            for s in data['scores']:
                lines.append(f"| {s['agent']} | {s['quality']:.2f} | {s['novelty']:.2f} | {s['expertise']:.2f} | {s['overall']:.2f} |")
            lines.append("")

        return "\n".join(lines)

    async def generate_json(self, conversation_id: str) -> str:
        """Exporta os dados brutos e estruturados do debate em JSON."""
        data = await self._fetch_debate_data(conversation_id)
        if not data:
            return json.dumps({"error": f"Debate {conversation_id} nao encontrado"}, indent=2)
        return json.dumps(data, indent=2, ensure_ascii=False)

    async def generate_html(self, conversation_id: str) -> str:
        """Gera um relatório HTML moderno e estilizado com visual escuro."""
        data = await self._fetch_debate_data(conversation_id)
        if not data:
            return "<html><body><h1>Debate não encontrado</h1></body></html>"

        topic_esc = html.escape(data['topic'])
        summary_short_esc = html.escape(data['summary_short']).replace("\n", "<br>")
        summary_full_esc = html.escape(data['summary_full']).replace("\n", "<br>")

        turns_html = []
        for m in data['messages']:
            agent_esc = html.escape(m['agent'])
            content_esc = html.escape(m['content']).replace("\n", "<br>")
            status_esc = html.escape(m['status'])
            status_cls = "badge-consensus" if m['status'] == "CONSENSUS" else "badge-continue"

            turns_html.append(f"""
            <div class="turn-card">
                <div class="turn-header">
                    <span class="turn-num">Turno {m['turn']}</span>
                    <span class="agent-name">{agent_esc}</span>
                    <span class="badge {status_cls}">{status_esc}</span>
                </div>
                <div class="turn-content">{content_esc}</div>
                <div class="turn-footer">{m['timestamp']}</div>
            </div>
            """)

        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Relatório: {topic_esc}</title>
    <style>
        body {{
            background-color: #1e1e2e;
            color: #cdd6f4;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 30px;
            line-height: 1.6;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1, h2, h3 {{ color: #94e2d5; }}
        .meta-box {{
            background: #282840;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 25px;
            border-left: 4px solid #89b4fa;
        }}
        .summary-box {{
            background: #282840;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 25px;
            border-left: 4px solid #a6e3a1;
        }}
        .turn-card {{
            background: #282840;
            border-radius: 8px;
            padding: 18px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .turn-header {{
            display: flex;
            align-items: center;
            margin-bottom: 10px;
            gap: 10px;
        }}
        .turn-num {{ color: #6c7086; font-size: 0.9em; }}
        .agent-name {{ font-weight: bold; color: #89b4fa; font-size: 1.1em; }}
        .badge {{
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .badge-consensus {{ background: #a6e3a1; color: #1e1e2e; }}
        .badge-continue {{ background: #f9e2af; color: #1e1e2e; }}
        .turn-content {{ margin-top: 8px; color: #f5f5f5; font-size: 0.95em; }}
        .turn-footer {{ font-size: 0.75em; color: #6c7086; margin-top: 8px; text-align: right; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 THZ Minds — Relatório de Debate</h1>
        <div class="meta-box">
            <div><strong>Tópico:</strong> {topic_esc}</div>
            <div><strong>ID:</strong> <code>{data['id']}</code></div>
            <div><strong>Data:</strong> {data['created_at']} | <strong>Turnos:</strong> {data['total_turns']} | <strong>Resultado:</strong> {data['final_status']}</div>
        </div>

        <h2>📋 Resumo Executivo</h2>
        <div class="summary-box">{summary_short_esc}</div>

        <h2>📖 Resumo Completo</h2>
        <div class="summary-box">{summary_full_esc}</div>

        <h2>💬 Transcrição dos Turnos</h2>
        {"".join(turns_html)}
    </div>
</body>
</html>"""
        return html_content

    async def generate_reputation_report(self) -> Dict[str, Any]:
        """Gera dados de reputação consolidados de todos os agentes."""
        if not self.db_path.exists():
            return {"skills": {}, "contributions": {}, "ranking": []}

        async with aiosqlite.connect(self.db_path) as db:
            # Skills
            skills_rows = await db.execute_fetchall(
                "SELECT agent_name, skill_domain, expertise_level, times_applied, consensus_contributions FROM agent_skills ORDER BY expertise_level DESC"
            )
            skills: Dict[str, List[Dict]] = {}
            for row in skills_rows:
                agent, domain, exp, times, contrib = row
                if agent not in skills:
                    skills[agent] = []
                skills[agent].append({
                    "domain": domain,
                    "expertise_level": exp,
                    "times_applied": times,
                    "consensus_contributions": contrib
                })

            # Contribuições gerais
            contrib_rows = await db.execute_fetchall("""
                SELECT 
                    agent_name,
                    COUNT(*) as total_messages,
                    SUM(CASE WHEN status = 'CONSENSUS' THEN 1 ELSE 0 END) as consensus_count
                FROM messages
                GROUP BY agent_name
            """)
            contributions = {
                r[0]: {"total_messages": r[1], "consensus_count": r[2] or 0}
                for r in contrib_rows
            }

            # Ranking ponderado
            ranking = []
            for agent, stats in contributions.items():
                agent_skills_list = skills.get(agent, [])
                avg_exp = sum(s["expertise_level"] for s in agent_skills_list) / len(agent_skills_list) if agent_skills_list else 0.5
                consensus_rate = stats["consensus_count"] / max(stats["total_messages"], 1)
                reputation_score = (avg_exp * 0.5) + (consensus_rate * 0.5)
                ranking.append({
                    "agent": agent,
                    "reputation_score": round(reputation_score, 3),
                    "total_messages": stats["total_messages"],
                    "consensus_count": stats["consensus_count"],
                    "avg_expertise": round(avg_exp, 2),
                    "skills": agent_skills_list
                })

            ranking.sort(key=lambda x: x["reputation_score"], reverse=True)

            return {
                "skills": skills,
                "contributions": contributions,
                "ranking": ranking
            }
