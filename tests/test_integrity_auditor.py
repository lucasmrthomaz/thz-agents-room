import pytest, asyncio
from pathlib import Path
from stability.integrity_auditor import IntegrityAuditor
import aiosqlite

class TestIntegrityAuditor:
    @pytest.mark.asyncio
    async def test_audit_detects_verified_and_missing_and_tampered(self, tmp_path):
        db_dir = tmp_path / 'data'
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / 'thz-room-cortex.db'
        output_dir = tmp_path / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)
        proj1 = output_dir / 'proj1'
        proj1.mkdir(parents=True, exist_ok=True)
        f1 = proj1 / 'app.py'
        f1.write_text('print(1)', encoding='utf-8')
        sha1 = IntegrityAuditor.calculate_file_sha256(f1)
        f2 = proj1 / 'tampered.py'
        f2.write_text('modificado', encoding='utf-8')
        expected_sha2 = 'hash_antigo_diferente'
        async with aiosqlite.connect(db_path) as db:
            await db.execute('CREATE TABLE teamwork_artifacts (id INTEGER PRIMARY KEY, session_id TEXT, project_name TEXT, file_path TEXT, file_type TEXT, author_role TEXT, content_length INTEGER, artifact_uuid TEXT, sha256_hash TEXT, created_at DATETIME);')
            await db.execute('INSERT INTO teamwork_artifacts (session_id, project_name, file_path, file_type, author_role, content_length, artifact_uuid, sha256_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?);', ('s1', 'proj1', 'app.py', 'code', 'Dev', 8, 'u1', sha1))
            await db.execute('INSERT INTO teamwork_artifacts (session_id, project_name, file_path, file_type, author_role, content_length, artifact_uuid, sha256_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?);', ('s1', 'proj1', 'tampered.py', 'code', 'Dev', 10, 'u2', expected_sha2))
            await db.execute('INSERT INTO teamwork_artifacts (session_id, project_name, file_path, file_type, author_role, content_length, artifact_uuid, sha256_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?);', ('s1', 'proj1', 'missing.py', 'code', 'Dev', 10, 'u3', 'sha_missing'))
            await db.commit()
        report = await IntegrityAuditor.audit_repository(base_dir=tmp_path)
        assert report['summary']['total_tracked_in_db'] == 3
        assert report['summary']['verified_intact'] == 1
        assert report['summary']['missing_on_disk'] == 1
        assert report['summary']['tampered_or_modified'] == 1
        assert report['status'] == 'WARNING'
