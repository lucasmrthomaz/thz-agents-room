"""
Testes para a classe CortexDB do THz Room
"""

import pytest
import pytest_asyncio

# Marca todos os testes deste arquivo como asyncio
pytestmark = pytest.mark.asyncio


class TestCortexDB:
    """Testes para operacoes do banco de dados Cortex."""

    async def test_init_db(self, temp_db):
        """Testa inicializacao do banco de dados."""
        import aiosqlite

        # Verifica se o banco foi criado
        assert temp_db.exists()

        # Verifica se as tabelas foram criadas
        async with aiosqlite.connect(temp_db) as db:
            tables = await db.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table';"
            )
            table_names = [t[0] for t in tables]

            assert "conversations" in table_names
            assert "messages" in table_names
            assert "topic_memory" in table_names
            assert "agent_skills" in table_names
            assert "debate_patterns" in table_names
            assert "content_references" in table_names

    async def test_save_conversation(self, temp_db):
        """Testa salvamento de conversa."""
        import aiosqlite
        from server import CortexDB

        conv_id = "test-conv-001"
        topic = "Kafka vs RabbitMQ"
        session_id = "test-session"

        await CortexDB.save_conversation(conv_id, topic, session_id)

        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM conversations WHERE id = ?;", (conv_id,)
            )
            assert len(rows) == 1
            assert rows[0][0] == conv_id
            assert rows[0][1] == topic
            assert rows[0][2] == session_id

    async def test_save_message(self, temp_db):
        """Testa salvamento de mensagem."""
        import aiosqlite
        from server import CortexDB

        # Primeiro cria uma conversa
        conv_id = "test-conv-002"
        await CortexDB.save_conversation(conv_id, "Teste")

        # Salva mensagem
        await CortexDB.save_message(
            conv_id,
            "Arquiteto",
            "Kafka e melhor para alta volumetria",
            "CONTINUE",
            1
        )

        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM messages WHERE conversation_id = ?;", (conv_id,)
            )
            assert len(rows) == 1
            assert rows[0][2] == "Arquiteto"  # agent_name
            assert rows[0][3] == "Kafka e melhor para alta volumetria"  # content
            assert rows[0][4] == "CONTINUE"  # status
            assert rows[0][5] == 1  # turn

    async def test_update_topic_memory_new(self, temp_db):
        """Testa insercao de novo topico na memoria."""
        import aiosqlite
        from server import CortexDB

        topic = "Kafka vs RabbitMQ"
        await CortexDB.update_topic_memory(topic, True)

        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM topic_memory WHERE topic = ?;", (topic,)
            )
            assert len(rows) == 1
            assert rows[0][1] == topic
            assert rows[0][3] == 1  # times_discussed
            assert rows[0][4] == 1  # last_consensus (True = 1)

    async def test_update_topic_memory_existing(self, temp_db):
        """Testa atualizacao de topico existente na memoria."""
        import aiosqlite
        from server import CortexDB

        topic = "Docker vs Podman"

        # Primeira discussao
        await CortexDB.update_topic_memory(topic, True)

        # Segunda discussao
        await CortexDB.update_topic_memory(topic, False)

        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT times_discussed, last_consensus FROM topic_memory WHERE topic = ?;",
                (topic,)
            )
            assert len(rows) == 1
            assert rows[0][0] == 2  # times_discussed
            assert rows[0][1] == 0  # last_consensus (False = 0)

    async def test_update_agent_skills_new(self, temp_db):
        """Testa insercao de nova skill de agente."""
        import aiosqlite
        from server import CortexDB

        await CortexDB.update_agent_skills("Arquiteto", "arquitetura", True)

        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM agent_skills WHERE agent_name = 'Arquiteto';"
            )
            assert len(rows) == 1
            assert rows[0][1] == "Arquiteto"
            assert rows[0][2] == "arquitetura"
            assert rows[0][3] == 1.0  # expertise_level (1/1 = 1.0)
            assert rows[0][4] == 1  # times_applied
            assert rows[0][5] == 1  # consensus_contributions

    async def test_update_agent_skills_existing(self, temp_db):
        """Testa atualizacao de skill existente."""
        import aiosqlite
        from server import CortexDB

        # Primeira contribuicao (consenso)
        await CortexDB.update_agent_skills("SRE", "tolerancia a falhas", True)

        # Segunda contribuicao (sem consenso)
        await CortexDB.update_agent_skills("SRE", "tolerancia a falhas", False)

        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT times_applied, consensus_contributions, expertise_level "
                "FROM agent_skills WHERE agent_name = 'SRE';"
            )
            assert len(rows) == 1
            assert rows[0][0] == 2  # times_applied
            assert rows[0][1] == 1  # consensus_contributions
            # expertise_level = 1/2 = 0.5
            assert abs(rows[0][2] - 0.5) < 0.01

    async def test_get_discussed_topics(self, temp_db):
        """Testa recuperacao de topicos discutidos."""
        from server import CortexDB

        # Insere topicos
        await CortexDB.update_topic_memory("Topico A", True)
        await CortexDB.update_topic_memory("Topico B", False)
        await CortexDB.update_topic_memory("Topico C", True)

        topics = await CortexDB.get_discussed_topics()

        assert len(topics) == 3
        assert "Topico A" in topics
        assert "Topico B" in topics
        assert "Topico C" in topics

    async def test_get_agent_skills(self, temp_db):
        """Testa recuperacao de skills dos agentes."""
        from server import CortexDB

        # Insere skills
        await CortexDB.update_agent_skills("Arquiteto", "arquitetura", True)
        await CortexDB.update_agent_skills("SRE", "resiliencia", True)

        skills = await CortexDB.get_agent_skills()

        assert "Arquiteto" in skills
        assert "SRE" in skills
        assert len(skills["Arquiteto"]) == 1
        assert skills["Arquiteto"][0]["domain"] == "arquitetura"

    async def test_cascade_delete_conversation(self, temp_db):
        """Testa cascade delete de conversa e mensagens."""
        import aiosqlite
        from server import CortexDB

        conv_id = "test-conv-cascade"
        await CortexDB.save_conversation(conv_id, "Teste cascade")
        await CortexDB.save_message(conv_id, "Agente", "Mensagem", "CONTINUE", 1)

        # Verifica que existe
        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM messages WHERE conversation_id = ?;", (conv_id,)
            )
            assert len(rows) == 1

        # Deleta conversa com CASCADE
        async with aiosqlite.connect(temp_db) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("DELETE FROM messages WHERE conversation_id = ?;", (conv_id,))
            await db.execute("DELETE FROM conversations WHERE id = ?;", (conv_id,))
            await db.commit()

        # Verifica que mensagens foram deletadas
        async with aiosqlite.connect(temp_db) as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM messages WHERE conversation_id = ?;", (conv_id,)
            )
            assert len(rows) == 0
