"""
THZ Minds — Guardrail de Escopo e Semântica (Scope & Content Gateway)
Garante que todas as requisições, tópicos e argumentos estejam estritamente dentro
do domínio de Tecnologia e Engenharia de Software, bloqueando tópicos não-técnicos
(carros, imóveis, piscinas, receitas, fofocas, política partidária, etc.).
"""

import re
import logging
from typing import List, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("ThzRoom.Guardrails.Scope")


class ScopeValidationResult(BaseModel):
    allowed: bool = Field(description="True se o conteúdo estiver dentro do escopo de tecnologia.")
    category: str = Field(description="Categoria detectada do escopo ou motivo do bloqueio.")
    reason: str = Field(description="Explicação detalhada para feedback ao usuário ou agente.")
    flagged_terms: List[str] = Field(default_factory=list, description="Termos proibidos identificados.")


class ScopeGuard:
    """Validador estrito de escopo para Engenharia de Software e Tecnologia."""

    ALLOWED_DOMAINS = [
        "arquitetura_de_software",
        "programacao_e_algoritmos",
        "bancos_de_dados",
        "devops_e_cloud",
        "seguranca_e_criptografia",
        "sre_e_observabilidade",
        "git_e_versionamento",
        "lideranca_e_processos_tech",
        "redacao_tecnica_e_documentacao",
        "design_de_sistemas_e_apis",
    ]

    # Palavras e raízes obrigatórias de tecnologia
    TECH_INDICATORS = [
        "software", "api", "apis", "banco de dados", "database", "sql", "nosql", "postgres", "postgresql",
        "mysql", "sqlite", "oracle", "mongodb", "redis", "kafka", "rabbitmq", "docker", "kubernetes", "k8s",
        "ci/cd", "ci", "cd", "deploy", "pipeline", "backend", "frontend", "fullstack", "devops", "sre", "cloud",
        "aws", "azure", "gcp", "linux", "git", "github", "gitlab", "código", "codigo", "arquitetura", "monolito",
        "microserviço", "microservico", "microsserviço", "microsservico", "endpoint", "autenticação", "autenticacao",
        "oauth", "oauth2", "jwt", "testes", "pytest", "unitário", "unitario", "refatoração", "refatoracao",
        "python", "fastapi", "flask", "django", "golang", "typescript", "javascript", "node", "java", "rust",
        "c#", "c++", "terraform", "ansible", "grafana", "prometheus", "opentelemetry", "clickhouse", "pgbouncer",
        "rest", "graphql", "grpc", "cache", "latência", "latencia", "throughput", "concorrência", "concorrencia",
        "thread", "assíncrono", "assincrono", "lead time", "sprint", "tech debt", "solid", "clean code", "dry",
        "kiss", "yagni", "tdd", "ddd", "design pattern", "agentes", "ia", "llm", "rag", "embeddings", "prompt",
        "thz-lang", "compilador", "framework", "stride", "owasp", "segurança", "seguranca", "observabilidade",
        "mensageria", "engenharia", "requisitos", "modelagem", "infraestrutura"
    ]

    # Termos e padrões estritamente proibidos (fora de escopo)
    FORBIDDEN_PATTERNS: List[Tuple[str, str, str]] = [
        # (Pattern regex, Categoria, Descrição amigável)
        (r"\b(carro|carros|veículo|veiculo|veículos|veiculos|automóvel|automovel|concessionária|concessionaria|motor v8|câmbio|cambio|embreagem|gasolina|etanol|troca de óleo|troca de oleo|tuning|escapamento|pneu|pneus|turbocharger|cilindrada)\b", "veiculos_automotores", "Veículos e mecânica automotiva"),
        (r"\b(piscina|piscinas|casa de praia|imóvel|imovel|imóveis|imoveis|aluguel por temporada|churrasqueira|jardim|área gourmet|area gourmet|condomínio fechado|condominio fechado|casa de campo|decoração de interiores|decoracao de interiores|arquitetura residencial)\b", "imoveis_e_lazer", "Imóveis residenciais, piscinas e lazer"),
        (r"\b(receita de bolo|receita culinária|culinaria|sobremesa|ingredientes para bolo|modo de preparo|cozinhar|gourmet|pastelaria|restaurante|churrasco)\b", "culinaria_e_receitas", "Culinária e receitas gastronômicas"),
        (r"\b(fofoca|bbb|big brother|novela|celebridade|celebridades|famosos|reality show|horóscopo|horoscopo|signos do zodíaco|astrologia)\b", "fofoca_e_entretenimento", "Fofoca, entretenimento e astrologia"),
        (r"\b(eleição presidencial|eleicoes|voto em candidato|partido político|partido politico|deputado|senador|presidente da república|campanha eleitoral|ideologia partidária)\b", "politica_partidaria", "Política partidária e campanhas eleitorais"),
        (r"\b(futebol|brasileirão|brasileirao|campeonato paulista|copa do mundo|escalação de time|escalacao de time|gol de placa|cartola fc)\b", "esportes_e_futebol", "Futebol e esportes recreativos"),
        (r"\b(day trade|forex|esquema de pirâmide|piramide financeira|aposta esportiva|bet365|blaze|cassino|tigrinho)\b", "apostas_e_especulacao", "Apostas e especulação financeira"),
    ]

    def validate_topic(self, topic: str) -> ScopeValidationResult:
        """Valida se um tópico ou prompt de entrada é estritamente técnico."""
        if not topic or not topic.strip():
            return ScopeValidationResult(
                allowed=False,
                category="vazio",
                reason="Tópico não pode ser vazio."
            )

        topic_clean = topic.strip().lower()

        # 1. Checagem de padrões proibidos (Blacklist)
        flagged = []
        for pattern, category, desc in self.FORBIDDEN_PATTERNS:
            matches = re.findall(pattern, topic_clean, flags=re.IGNORECASE)
            if matches:
                flagged.extend(matches)
                logger.warning(f"[SCOPE-GUARD] Bloqueado por '{desc}': termos={matches}")
                return ScopeValidationResult(
                    allowed=False,
                    category=category,
                    reason=f"Tópico rejeitado pelo Guardrail: o assunto envolve '{desc}', que está fora do escopo permitido do sistema.",
                    flagged_terms=list(set(flagged))
                )

        # 2. Checagem de pertinência técnica (Allowlist)
        has_tech_indicator = any(ind in topic_clean for ind in self.TECH_INDICATORS)

        # Se for um tópico curto sem nenhum indicativo técnico conhecido
        words = topic_clean.split()
        if len(words) < 15 and not has_tech_indicator:
            # Checar se parece pergunta técnica genérica
            tech_verbs = ["como criar", "como implementar", "comparação entre", "comparacao entre", "melhores práticas", "melhores praticas", "quando usar", "vs", "versus", "performance de"]
            is_tech_structure = any(v in topic_clean for v in tech_verbs)
            if not is_tech_structure:
                logger.info(f"[SCOPE-GUARD] Tópico sem contexto técnico evidente: '{topic}'")
                return ScopeValidationResult(
                    allowed=False,
                    category="fora_de_escopo_geral",
                    reason="Tópico rejeitado: o assunto não apresenta contexto claro de Engenharia de Software ou Tecnologia. O THZ Minds é exclusivo para temas técnicos.",
                    flagged_terms=[]
                )

        return ScopeValidationResult(
            allowed=True,
            category="engenharia_de_software",
            reason="Tópico aprovado pelo Guardrail de Escopo Técnico."
        )

    def validate_in_flight(self, content: str) -> ScopeValidationResult:
        """Valida argumentos e mensagens geradas para evitar desvios graves de tema."""
        if not content:
            return ScopeValidationResult(allowed=True, category="neutro", reason="Conteúdo vazio.")

        content_clean = content.lower()
        flagged = []
        for pattern, category, desc in self.FORBIDDEN_PATTERNS:
            matches = re.findall(pattern, content_clean, flags=re.IGNORECASE)
            # Para in-flight, permitir apenas menções rápidas se houver contexto técnico forte, mas se houver múltiplos termos, bloquear
            if len(matches) >= 2:
                flagged.extend(matches)
                return ScopeValidationResult(
                    allowed=False,
                    category=category,
                    reason=f"Desvio de conduta técnica: o argumento contém múltiplos termos fora de escopo ({desc}).",
                    flagged_terms=list(set(flagged))
                )

        return ScopeValidationResult(
            allowed=True,
            category="tecnico",
            reason="Conteúdo em conformidade técnica."
        )


_global_scope_guard = None

def get_scope_guard() -> ScopeGuard:
    global _global_scope_guard
    if _global_scope_guard is None:
        _global_scope_guard = ScopeGuard()
    return _global_scope_guard
