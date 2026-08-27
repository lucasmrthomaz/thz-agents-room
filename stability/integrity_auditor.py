import os, hashlib, json, logging, aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger('ThzRoom.Stability.IntegrityAuditor')
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

class IntegrityAuditor:
    @staticmethod
    def calculate_file_sha256(filepath: Path) -> Optional[str]:
        if not filepath.exists() or not filepath.is_file():
            return None
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    async def audit_repository(base_dir: Optional[Path] = None) -> Dict[str, Any]:
        root = base_dir or WORKSPACE_ROOT
        db_path = root / 'data' / 'thz-room-cortex.db'
        output_dir = root / 'output'
        sessions_dir = root / 'sessions'
        verified_files = []
        missing_files = []
        tampered_files = []
        orphan_files = []
        db_tracked_paths = set()
        db_records_count = 0
        if db_path.exists():
            async with aiosqlite.connect(db_path) as db:
                try:
                    rows = await db.execute_fetchall('SELECT session_id, project_name, file_path, file_type, author_role, content_length, artifact_uuid, sha256_hash, created_at FROM teamwork_artifacts;')
                    db_records_count = len(rows)
                    for r in rows:
                        s_id, p_name, f_path, f_type, role, c_len, art_uuid, expected_sha, created_at = r
                        disk_path = output_dir / p_name / f_path
                        db_tracked_paths.add(str(disk_path.resolve()))
                        if not disk_path.exists():
                            missing_files.append({'session_id': s_id, 'project_name': p_name, 'file_path': f_path, 'author_role': role, 'expected_sha256': expected_sha, 'status': 'MISSING_ON_DISK', 'created_at': created_at})
                        else:
                            current_sha = IntegrityAuditor.calculate_file_sha256(disk_path)
                            if expected_sha and current_sha != expected_sha:
                                tampered_files.append({'session_id': s_id, 'project_name': p_name, 'file_path': f_path, 'author_role': role, 'expected_sha256': expected_sha, 'actual_sha256': current_sha, 'status': 'TAMPERED_OR_MODIFIED', 'created_at': created_at})
                            else:
                                verified_files.append({'session_id': s_id, 'project_name': p_name, 'file_path': f_path, 'author_role': role, 'sha256_hash': current_sha, 'size_bytes': disk_path.stat().st_size, 'status': 'VERIFIED_INTACT', 'created_at': created_at})
                except Exception as e:
                    logger.warning(f'Erro auditoria: {e}')
        if output_dir.exists():
            for p in output_dir.rglob('*'):
                if p.is_file():
                    if p.name in ['project_manifest.json', 'metadata.json'] or '__pycache__' in p.parts:
                        continue
                    if str(p.resolve()) not in db_tracked_paths:
                        orphan_files.append({'relative_path': str(p.relative_to(output_dir)), 'size_bytes': p.stat().st_size, 'sha256_hash': IntegrityAuditor.calculate_file_sha256(p), 'status': 'ORPHAN_ON_DISK'})
        total_checked = len(verified_files) + len(missing_files) + len(tampered_files)
        integrity_score = (len(verified_files) / total_checked * 100.0) if total_checked > 0 else 100.0
        return {'audit_timestamp': datetime.now().isoformat(), 'integrity_score_pct': round(integrity_score, 2), 'status': 'HEALTHY' if integrity_score >= 99.0 and not missing_files else 'WARNING', 'summary': {'total_tracked_in_db': db_records_count, 'verified_intact': len(verified_files), 'missing_on_disk': len(missing_files), 'tampered_or_modified': len(tampered_files), 'orphans_on_disk': len(orphan_files)}, 'details': {'missing_files': missing_files, 'tampered_files': tampered_files, 'orphan_files': orphan_files, 'sample_verified': verified_files[:10]}}

    @staticmethod
    async def reconcile_and_backfill(base_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Varre todos os projetos em output/, sincroniza manifestos existentes com o banco SQLite Cortex,
        preenche registros ausentes com SHA-256 e UUIDs, tornando o Livro-Verdade 100% consistente.
        """
        root = base_dir or WORKSPACE_ROOT
        db_path = root / 'data' / 'thz-room-cortex.db'
        output_dir = root / 'output'

        if not db_path.exists() or not output_dir.exists():
            return {"reconciled_count": 0, "status": "NO_DATA"}

        try:
            from server import CortexDB
            await CortexDB.init()
        except Exception:
            pass

        import uuid as _uuid
        reconciled_count = 0

        async with aiosqlite.connect(db_path) as db:
            for proj_dir in output_dir.iterdir():
                if not proj_dir.is_dir() or proj_dir.name.startswith("."):
                    continue

                p_name = proj_dir.name
                manifest_file = proj_dir / "project_manifest.json"
                meta_file = proj_dir / "metadata.json"

                mode = "content" if p_name.startswith("article_") else "engineering"
                goal = p_name

                if meta_file.exists():
                    try:
                        m_data = json.loads(meta_file.read_text(encoding="utf-8"))
                        goal = m_data.get("topic", m_data.get("goal", goal))
                        mode = m_data.get("mode", mode)
                    except Exception:
                        pass

                # Inserir ou garantir sessão
                await db.execute("""
                    INSERT OR IGNORE INTO teamwork_sessions
                        (id, project_name, mode, goal, status, output_dir, total_steps)
                    VALUES (?, ?, ?, ?, 'completed', ?, ?);
                """, (p_name, p_name, mode, goal, str(proj_dir.resolve()), 6 if mode == "content" else 7))

                # Ler arquivos da pasta
                for f_path in proj_dir.rglob("*"):
                    if not f_path.is_file() or f_path.name in ["project_manifest.json", "metadata.json"] or "__pycache__" in f_path.parts:
                        continue

                    rel_path = str(f_path.relative_to(proj_dir)).replace("\\", "/")
                    sha256_hash = IntegrityAuditor.calculate_file_sha256(f_path)
                    content_len = f_path.stat().st_size
                    art_uuid = f"art_{_uuid.uuid4().hex[:12]}"

                    ext = f_path.suffix.lower()
                    if ext in [".py", ".ts", ".js", ".go"]:
                        f_type = "code"
                    elif ext == ".sql":
                        f_type = "sql"
                    elif ext in [".yaml", ".yml"]:
                        f_type = "yaml"
                    elif ext == ".md":
                        f_type = "markdown"
                    else:
                        f_type = "config"

                    # Verificar se já existe no banco
                    existing = await db.execute_fetchall("""
                        SELECT id FROM teamwork_artifacts WHERE project_name = ? AND file_path = ?;
                    """, (p_name, rel_path))

                    if not existing:
                        await db.execute("""
                            INSERT INTO teamwork_artifacts
                                (session_id, project_name, file_path, file_type, author_role, content_length, artifact_uuid, sha256_hash)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """, (p_name, p_name, rel_path, f_type, "Especialista", content_len, art_uuid, sha256_hash))
                        reconciled_count += 1
                    else:
                        # Atualizar SHA e UUID caso estejam nulos
                        await db.execute("""
                            UPDATE teamwork_artifacts
                            SET sha256_hash = coalesce(sha256_hash, ?),
                                artifact_uuid = coalesce(artifact_uuid, ?)
                            WHERE project_name = ? AND file_path = ?;
                        """, (sha256_hash, art_uuid, p_name, rel_path))

            await db.commit()

        logger.info(f"[INTEGRITY-AUDIT] Reconciliação concluída: {reconciled_count} artefatos sincronizados.")
        return {"reconciled_count": reconciled_count, "status": "SUCCESS"}
