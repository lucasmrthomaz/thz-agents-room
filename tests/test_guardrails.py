"""
Testes para os Guardrails de Escopo e Sandbox Zero-Trust
"""

import pytest
from pathlib import Path

from guardrails.scope_guard import ScopeGuard, get_scope_guard
from guardrails.sandbox import SandboxExecutor, ASTStaticScanner, PathValidator, SandboxSecurityError

pytestmark = pytest.mark.asyncio


class TestScopeGuard:
    """Testes para o validador de escopo semântico (Allowlist / Blacklist)."""

    def test_scope_guard_allows_tech_topics(self):
        guard = get_scope_guard()
        tech_topics = [
            "Arquitetura de microsserviços com FastAPI e PostgreSQL",
            "Como implementar autenticação OAuth2 com JWT rotativo",
            "Kafka vs RabbitMQ para mensageria assíncrona de alta volumetria",
            "Otimização de queries SQL e connection pooling com PgBouncer",
            "Pipeline CI/CD no GitHub Actions com Docker e Kubernetes",
            "Modelagem de ameaças STRIDE para proteção contra OWASP Top 10"
        ]
        for topic in tech_topics:
            res = guard.validate_topic(topic)
            assert res.allowed is True, f"Tópico técnico foi rejeitado incorretamente: '{topic}' - motivo: {res.reason}"

    def test_scope_guard_blocks_out_of_scope_topics(self):
        guard = get_scope_guard()
        forbidden_topics = [
            "Qual o melhor carro para comprar com motor v8 e câmbio automático?",
            "Casa de praia com piscina e churrasqueira para aluguel por temporada",
            "Receita de bolo de chocolate fofinho e modo de preparo culinário",
            "Fofocas sobre os eliminados do Big Brother e famosos",
            "Campanha eleitoral e debate sobre candidatos a presidente da república",
            "Melhores dicas de day trade e apostas esportivas no tigrinho"
        ]
        for topic in forbidden_topics:
            res = guard.validate_topic(topic)
            assert res.allowed is False, f"Tópico proibido foi permitido incorretamente: '{topic}'"
            assert "rejeitado" in res.reason.lower() or "fora" in res.reason.lower()


class TestSandboxASTScanner:
    """Testes para análise estática de código AST (Anti-Malware / Anti-Dano)."""

    def test_ast_scanner_allows_safe_code(self):
        safe_code = """
import math
import json

def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

result = calculate_fibonacci(10)
print(f"Fibonacci: {result}")
"""
        # Não deve lançar exceção
        ASTStaticScanner.scan(safe_code)

    def test_ast_scanner_blocks_os_module(self):
        dangerous_code = "import os\nos.system('rmdir /s /q test')"
        with pytest.raises(SandboxSecurityError) as exc:
            ASTStaticScanner.scan(dangerous_code)
        assert "importação proibida" in str(exc.value).lower()

    def test_ast_scanner_blocks_subprocess(self):
        dangerous_code = "from subprocess import Popen\nPopen(['dir'])"
        with pytest.raises(SandboxSecurityError) as exc:
            ASTStaticScanner.scan(dangerous_code)
        assert "importação proibida" in str(exc.value).lower()

    def test_ast_scanner_blocks_eval_exec(self):
        dangerous_code = "eval('__import__(\"os\").getcwd()')"
        with pytest.raises(SandboxSecurityError) as exc:
            ASTStaticScanner.scan(dangerous_code)
        assert "perigosa bloqueada" in str(exc.value).lower()


class TestPathValidator:
    """Testes para o confinamento seguro de diretórios (Path Sandboxing & Anti-Traversal)."""

    def test_path_validator_allows_valid_project_path(self, tmp_path):
        target = PathValidator.validate_safe_write_path("src/main.py", "test_proj_123")
        assert "output" in str(target)
        assert "test_proj_123" in str(target)
        assert target.name == "main.py"

    def test_path_validator_blocks_path_traversal(self):
        with pytest.raises(SandboxSecurityError):
            PathValidator.validate_safe_write_path("../../../windows/system32/cmd.exe", "test_proj_123")

    def test_path_validator_blocks_protected_files(self):
        with pytest.raises(SandboxSecurityError):
            PathValidator.validate_safe_write_path(".env", "test_proj_123")
        with pytest.raises(SandboxSecurityError):
            PathValidator.validate_safe_write_path("server.py", "test_proj_123")

    def test_path_validator_blocks_executable_extensions(self):
        with pytest.raises(SandboxSecurityError):
            PathValidator.validate_safe_write_path("malware.exe", "test_proj_123")


class TestSandboxExecutor:
    """Testes para execução isolada com limites de tempo."""

    async def test_sandbox_executes_valid_code(self):
        sandbox = SandboxExecutor(timeout_seconds=2.0)
        code = "print(sum([x * 2 for x in range(5)]))"
        result = await sandbox.execute_code(code)
        assert result.success is True
        assert result.output == "20"

    async def test_sandbox_blocks_malicious_code_execution(self):
        sandbox = SandboxExecutor(timeout_seconds=2.0)
        code = "import os; os.system('echo test')"
        result = await sandbox.execute_code(code)
        assert result.success is False
        assert "violação de segurança" in result.error.lower()

    async def test_sandbox_timeout_on_infinite_loop(self):
        sandbox = SandboxExecutor(timeout_seconds=1.0)
        code = "while True: pass"
        result = await sandbox.execute_code(code)
        assert result.success is False
        assert "loop infinito" in result.error.lower() or "timeout" in result.error.lower()
