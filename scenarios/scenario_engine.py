"""
THZ Minds — Gerador de Cenários Complexos e Realistas do Mundo Real
Substitui tópicos genéricos e simplistas por cenários de engenharia contendo
restrições de produção (RPS, SLAs de latência, orçamento em cloud, banco de dados legado e equipe).
"""

import random
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("ThzRoom.Scenarios")


class EngineeringScenario(BaseModel):
    title: str
    category: str
    scale: str
    sla_target: str
    constraints: List[str]
    tech_stack: List[str]
    prompt: str


class ScenarioEngine:
    """Gera problemas técnicos ricos e contextuais com restrições do mundo real."""

    REALISTIC_SCENARIOS: List[EngineeringScenario] = [
        EngineeringScenario(
            title="Escalabilidade de Checkout em Black Friday com Postgres e Kafka",
            category="Arquitetura & Alta Escala",
            scale="45.000 requisições/minuto (Pico)",
            sla_target="p99 < 200ms, Disponibilidade 99.99%",
            constraints=[
                "Banco legado PostgreSQL 13 sofrendo com lock na tabela 'orders'",
                "Orçamento extra de nuvem limitado a $3.000/mês",
                "Equipe de 5 desenvolvedores backend e 1 SRE"
            ],
            tech_stack=["Python/FastAPI", "PostgreSQL", "Kafka/RabbitMQ", "Redis", "Docker/K8s"],
            prompt=(
                "Cenário de Produção: Um e-commerce nacional está preparando o sistema de checkout para a Black Friday. "
                "O sistema atual é um monólito com PostgreSQL 13 que trava por lock de tabela ao atingir 10.000 req/min. "
                "A meta é suportar 45.000 req/min com p99 < 200ms. "
                "Proponha a arquitetura assíncrona desacoplada com Debezium/Kafka, pool de conexões (PgBouncer), "
                "estratégia de idempotência com Redis e plano de contingência."
            )
        ),
        EngineeringScenario(
            title="Autenticação Centralizada OAuth2 com Rotação de JWT e Rate Limiting",
            category="Segurança & APIs",
            scale="10.000 logins/minuto, 500k usuários ativos diários",
            sla_target="Validação de token < 15ms",
            constraints=[
                "Compliance com LGPD e OWASP Top 10",
                "Tokens com expiração curta (15 min) e Refresh Token em rotação",
                "Rate limit distribuído por IP e por Tenant"
            ],
            tech_stack=["Go / Python", "Redis Cluster", "PostgreSQL", "Vault", "Envoy/Nginx"],
            prompt=(
                "Cenário de Produção: Uma fintech precisa construir um microsserviço de autenticação e autorização seguro. "
                "O serviço deve emitir tokens JWT assimétricos (RS256) com rotação periódica de chaves públicas via JWKS, "
                "armazenar sessões e rate limits no Redis Cluster com algoritmo Token Bucket, "
                "e garantir proteção contra ataques de força bruta e replay."
            )
        ),
        EngineeringScenario(
            title="Migração Zero-Downtime de Banco de Dados Relacional Monolítico",
            category="Bancos de Dados & Resiliência",
            scale="Base de dados de 4.2 Terabytes, 800 GB em tabelas transacionais críticas",
            sla_target="Downtime máximo tolerado: 0 segundos (Zero Downtime)",
            constraints=[
                "Migração de PostgreSQL on-premise para AWS Aurora PostgreSQL Serverless",
                "Manter consistência transacional e replicação bidirecional durante a transição",
                "Plano de rollback instantâneo sem perda de transações"
            ],
            tech_stack=["PostgreSQL", "AWS DMS / Debezium", "Flyway / Liquibase", "Terraform"],
            prompt=(
                "Cenário de Produção: Uma plataforma de pagamentos precisa migrar seu banco de dados principal de 4.2 TB "
                "para uma infraestrutura gerenciada em nuvem sem nenhum minuto de indisponibilidade. "
                "Defina a estratégia usando o padrão Expand and Contract (Blue/Green de banco), replicação lógica contínua "
                "e testes de validação de consistência de dados em tempo real."
            )
        ),
        EngineeringScenario(
            title="Pipeline de Ingestão de Telemetria e Logs com OpenTelemetry e ClickHouse",
            category="Observabilidade & Big Data",
            scale="150.000 eventos de telemetria por segundo (Logs, Traces, Metrics)",
            sla_target="Atraso de indexação < 3 segundos, Retenção de 90 dias",
            constraints=[
                "Elasticsearch atual está custando $18.000/mês e estourando consumo de memória",
                "Reduzir custo de infraestrutura em 60% usando ClickHouse e Vector/FluentBit",
                "Dashboards unificados no Grafana com amostragem inteligente de traces"
            ],
            tech_stack=["OpenTelemetry Collector", "ClickHouse", "Vector", "Grafana", "Kubernetes"],
            prompt=(
                "Cenário de Produção: O cluster Elasticsearch da empresa está com custos insustentáveis para armazenar 150k logs/seg. "
                "O time precisa projetar uma nova pipeline de observabilidade baseada em OpenTelemetry Collector, "
                "ingestão via Kafka e armazenamento colunar compactado no ClickHouse, reduzindo custos e acelerando queries analíticas."
            )
        ),
        EngineeringScenario(
            title="Plataforma de Execução Segura de Funções Serverless com Isolamento e Sandbox",
            category="Sistemas Operacionais & Runtime",
            scale="Execução de 5.000 scripts/minuto submetidos por clientes",
            sla_target="Tempo de inicialização (Cold Start) < 50ms, Timeout máximo de 5s",
            constraints=[
                "Isolamento estrito entre tenants (sem vazamento de memória ou arquivos)",
                "Prevenção contra fork-bombs, consumo abusivo de CPU e chamadas de rede não autorizadas",
                "Suporte a Python e JavaScript"
            ],
            tech_stack=["gVisor / Firecracker", "Docker / Podman", "Linux cgroups v2 / namespaces", "Rust / Go"],
            prompt=(
                "Cenário de Produção: Uma startup de automação precisa permitir que usuários enviem scripts customizados "
                "para rodar em sua plataforma. Projete o motor de execução segura utilizando MicroVMs Firecracker ou gVisor, "
                "com restrições rígidas de CPU/RAM via cgroups v2, limites de I/O de disco e rede completamente bloqueada por padrão."
            )
        ),
    ]

    CONTENT_TOPICS: List[str] = [
        "Arquitetura Hexagonal na Prática: Construindo Microsserviços Desacoplados com Python e FastAPI",
        "Por que seu Banco de Dados Trava: Guia Definitivo de Connection Pooling, Locks e Índices no PostgreSQL",
        "Zero-Trust na Prática: Implementando mTLS e Rotação de Chaves em Ambientes Kubernetes",
        "Do Monólito aos Microsserviços sem Dor: Estratégias de Strangler Fig Pattern e Event-Driven com Kafka",
        "Como Reduzir 70% da sua Conta de Nuvem: Padrões Reais de FinOps e Dimensionamento de Containers",
        "Observabilidade de Alta Performance: Substituindo Elasticsearch por ClickHouse e OpenTelemetry",
        "Idempotência em Sistemas Distribuídos: Como Evitar Cobranças Duplicadas em APIs de Pagamento",
    ]

    def get_random_engineering_scenario(self) -> EngineeringScenario:
        """Retorna um cenário rico de engenharia aleatório."""
        return random.choice(self.REALISTIC_SCENARIOS)

    def get_random_content_topic(self) -> str:
        """Retorna um tema aprofundado para artigo técnico."""
        return random.choice(self.CONTENT_TOPICS)

    def format_scenario_prompt(self, scenario: EngineeringScenario) -> str:
        """Formata o cenário completo para ser usado como prompt de debate ou teamwork."""
        return (
            f"**CENÁRIO DE ENGENHARIA:** {scenario.title}\n\n"
            f"📊 **Escala Alvo:** {scenario.scale}\n"
            f"🎯 **SLA / SLO:** {scenario.sla_target}\n"
            f"⚠️ **Restrições de Produção:**\n" +
            "\n".join(f"- {c}" for c in scenario.constraints) +
            f"\n\n🛠️ **Stack Sugerida:** {', '.join(scenario.tech_stack)}\n\n"
            f"📝 **Desafio Técnico:** {scenario.prompt}"
        )


_global_scenario_engine = None

def get_scenario_engine() -> ScenarioEngine:
    global _global_scenario_engine
    if _global_scenario_engine is None:
        _global_scenario_engine = ScenarioEngine()
    return _global_scenario_engine
