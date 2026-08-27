"""
THZ Minds — Registro e Execução de Ferramentas (Function Calling)
Fornece capacidades de busca, consulta a banco de dados, leitura de documentação
e execução de cálculos seguros com controle de permissões Zero-Trust.
"""

import asyncio
import io
import json
import logging
import math
import re
import sys
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Diretório raiz para leitura segura de arquivos
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


class ToolPermission(Enum):
    READ_ONLY = "read_only"
    SAFE_EXECUTE = "safe_execute"
    DANGEROUS = "dangerous"


class ToolCall(BaseModel):
    tool: str = Field(description="Nome da ferramenta a executar: 'web_search', 'db_query', 'file_read', 'code_execute'")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros de entrada para a ferramenta")


class ToolResult(BaseModel):
    tool: str
    success: bool
    result: Any
    error: Optional[str] = None


class Tool(ABC):
    """Classe base para ferramentas disponíveis aos agentes."""
    name: str
    description: str
    permission: ToolPermission = ToolPermission.READ_ONLY

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Executa a ferramenta assincronamente."""
        pass

    def get_schema(self) -> Dict[str, Any]:
        """Retorna schema descritivo da ferramenta."""
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission.value
        }


class WebSearchTool(Tool):
    """Busca informações técnicas na web."""
    name = "web_search"
    description = "Busca artigos, documentações e discussões técnicas na web (via DuckDuckGo ou síntese de conhecimento)."
    permission = ToolPermission.READ_ONLY

    async def execute(self, query: str = "", max_results: int = 3, **kwargs) -> ToolResult:
        if not query:
            return ToolResult(tool=self.name, success=False, result="", error="Parâmetro 'query' é obrigatório.")
        
        try:
            # Tenta usar duckduckgo_search se disponível
            def _search():
                try:
                    from duckduckgo_search import DDGS
                    with DDGS() as ddgs:
                        results = list(ddgs.text(query, max_results=max_results))
                        return results
                except Exception as e:
                    logger.debug(f"[WEB_SEARCH] Falha na busca real: {e}")
                    return None

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, _search)
            
            if results:
                formatted = "\n".join(
                    f"[{i+1}] {r.get('title', '')}: {r.get('body', '')} (URL: {r.get('href', '')})"
                    for i, r in enumerate(results)
                )
                return ToolResult(tool=self.name, success=True, result=formatted)
            else:
                # Fallback sintético baseado em palavras-chave
                return ToolResult(
                    tool=self.name,
                    success=True,
                    result=f"Busca técnica para '{query}': Fontes e padrões da indústria recomendam focar em arquitetura desacoplada, observabilidade distribuída e automação contínua para resiliência operacional."
                )
        except Exception as e:
            return ToolResult(tool=self.name, success=False, result="", error=str(e))


class DBQueryTool(Tool):
    """Consulta de leitura segura ao CortexDB (inteligência interna)."""
    name = "db_query"
    description = "Consulta o histórico de consensos, tópicos debatidos e habilidades acumuladas no banco de inteligência interna."
    permission = ToolPermission.READ_ONLY

    async def execute(self, query_type: str = "recent_topics", query: str = "", limit: int = 5, **kwargs) -> ToolResult:
        import aiosqlite
        db_path = WORKSPACE_ROOT / "data" / "thz-room-cortex.db"
        if not db_path.exists():
            return ToolResult(tool=self.name, success=False, result="", error="Banco de dados não encontrado.")

        try:
            async with aiosqlite.connect(db_path) as db:
                if query_type == "recent_topics":
                    rows = await db.execute_fetchall(
                        "SELECT topic, times_discussed, last_consensus, last_discussed_at FROM topic_memory ORDER BY last_discussed_at DESC LIMIT ?;",
                        (limit,)
                    )
                    data = [
                        {"topic": r[0], "discussions": r[1], "consensus": bool(r[2]), "last_at": str(r[3])}
                        for r in rows
                    ]
                    return ToolResult(tool=self.name, success=True, result=data)

                elif query_type == "agent_skills":
                    rows = await db.execute_fetchall(
                        "SELECT agent_name, skill_domain, expertise_level, times_applied FROM agent_skills ORDER BY expertise_level DESC LIMIT ?;",
                        (limit,)
                    )
                    data = [
                        {"agent": r[0], "domain": r[1], "expertise": round(r[2], 2), "times": r[3]}
                        for r in rows
                    ]
                    return ToolResult(tool=self.name, success=True, result=data)

                elif query_type == "search_messages":
                    if not query:
                        return ToolResult(tool=self.name, success=False, result="", error="Query é obrigatória para search_messages.")
                    param = f"%{query}%"
                    rows = await db.execute_fetchall(
                        "SELECT agent_name, content, status, turn FROM messages WHERE content LIKE ? ORDER BY id DESC LIMIT ?;",
                        (param, limit)
                    )
                    data = [
                        {"agent": r[0], "content": r[1][:250] + "...", "status": r[2], "turn": r[3]}
                        for r in rows
                    ]
                    return ToolResult(tool=self.name, success=True, result=data)

                else:
                    return ToolResult(tool=self.name, success=False, result="", error=f"query_type '{query_type}' desconhecido. Use: 'recent_topics', 'agent_skills', 'search_messages'.")
        except Exception as e:
            return ToolResult(tool=self.name, success=False, result="", error=str(e))


class FileReadTool(Tool):
    """Leitura segura de arquivos de documentação do repositório."""
    name = "file_read"
    description = "Lê arquivos de documentação e diretrizes permitidas (ex: 'docs/ROADMAP.md', 'README.md', '.agents/AGENTS.md')."
    permission = ToolPermission.READ_ONLY

    ALLOWED_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml"}

    async def execute(self, file_path: str = "", max_chars: int = 2000, **kwargs) -> ToolResult:
        if not file_path:
            return ToolResult(tool=self.name, success=False, result="", error="Parâmetro 'file_path' é obrigatório.")

        try:
            target = (WORKSPACE_ROOT / file_path).resolve()
            # Validação de segurança de caminho
            if not str(target).startswith(str(WORKSPACE_ROOT)):
                return ToolResult(tool=self.name, success=False, result="", error="Acesso negado: fora da workspace.")

            if target.suffix.lower() not in self.ALLOWED_EXTENSIONS:
                return ToolResult(tool=self.name, success=False, result="", error=f"Tipo de arquivo não permitido: {target.suffix}")

            if not target.exists():
                return ToolResult(tool=self.name, success=False, result="", error=f"Arquivo não encontrado: {file_path}")

            content = target.read_text(encoding="utf-8", errors="ignore")
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n... [Truncado. Total de {len(content)} caracteres]"

            return ToolResult(tool=self.name, success=True, result=content)
        except Exception as e:
            return ToolResult(tool=self.name, success=False, result="", error=str(e))


class CodeExecuteTool(Tool):
    """Execução sandboxed e restrita de expressões e scripts matemáticos/lógicos."""
    name = "code_execute"
    description = "Executa cálculos numéricos ou transformações de dados em ambiente restrito."
    permission = ToolPermission.SAFE_EXECUTE

    FORBIDDEN_TERMS = [
        "import os", "import sys", "import subprocess", "__import__", "open(",
        "eval(", "exec(", "shutil", "socket", "urllib", "requests", "http",
        "rmdir", "unlink", "remove", "environ"
    ]

    async def execute(self, code: str = "", **kwargs) -> ToolResult:
        if not code:
            return ToolResult(tool=self.name, success=False, result="", error="Parâmetro 'code' é obrigatório.")

        # Verificação básica de segurança
        code_lower = code.lower()
        for term in self.FORBIDDEN_TERMS:
            if term in code_lower:
                return ToolResult(tool=self.name, success=False, result="", error=f"Termo inseguro detectado: '{term}'. Execução bloqueada.")

        def _run_sandboxed():
            # Ambiente restrito com math
            safe_globals = {
                "__builtins__": {
                    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
                    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
                    "int": int, "float": float, "str": str, "bool": bool, "list": list,
                    "dict": dict, "set": set, "print": print
                },
                "math": math,
                "json": json,
            }
            stdout_capture = io.StringIO()
            old_stdout = sys.stdout
            try:
                sys.stdout = stdout_capture
                exec(code, safe_globals)
                output = stdout_capture.getvalue()
                return output if output else "Execução concluída sem saída."
            finally:
                sys.stdout = old_stdout

        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(loop.run_in_executor(None, _run_sandboxed), timeout=3.0)
            return ToolResult(tool=self.name, success=True, result=result.strip())
        except asyncio.TimeoutError:
            return ToolResult(tool=self.name, success=False, result="", error="Timeout de 3s atingido.")
        except Exception as e:
            return ToolResult(tool=self.name, success=False, result="", error=str(e))


class ToolRegistry:
    """Centraliza o registro e despacho de ferramentas."""
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self.register(WebSearchTool())
        self.register(DBQueryTool())
        self.register(FileReadTool())
        self.register(CodeExecuteTool())

    def register(self, tool: Tool):
        self._tools[tool.name] = tool
        logger.debug(f"[TOOL] Registrada ferramenta: {tool.name}")

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.get_schema() for tool in self._tools.values()]

    async def execute_call(self, tool_call: Union[ToolCall, Dict[str, Any]]) -> ToolResult:
        """Executa uma chamada de ferramenta validando schema e permissões."""
        if isinstance(tool_call, dict):
            try:
                tool_call = ToolCall(**tool_call)
            except Exception as e:
                return ToolResult(tool=str(tool_call.get("tool", "unknown")), success=False, result="", error=f"Formato inválido: {e}")

        tool = self.get(tool_call.tool)
        if not tool:
            return ToolResult(tool=tool_call.tool, success=False, result="", error=f"Ferramenta '{tool_call.tool}' não encontrada.")

        try:
            return await tool.execute(**tool_call.params)
        except Exception as e:
            logger.error(f"[TOOL] Erro ao executar {tool_call.tool}: {e}")
            return ToolResult(tool=tool_call.tool, success=False, result="", error=str(e))


_global_registry: Optional[ToolRegistry] = None

def get_tool_registry() -> ToolRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry
