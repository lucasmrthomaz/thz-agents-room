"""
THZ Minds — Pipeline de TeamWork de Engenharia de Software
Executa uma linha de montagem com 7 especialistas para criar uma solução de software real
(Código, SQL, Docker, K8s, Segurança e Testes com Self-Healing).
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import httpx

from guardrails.sandbox import get_sandbox
from guardrails.scope_guard import get_scope_guard
from .models import (
    TeamworkArtifact,
    TeamworkRole,
    TeamworkSessionRequest,
    TeamworkSessionResult,
    TeamworkStage,
    TeamworkStepResult,
    TeamworkMode,
)
from .workspace_manager import WorkspaceManager

logger = logging.getLogger("ThzRoom.Teamwork.Engineering")

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:7b"


class EngineeringPipeline:
    """Orquestrador do ciclo de vida de desenvolvimento de software multiagente."""

    def __init__(self, model: str = DEFAULT_MODEL, num_ctx: int = 8192):
        self.model = model
        self.num_ctx = num_ctx
        self.sandbox = get_sandbox()
        self.scope_guard = get_scope_guard()

    async def run(
        self,
        request: TeamworkSessionRequest,
        progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ) -> TeamworkSessionResult:
        """Executa a pipeline completa de engenharia de software."""
        # 1. Validar Guardrail de Escopo
        scope_res = self.scope_guard.validate_topic(request.goal)
        if not scope_res.allowed:
            raise ValueError(f"Guardrail de Escopo Rejeitou: {scope_res.reason}")

        session_id = f"eng_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        project_name = request.project_name or f"project_{session_id}"
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

        await _notify(TeamworkStage.INIT, "Orchestrator", "started", f"Iniciando TeamWork de Engenharia: '{request.goal}'")

        # -------------------------------------------------------------
        # ETAPAS DA PIPELINE
        # -------------------------------------------------------------
        roles_pipeline = [
            (
                1,
                TeamworkStage.REQUIREMENTS,
                TeamworkRole.TECH_LEAD,
                "Tech Lead & Product Specialist",
                (
                    "Você é o Tech Lead experiente. Sua missão é decompor o objetivo em especificações técnicas precisas.\n"
                    "Defina:\n"
                    "1. Escopo e Casos de Uso principais\n"
                    "2. Contratos de API/Interface (endpoints, inputs, outputs, códigos HTTP)\n"
                    "3. Requisitos Não Funcionais (latência alvo, concorrência, idempotência, segurança)\n"
                    "Gere um arquivo de especificação no formato:\n"
                    "### FILE: docs/SPEC.md\n```markdown\n[conteúdo da especificação]\n```"
                )
            ),
            (
                2,
                TeamworkStage.ARCHITECTURE,
                TeamworkRole.ARCHITECT,
                "Software Architect",
                (
                    "Você é o Arquiteto de Software. Com base na especificação do Tech Lead, desenhe o blueprint técnico.\n"
                    "Defina:\n"
                    "1. Padrões de Projeto (Clean Architecture, Ports & Adapters ou Monólito Modular)\n"
                    "2. Estrutura de Pastas e Módulos do Projeto\n"
                    "3. Diagrama C4 ou Fluxo de Componentes em ASCII/Mermaid\n"
                    "Gere a documentação de arquitetura no formato:\n"
                    "### FILE: docs/ARCHITECTURE.md\n```markdown\n[conteúdo de arquitetura]\n```"
                )
            ),
            (
                3,
                TeamworkStage.DATA_MODELING,
                TeamworkRole.DBA,
                "Database Specialist & DBA",
                (
                    "Você é o DBA Especialista. Com base no escopo e arquitetura, crie o modelo relacional de dados.\n"
                    "Defina:\n"
                    "1. DDL completo em SQL (PostgreSQL compatível) com tabelas, chaves primárias/estrangeiras e tipos estritos\n"
                    "2. Índices para otimização de busca e constraints de unicidade/idempotência\n"
                    "3. Script de dados iniciais (Seed)\n"
                    "Gere os arquivos no formato:\n"
                    "### FILE: db/schema.sql\n```sql\n[DDL completo]\n```\n"
                    "### FILE: db/seed.sql\n```sql\n[dados iniciais]\n```"
                )
            ),
            (
                4,
                TeamworkStage.IMPLEMENTATION,
                TeamworkRole.SENIOR_DEV,
                "Senior Backend Developer",
                (
                    "Você é o Desenvolvedor Senior. Implemente o código-fonte executável COMPLETO e LIMPO da aplicação.\n"
                    "REGRAS ESTRITAS:\n"
                    "- NUNCA deixe código incompleto, NUNCA use '# TODO' ou 'implementar depois'.\n"
                    "- Código em Python (ou FastAPI/Flask conforme apropriado) com tratamento robusto de erros e tipagem estrita.\n"
                    "- Implemente a lógica de negócio, rotas e conexão/queries com o banco.\n"
                    "Gere os arquivos no formato:\n"
                    "### FILE: src/main.py\n```python\n[código completo]\n```\n"
                    "### FILE: requirements.txt\n```text\n[dependências necessárias]\n```"
                )
            ),
            (
                5,
                TeamworkStage.INFRASTRUCTURE,
                TeamworkRole.DEVOPS_SRE,
                "DevOps & SRE Engineer",
                (
                    "Você é o DevOps e SRE. Prepare toda a infraestrutura como código e observabilidade.\n"
                    "Defina:\n"
                    "1. Dockerfile multi-stage otimizado e seguro (sem rodar como root)\n"
                    "2. docker-compose.yml pronto para subir app + postgres\n"
                    "3. Manifesto Kubernetes (Deployment com limites de CPU/memória e Service)\n"
                    "Gere os arquivos no formato:\n"
                    "### FILE: Dockerfile\n```dockerfile\n[conteúdo]\n```\n"
                    "### FILE: docker-compose.yml\n```yaml\n[conteúdo]\n```\n"
                    "### FILE: k8s/deployment.yaml\n```yaml\n[conteúdo]\n```"
                )
            ),
            (
                6,
                TeamworkStage.SECURITY_AUDIT,
                TeamworkRole.SECURITY,
                "Security Specialist",
                (
                    "Você é o Especialista de Segurança da Informação. Audite o código e a infraestrutura gerados.\n"
                    "Avalie:\n"
                    "1. Vulnerabilidades OWASP (Injeção SQL, exposição de credenciais, XSS, autenticação)\n"
                    "2. Sanitização de inputs e headers de segurança\n"
                    "3. Gere um relatório de segurança e, se necessário, aplique correções.\n"
                    "Gere o relatório no formato:\n"
                    "### FILE: docs/SECURITY.md\n```markdown\n[análise de segurança e ameaças STRIDE]\n```"
                )
            ),
            (
                7,
                TeamworkStage.TESTING,
                TeamworkRole.QA_TESTER,
                "QA Engineer & Test Specialist",
                (
                    "Você é o Engenheiro de QA. Crie a suíte de testes unitários e de integração automatizados em Pytest.\n"
                    "Cubra:\n"
                    "1. Casos de sucesso (caminho feliz)\n"
                    "2. Casos de erro, validação de payload inválido e limites de borda\n"
                    "Gere os testes no formato:\n"
                    "### FILE: tests/test_app.py\n```python\n[testes completos em pytest]\n```"
                )
            ),
        ]

        # Executar cada especialista em sequência
        for step_num, stage, role, title, system_prompt in roles_pipeline:
            await _notify(stage, role.value, "running", f"Etapa {step_num}/7: {title} trabalhando...")

            # Montar contexto acumulado com entregas dos agentes anteriores
            history_summary = "\n\n".join(context_accumulator[-3:]) if context_accumulator else "Início do projeto."
            user_prompt = (
                f"OBJETIVO DO PROJETO: {request.goal}\n\n"
                f"CONTEXTO PRODUZIDO ATÉ O MOMENTO PELO TIME:\n{history_summary}\n\n"
                f"SUA TAREFA COMO {title.upper()}:\n"
                f"{system_prompt}\n\n"
                "IMPORTANTE E OBRIGATÓRIO:\n"
                "- Escreva código COMPLETO, sem 'pass', sem '...', sem omitir funções.\n"
                "- Formate TODOS os arquivos gerados com os marcadores '### FILE: caminho/do/arquivo.ext' e feche os blocos de código com '```'."
            )

            messages = [
                {"role": "system", "content": f"Você é o {title} em um time de alto nível de engenharia de software. Você sempre entrega código e artefatos 100% completos e funcionais de produção."},
                {"role": "user", "content": user_prompt}
            ]
            options = {
                "temperature": 0.4,
                "num_ctx": request.num_ctx,
                "num_predict": 4096
            }

            from stability.model_selector import get_model_selector
            selector = get_model_selector()

            async def on_degrade(event_dict):
                await _notify(stage, role.value, "model_fallback", event_dict.get("message", "Abaixando a régua do modelo..."), step_data=event_dict)

            try:
                agent_output, effective_model, latency = await selector.infer_with_adaptive_fallback(
                    messages=messages,
                    options=options,
                    preferred_model=model_to_use,
                    step_timeout_sec=120.0,
                    progress_callback=on_degrade
                )
                logger.info(f"[TEAMWORK-ENG] Etapa {step_num} executada com '{effective_model}' em {latency:.2f}s.")
            except Exception as e:
                logger.error(f"[TEAMWORK-ENG] Erro irrecuperável na etapa {stage.value} ({role.value}): {e}")
                agent_output = f"Erro na inferência da etapa {stage.value}: {e}"

            # Extrair arquivos gerados
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
                f"Etapa {step_num}/7 concluída por {role.value}. {len(extracted_files)} arquivo(s) gerado(s).",
                step_data={
                    "step_number": step_num,
                    "total_steps": 7,
                    "role_title": title,
                    "files": [f.path for f in extracted_files],
                    "contribution": agent_output
                }
            )

        # -------------------------------------------------------------
        # SELF-HEALING LOOP: Execução e Correção de Testes
        # -------------------------------------------------------------
        if request.auto_heal:
            test_artifact = next((a for a in all_artifacts if "test" in a.path.lower() and a.path.endswith(".py")), None)
            code_artifact = next((a for a in all_artifacts if ("main.py" in a.path or "app.py" in a.path or "src/" in a.path) and a.path.endswith(".py")), None)

            if test_artifact and code_artifact:
                await _notify(TeamworkStage.SELF_HEALING, "Self-Healing", "running", "Executando suíte de testes em sandbox...")
                combined_code = f"{code_artifact.content}\n\n# --- TESTES ---\n{test_artifact.content}"
                sandbox_res = await self.sandbox.execute_code(combined_code)

                if not sandbox_res.success:
                    logger.warning(f"[SELF-HEALING] Testes falharam: {sandbox_res.error}. Acionando Dev Senior para auto-correção...")
                    await _notify(TeamworkStage.SELF_HEALING, TeamworkRole.SENIOR_DEV.value, "healing", f"Falha detectada nos testes: {sandbox_res.error}. Auto-corrigindo...")

                    heal_prompt = (
                        f"O código gerado anteriormente falhou na execução dos testes.\n"
                        f"ERRO / TRACEBACK:\n{sandbox_res.error}\n\n"
                        f"CÓDIGO ATUAL:\n{code_artifact.content}\n\n"
                        f"TESTES:\n{test_artifact.content}\n\n"
                        "Por favor, CORRIJA O CÓDIGO para que todos os testes passem com 100% de sucesso.\n"
                        "Retorne o arquivo corrigido com '### FILE: src/main.py'."
                    )

                    heal_payload = {
                        "model": model_to_use,
                        "messages": [
                            {"role": "system", "content": "Você é o Dev Senior responsável por corrigir bugs e garantir testes verdes."},
                            {"role": "user", "content": heal_prompt}
                        ],
                        "stream": False,
                        "options": {"temperature": 0.2, "num_ctx": request.num_ctx}
                    }

                    try:
                        async with httpx.AsyncClient() as client:
                            heal_resp = await client.post(OLLAMA_CHAT_URL, json=heal_payload, timeout=180.0)
                            heal_resp.raise_for_status()
                            healed_output = heal_resp.json()["message"]["content"]
                            healed_files = WorkspaceManager.extract_artifacts_from_text(healed_output, author_role=TeamworkRole.SENIOR_DEV.value)
                            if healed_files:
                                for hf in healed_files:
                                    # Atualizar na lista
                                    for idx, a in enumerate(all_artifacts):
                                        if a.path == hf.path:
                                            all_artifacts[idx] = hf
                                            break
                                    else:
                                        all_artifacts.append(hf)
                                logger.info(f"[SELF-HEALING] Código corrigido com sucesso pelo Dev Senior.")
                    except Exception as heal_err:
                        logger.error(f"[SELF-HEALING] Erro no retry do Dev Senior: {heal_err}")

        # -------------------------------------------------------------
        # SALVAR PROJETO COMPLETO NO DISCO
        # -------------------------------------------------------------
        # Adicionar README.md mestre se não existir
        if not any(a.path.lower() == "readme.md" for a in all_artifacts):
            readme_content = (
                f"# 🚀 {project_name}\n\n"
                f"**Objetivo:** {request.goal}\n\n"
                f"- **Sessão:** `{session_id}`\n"
                f"- **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- **Arquitetura:** Gerada pelo time autônomo THZ Minds TeamWork\n\n"
                f"## 📂 Estrutura de Arquivos\n" +
                "\n".join(f"- `{a.path}` ({a.author_role})" for a in all_artifacts) +
                "\n\n## 🛠️ Como Executar\n```bash\ndocker-compose up --build\n```\n"
            )
            all_artifacts.append(TeamworkArtifact(
                path="README.md",
                content=readme_content,
                file_type="markdown",
                author_role="Orchestrator",
                created_at=datetime.now().isoformat()
            ))

        output_path = WorkspaceManager.save_artifacts(project_name, all_artifacts)

        final_summary = (
            f"Solução de engenharia '{project_name}' concluída com sucesso.\n"
            f"Total de etapas: 7 | Total de arquivos gerados: {len(all_artifacts)}.\n"
            f"Arquivos salvos em: {output_path}"
        )

        await _notify(
            TeamworkStage.COMPLETED, "Orchestrator", "pipeline_finished", final_summary,
            step_data={
                "step_number": 7,
                "total_steps": 7,
                "role_title": "Orchestrator",
                "contribution": final_summary
            }
        )

        return TeamworkSessionResult(
            session_id=session_id,
            mode=TeamworkMode.ENGINEERING,
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
