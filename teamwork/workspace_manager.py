"""
THZ Minds — Workspace Manager
Extrai blocos de arquivos de saídas de texto de agentes e grava projetos físicos
de forma segura e atômica dentro de output/<project_id>/, respeitando os Guardrails de Sandbox.
"""

import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from guardrails.sandbox import PathValidator, SandboxSecurityError
from .models import TeamworkArtifact

logger = logging.getLogger("ThzRoom.Teamwork.Workspace")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = WORKSPACE_ROOT / "output"


class WorkspaceManager:
    """Gerencia a extração, escrita e leitura segura de arquivos de projetos gerados."""

    @staticmethod
    def extract_artifacts_from_text(text: str, author_role: str = "Agente") -> List[TeamworkArtifact]:
        """Extrai artefatos estruturados a partir de marcadores '### FILE: caminho' ou code blocks."""
        artifacts: List[TeamworkArtifact] = []
        if not text:
            return artifacts

        # Padrão: ### FILE: caminho/do/arquivo.ext\n```lang\nconteúdo\n```
        file_pattern = re.compile(
            r"(?:###\s*FILE:\s*|#\s*Arquivo:\s*|/\*\s*FILE:\s*)([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)\s*[\r\n]+```(?:[a-zA-Z0-9_\-]+)?\s*[\r\n]+([\s\S]*?)```",
            re.IGNORECASE
        )

        for match in file_pattern.finditer(text):
            raw_path = match.group(1).strip().replace("\\", "/")
            content = match.group(2)

            # Normalizar path removendo barras iniciais
            clean_path = raw_path.lstrip("/")

            # Identificar tipo
            ext = Path(clean_path).suffix.lower()
            if ext in {".py", ".go", ".ts", ".js", ".java", ".rs", ".c", ".cpp"}:
                f_type = "code"
            elif ext in {".sql"}:
                f_type = "sql"
            elif ext in {".yaml", ".yml"}:
                f_type = "yaml"
            elif ext in {".json"}:
                f_type = "json"
            elif ext in {".md", ".txt"}:
                f_type = "markdown"
            else:
                f_type = "config"

            artifacts.append(TeamworkArtifact(
                path=clean_path,
                content=content,
                file_type=f_type,
                author_role=author_role,
                created_at=datetime.now().isoformat()
            ))

        return artifacts

    @staticmethod
    def save_artifacts(project_id: str, artifacts: List[TeamworkArtifact], base_dir: Optional[Path] = None) -> Path:
        """Salva a lista de artefatos no disco sob output/<project_id>/ de forma isolada e deduplicada."""
        root = base_dir or OUTPUT_ROOT
        project_dir = (root / project_id).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)

        # Deduplicar artefatos por path (versão mais recente sobrescreve)
        unique_artifacts: Dict[str, TeamworkArtifact] = {}
        for art in artifacts:
            unique_artifacts[art.path] = art

        final_artifacts = list(unique_artifacts.values())

        for art in final_artifacts:
            try:
                target_file = PathValidator.validate_safe_write_path(art.path, project_id, base_dir=root)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(art.content, encoding="utf-8")
                logger.info(f"[WORKSPACE] Arquivo salvo com sucesso: {art.path} ({len(art.content)} chars)")
            except SandboxSecurityError as sec_err:
                logger.error(f"[WORKSPACE] Violação de segurança bloqueada ao salvar {art.path}: {sec_err}")
            except Exception as e:
                logger.error(f"[WORKSPACE] Erro ao salvar {art.path}: {e}")

        # Salvar manifesto do projeto com metadados estruturados
        try:
            manifest_data = {
                "project_id": project_id,
                "created_at": datetime.now().isoformat(),
                "total_files": len(final_artifacts),
                "files": [
                    {
                        "path": a.path,
                        "file_type": a.file_type,
                        "author_role": a.author_role,
                        "size_bytes": len(a.content.encode("utf-8"))
                    }
                    for a in final_artifacts
                ]
            }
            manifest_file = project_dir / "project_manifest.json"
            manifest_file.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[WORKSPACE] Erro ao gravar manifest: {e}")

        return project_dir

    @staticmethod
    def get_project_tree(project_id: str) -> List[Dict[str, Any]]:
        """Lista os arquivos gerados de um projeto."""
        project_dir = OUTPUT_ROOT / project_id
        if not project_dir.exists():
            return []

        files = []
        for path in project_dir.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(project_dir).as_posix()
                files.append({
                    "path": rel_path,
                    "size_bytes": path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat()
                })
        return files

    @staticmethod
    def get_all_projects_summary() -> List[Dict[str, Any]]:
        """Retorna todos os projetos criados no diretório output/ com seus metadados."""
        if not OUTPUT_ROOT.exists():
            return []

        projects = []
        for p in sorted(OUTPUT_ROOT.iterdir(), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
            if p.is_dir():
                manifest_file = p / "project_manifest.json"
                if manifest_file.exists():
                    try:
                        data = json.loads(manifest_file.read_text(encoding="utf-8"))
                        projects.append({
                            "project_id": p.name,
                            "created_at": data.get("created_at", datetime.fromtimestamp(p.stat().st_mtime).isoformat()),
                            "total_files": data.get("total_files", len(list(p.rglob("*")))),
                            "files": data.get("files", []),
                            "path": str(p)
                        })
                        continue
                    except Exception:
                        pass

                # Fallback se não houver manifest
                file_list = []
                for f in p.rglob("*"):
                    if f.is_file():
                        file_list.append({
                            "path": f.relative_to(p).as_posix(),
                            "size_bytes": f.stat().st_size,
                            "file_type": f.suffix.replace(".", "") or "text",
                            "author_role": "TeamWork"
                        })

                projects.append({
                    "project_id": p.name,
                    "created_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                    "total_files": len(file_list),
                    "files": file_list,
                    "path": str(p)
                })

        return projects
