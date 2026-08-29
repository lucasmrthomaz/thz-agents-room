"""
THZ Minds — Configuracao centralizada
Carrega variaveis de .env via python-dotenv com fallbacks seguros.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


class Settings:
    """Configuracao centralizada do THZ Minds."""

    # Server
    PORT: int = int(os.getenv("PORT", "9983"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    WORKERS: int = int(os.getenv("WORKERS", "1"))

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_CHAT_URL: str = f"{OLLAMA_BASE_URL}/api/chat"
    OLLAMA_EMBED_URL: str = f"{OLLAMA_BASE_URL}/api/embed"

    # Modelos
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "qwen2.5:7b")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "768"))

    # Debate
    CONSENSUS_THRESHOLD: int = int(os.getenv("CONSENSUS_THRESHOLD", "5"))
    LANGUAGE: str = os.getenv("LANGUAGE", "pt-BR")

    # Paths
    DATA_DIR: Path = BASE_DIR / os.getenv("DATA_DIR", "data")
    SESSIONS_DIR: Path = BASE_DIR / os.getenv("SESSIONS_DIR", "sessions")
    OUTPUT_DIR: Path = BASE_DIR / os.getenv("OUTPUT_DIR", "output")
    DB_PATH: Path = DATA_DIR / os.getenv("DB_PATH", "thz-room-cortex.db")

    # Derivados
    SERVER_URL: str = f"http://127.0.0.1:{PORT}"
    WS_URI: str = os.getenv("WS_URI", f"ws://127.0.0.1:{PORT}/ws/debate")


settings = Settings()
