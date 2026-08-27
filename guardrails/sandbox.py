"""
THZ Minds — Sandbox de Execução Segura e Confinamento Zero-Trust
Fornece análise estática de código via AST e confinamento estrito de sistema de arquivos (Path Jail),
impedindo qualquer operação danosa (ex: deletar arquivos, executar comandos de shell, acessar rede ou sair de output/).
"""

import ast
import asyncio
import io
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

logger = logging.getLogger("ThzRoom.Guardrails.Sandbox")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = WORKSPACE_ROOT / "output"


class SandboxSecurityError(Exception):
    """Exceção levantada quando uma violação de segurança do sandbox é detectada."""
    pass


class SandboxResult(BaseModel):
    success: bool
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class ASTStaticScanner:
    """Inspeciona a Árvore Sintática Abstrata (AST) de um código Python antes da execução."""

    FORBIDDEN_MODULES: Set[str] = {
        "os", "sys", "subprocess", "shutil", "socket", "urllib", "requests",
        "http", "pty", "ctypes", "multiprocessing", "threading", "builtins",
        "posix", "nt", "signal", "winreg", "_winapi", "asyncio.subprocess",
        "importlib", "pip", "venv"
    }

    FORBIDDEN_CALLS: Set[str] = {
        "eval", "exec", "open", "__import__", "globals", "locals", "compile",
        "breakpoint", "memoryview", "input"
    }

    FORBIDDEN_ATTRS: Set[str] = {
        "__subclasses__", "__bases__", "__globals__", "__code__", "__reduce__",
        "__import__", "__builtins__"
    }

    @classmethod
    def scan(cls, code: str) -> None:
        """Varre o código via AST. Lança SandboxSecurityError se encontrar padrões perigosos."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SandboxSecurityError(f"Erro de sintaxe no código: {e}")

        for node in ast.walk(tree):
            # 1. Checagem de Imports (import x, import x as y)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0].lower()
                    if root_mod in cls.FORBIDDEN_MODULES:
                        raise SandboxSecurityError(f"Importação proibida pelo Sandbox: '{alias.name}'")

            # 2. Checagem de Import From (from x import y)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0].lower()
                    if root_mod in cls.FORBIDDEN_MODULES:
                        raise SandboxSecurityError(f"Importação proibida pelo Sandbox: 'from {node.module} import ...'")

            # 3. Checagem de Funções Proibidas
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in cls.FORBIDDEN_CALLS:
                        raise SandboxSecurityError(f"Chamada de função perigosa bloqueada: '{node.func.id}()'")

            # 4. Checagem de Acesso a Atributos Mágicos de Escape de Sandbox
            elif isinstance(node, ast.Attribute):
                if node.attr in cls.FORBIDDEN_ATTRS:
                    raise SandboxSecurityError(f"Acesso a atributo interno bloqueado: '{node.attr}'")


class PathValidator:
    """Valida caminhos de arquivos garantindo confinamento estrito dentro do diretório de saída."""

    FORBIDDEN_NAMES: Set[str] = {
        ".env", ".git", ".gitignore", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
        "thz-room-cortex.db", "server.py", "gui.py", "requirements.txt"
    }

    FORBIDDEN_EXTENSIONS: Set[str] = {
        ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".vbs", ".ps1", ".pem", ".key"
    }

    @classmethod
    def validate_safe_write_path(cls, relative_or_abs_path: str, project_id: str, base_dir: Optional[Path] = None) -> Path:
        """Garante que a escrita ocorra estritamente dentro de output/<project_id>/."""
        root = base_dir or OUTPUT_ROOT
        project_root = (root / project_id).resolve()
        project_root.mkdir(parents=True, exist_ok=True)

        target = (project_root / relative_or_abs_path).resolve()

        # Checagem de Path Traversal
        if not str(target).startswith(str(project_root)):
            raise SandboxSecurityError(f"Tentativa de Path Traversal bloqueada: caminho '{target}' fora de '{project_root}'")

        # Checagem de nomes protegidos
        if target.name.lower() in cls.FORBIDDEN_NAMES:
            raise SandboxSecurityError(f"Nome de arquivo protegido contra sobrescrita: '{target.name}'")

        # Checagem de extensões perigosas
        if target.suffix.lower() in cls.FORBIDDEN_EXTENSIONS:
            raise SandboxSecurityError(f"Extensão de arquivo não permitida para gravação: '{target.suffix}'")

        return target

    @classmethod
    def validate_safe_read_path(cls, relative_or_abs_path: str) -> Path:
        """Valida que leituras fiquem confinadas dentro da workspace raiz."""
        target = (WORKSPACE_ROOT / relative_or_abs_path).resolve()

        if not str(target).startswith(str(WORKSPACE_ROOT)):
            raise SandboxSecurityError(f"Acesso negado: caminho '{target}' fora do diretório da aplicação.")

        if target.name.lower() in cls.FORBIDDEN_NAMES and target.name.startswith("."):
            raise SandboxSecurityError(f"Leitura de arquivo protegido negada: '{target.name}'")

        return target


class SandboxExecutor:
    """Executa código Python em ambiente isolado com limites estritos de tempo e recursos."""

    def __init__(self, timeout_seconds: float = 3.0):
        self.timeout_seconds = timeout_seconds

    async def execute_code(self, code: str) -> SandboxResult:
        """Valida via AST e executa o código em sandbox restrito."""
        if not code or not code.strip():
            return SandboxResult(success=False, output="", error="Código vazio para execução.")

        # 1. Análise Estática AST (Bloqueio prévio)
        try:
            ASTStaticScanner.scan(code)
        except SandboxSecurityError as sec_err:
            logger.warning(f"[SANDBOX-SECURITY] Violação bloqueada: {sec_err}")
            return SandboxResult(success=False, output="", error=f"Violação de Segurança: {sec_err}")

        # 2. Preparar ambiente seguro
        safe_builtins = {
            "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
            "len": len, "range": range, "enumerate": enumerate, "zip": zip,
            "int": int, "float": float, "str": str, "bool": bool, "list": list,
            "dict": dict, "set": set, "tuple": tuple, "print": print,
            "isinstance": isinstance, "issubclass": issubclass, "Exception": Exception,
            "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError,
            "IndexError": IndexError, "AssertionError": AssertionError, "True": True, "False": False, "None": None
        }

        safe_globals = {
            "__builtins__": safe_builtins,
            "math": math,
            "json": json,
        }

        def _run():
            import time
            start = time.perf_counter()
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            old_out = sys.stdout
            old_err = sys.stderr

            max_steps = 100_000
            steps = [0]

            def _step_limit_trace(frame, event, arg):
                steps[0] += 1
                if steps[0] > max_steps:
                    raise SandboxSecurityError("Limite de passos de execução excedido (possível loop infinito ou recursão excessiva).")
                return _step_limit_trace

            try:
                sys.stdout = stdout_buf
                sys.stderr = stderr_buf
                sys.settrace(_step_limit_trace)
                exec(code, safe_globals)
                sys.settrace(None)
                out = stdout_buf.getvalue()
                err = stderr_buf.getvalue()
                elapsed = (time.perf_counter() - start) * 1000.0
                return True, out, err if err else None, elapsed
            except Exception as e:
                sys.settrace(None)
                elapsed = (time.perf_counter() - start) * 1000.0
                return False, stdout_buf.getvalue(), str(e), elapsed
            finally:
                sys.settrace(None)
                sys.stdout = old_out
                sys.stderr = old_err

        loop = asyncio.get_event_loop()
        try:
            success, out, err, elapsed = await asyncio.wait_for(
                loop.run_in_executor(None, _run),
                timeout=self.timeout_seconds
            )
            return SandboxResult(
                success=success,
                output=out.strip() if out else ("Execução concluída com sucesso." if success else ""),
                error=err,
                execution_time_ms=round(elapsed, 2)
            )
        except asyncio.TimeoutError:
            logger.error(f"[SANDBOX] Timeout de {self.timeout_seconds}s excedido.")
            return SandboxResult(
                success=False,
                output="",
                error=f"Timeout de execução ({self.timeout_seconds}s) excedido. Possível loop infinito bloqueado.",
                execution_time_ms=self.timeout_seconds * 1000.0
            )


_global_sandbox = None

def get_sandbox() -> SandboxExecutor:
    global _global_sandbox
    if _global_sandbox is None:
        _global_sandbox = SandboxExecutor()
    return _global_sandbox
