"""
THZ Minds — Módulo de Segurança e Guardrails
Fornece validação de escopo semântico e execução segura em sandbox Zero-Trust.
"""

from .scope_guard import ScopeGuard, ScopeValidationResult, get_scope_guard
from .sandbox import SandboxExecutor, SandboxSecurityError, get_sandbox

__all__ = [
    "ScopeGuard",
    "ScopeValidationResult",
    "get_scope_guard",
    "SandboxExecutor",
    "SandboxSecurityError",
    "get_sandbox",
]
