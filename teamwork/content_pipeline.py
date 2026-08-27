"""
THZ Minds — Pipeline de TeamWork de Criação & Revisão de Artigos Técnicos
Inspirado no modelo editorial da DIO e publicações de tecnologia da comunidade.
Orquestra 6 especialistas: Pesquisador -> Redator -> Revisor Técnico -> Especialista SEO -> Revisor Gramatical -> Editor-Chefe.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import httpx

from guardrails.scope_guard import get_scope_guard
from .models import (
    TeamworkArtifact,
    TeamworkMode,
    TeamworkRole,
    TeamworkSessionRequest,
    TeamworkSessionResult,
    TeamworkStage,
    TeamworkStepResult,
)
from .workspace_manager import WorkspaceManager

logger = logging.getLogger("ThzRoom.Teamwork.Content")

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:7b"


class ContentPipeline:
    """Orquestrador do ciclo editorial de artigos técnicos multiagente."""

    def __init__(self, model: str = DEFAULT_MODEL, num_ctx: int = 8192):
        self.model = model
        self.num_ctx = num_ctx
        self.scope_guard = get_scope_guard()

    async def run(
        self,
        request: TeamworkSessionRequest,
        progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ) -> TeamworkSessionResult:
        """Executa a pipeline completa de criação e curadoria de artigo técnico."""
        # 1. Validar Guardrail de Escopo
        scope_res = self.scope_guard.validate_topic(request.goal)
        if not scope_res.allowed:
            raise ValueError(f"Guardrail de Escopo Rejeitou: {scope_res.reason}")

        session_id = f"art_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        project_name = request.project_name or f"article_{session_id}"
        model_to_use = request.model or self.model

        steps: List[TeamworkStepResult] = []
        all_artifacts: List[TeamworkArtifact] = []
        context_accumulator: List[str] = []

        async def _notify(stage: TeamworkStage, role: str, status: str, message: str, step_data: Any = None):
            if progress_callback:
                payload = {
                    "session_id": session_id,
                    "project_name": project_name,
                    "stage": stage.value,
                    "role": role,
                    "status": status,
                    "message": message,
                    "step_data": step_data
                }
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback(payload)
                else:
                    progress_callback(payload)

        await _notify(TeamworkStage.INIT, "Editorial Board", "started", f"Iniciando Produção de Artigo: '{request.goal}'")

        editorial_pipeline = [
            (
                1,
                TeamworkStage.EDITORIAL_RESEARCH,
                TeamworkRole.RESEARCHER,
                "Pesquisador & Analista de Tendências",
                (
                    "Você é o Pesquisador Técnico. Mapeie o estado da arte e fontes sobre o tema.\n"
                    "Estruture:\n"
                    "1. Tese central do artigo e público-alvo (Devs, Arquitetos, Tech Leads)\n"
                    "2. Tópicos essenciais que DEVEM ser abordados\n"
                    "3. Boas práticas e armadilhas comuns a destacar\n"
                    "Gere a pauta no formato:\n"
                    "### FILE: docs/PAUTA.md\n```markdown\n[estrutura e fontes da pesquisa]\n```"
                )
            ),
            (
                2,
                TeamworkStage.FIRST_DRAFT,
                TeamworkRole.TECHNICAL_WRITER,
                "Redator Técnico Especialista",
                (
                    "Você é o Redator Técnico. Escreva o artigo completo, aprofundado, didático e prático.\n"
                    "REGRAS:\n"
                    "- Português do Brasil (pt-BR) impecável.\n"
                    "- Inclua exemplos reais de código, diagramas conceituais e comandos.\n"
                    "- Estruture em: Introdução provocativa, Fundamentação, Prática/Código, Trade-offs e Conclusão.\n"
                    "Gere o rascunho no formato:\n"
                    "### FILE: rascunho_artigo.md\n```markdown\n[artigo completo com código]\n```"
                )
            ),
            (
                3,
                TeamworkStage.TECHNICAL_REVIEW,
                TeamworkRole.TECHNICAL_REVIEWER,
                "Revisor Técnico (Subject Matter Expert - SME)",
                (
                    "Você é o Revisor Técnico Especialista (SME). Valide a exatidão técnica do artigo.\n"
                    "Avalie:\n"
                    "1. Os exemplos de código e comandos estão corretos e atualizados?\n"
                    "2. Os conceitos arquiteturais e termos técnicos foram usados com precisão?\n"
                    "3. Faça correções pontuais no código e no texto.\n"
                    "Gere o feedback técnico no formato:\n"
                    "### FILE: docs/REVISAO_TECNICA.md\n```markdown\n[análise técnica e correções]\n```"
                )
            ),
            (
                4,
                TeamworkStage.SEO_OPTIMIZATION,
                TeamworkRole.SEO_SPECIALIST,
                "Especialista em SEO & Engajamento",
                (
                    "Você é o Especialista de SEO e Developer Experience.\n"
                    "Otimize o artigo para mecanismos de busca e leitura escaneável:\n"
                    "1. Sugira 3 opções de Títulos atraentes (High CTR)\n"
                    "2. Meta-descrição (max 160 caracteres)\n"
                    "3. Ajuste hierarquia de títulos (H1, H2, H3) e bullet points para reter o leitor.\n"
                    "Gere o relatório no formato:\n"
                    "### FILE: docs/SEO_REPORT.md\n```markdown\n[otimizações de SEO e títulos]\n```"
                )
            ),
            (
                5,
                TeamworkStage.GRAMMAR_POLISH,
                TeamworkRole.GRAMMAR_REVIEWER,
                "Revisor Gramatical & Estilo",
                (
                    "Você é o Revisor de Estilo e Gramática (pt-BR).\n"
                    "Ajuste:\n"
                    "1. Clareza, coesão e fluidez dos parágrafos\n"
                    "2. Elimine redundâncias e jargões desnecessários\n"
                    "3. Garanta concordância e pontuação impecáveis.\n"
                    "Gere o artigo polido no formato:\n"
                    "### FILE: artigo_revisado.md\n```markdown\n[artigo revisado e polido]\n```"
                )
            ),
            (
                6,
                TeamworkStage.FINAL_PACKAGING,
                TeamworkRole.EDITOR_IN_CHIEF,
                "Editor-Chefe da Comunidade",
                (
                    "Você é o Editor-Chefe. Unifique todas as melhorias e gere a versão FINAL PRONTA PARA PUBLICAÇÃO.\n"
                    "Gere:\n"
                    "1. O arquivo `ARTIGO_FINAL.md` completo, formatado e pronto para o blog.\n"
                    "2. O arquivo `metadata.json` com tags da comunidade, tempo de leitura estimado e resumo.\n"
                    "Gere os arquivos no formato:\n"
                    "### FILE: ARTIGO_FINAL.md\n```markdown\n[artigo final completo]\n```\n"
                    "### FILE: metadata.json\n```json\n{\n  \"title\": \"...\",\n  \"tags\": [\"...\"],\n  \"read_time_minutes\": 5,\n  \"summary\": \"...\"\n}\n```"
                )
            ),
        ]

        for step_num, stage, role, title, system_prompt in editorial_pipeline:
            await _notify(stage, role.value, "running", f"Etapa {step_num}/6: {title} trabalhando...")

            history_summary = "\n\n".join(context_accumulator[-2:]) if context_accumulator else "Início da produção."
            user_prompt = (
                f"TEMA DO ARTIGO: {request.goal}\n\n"
                f"PRODUÇÃO EDITORIAL ATÉ O MOMENTO:\n{history_summary}\n\n"
                f"SUA TAREFA COMO {title.upper()}:\n"
                f"{system_prompt}\n\n"
                "IMPORTANTE: Formate seus arquivos gerados com os marcadores '### FILE: caminho/do/arquivo.ext'."
            )

            payload = {
                "model": model_to_use,
                "messages": [
                    {"role": "system", "content": f"Você é o {title} na redação técnica da comunidade de desenvolvedores."},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": 0.5,
                    "num_ctx": request.num_ctx
                }
            }

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(OLLAMA_CHAT_URL, json=payload, timeout=180.0)
                    resp.raise_for_status()
                    agent_output = resp.json()["message"]["content"].strip()
            except Exception as e:
                logger.error(f"[TEAMWORK-CONTENT] Erro na etapa {stage.value} ({role.value}): {e}")
                agent_output = f"Erro na inferência da etapa {stage.value}: {e}"

            extracted_files = WorkspaceManager.extract_artifacts_from_text(agent_output, author_role=role.value)
            all_artifacts.extend(extracted_files)

            step_res = TeamworkStepResult(
                step_number=step_num,
                stage=stage,
                agent_name=role.value,
                role_title=title,
                contribution=agent_output,
                artifacts=extracted_files,
                success=True
            )
            steps.append(step_res)
            context_accumulator.append(f"[{role.value} - {stage.value}]:\n{agent_output[:1500]}")

            await _notify(
                stage, role.value, "completed",
                f"Etapa {step_num}/6 concluída por {role.value}.",
                step_data={
                    "step_number": step_num,
                    "total_steps": 6,
                    "role_title": title,
                    "files": [f.path for f in extracted_files],
                    "contribution": agent_output
                }
            )

        output_path = WorkspaceManager.save_artifacts(project_name, all_artifacts)

        final_summary = (
            f"Artigo técnico '{project_name}' finalizado com sucesso pelo time editorial.\n"
            f"Total de etapas: 6 | Total de arquivos gerados: {len(all_artifacts)}.\n"
            f"Salvo em: {output_path}"
        )

        await _notify(TeamworkStage.COMPLETED, "Editorial Board", "completed", final_summary)

        return TeamworkSessionResult(
            session_id=session_id,
            mode=TeamworkMode.CONTENT,
            goal=request.goal,
            project_name=project_name,
            status="success",
            total_steps=len(steps),
            steps=steps,
            artifacts=all_artifacts,
            output_directory=str(output_path),
            executive_summary=final_summary,
            created_at=datetime.now().isoformat()
        )
