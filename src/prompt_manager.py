import sqlite3
import uuid
import time
from pathlib import Path
from typing import List, Dict, Optional

from src.config import env_config


class PromptManager:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            self.base_dir = Path(env_config.DATA_DIR)
        else:
            self.base_dir = Path(data_dir)

        self.prompts_dir = self.base_dir / "prompts"
        try:
            self.prompts_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = self.prompts_dir / "metadata.db"
            self._init_db()
        except OSError:
            # Fallback for read-only environments
            self.db_path = ":memory:"
            pass

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    is_default INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    def list_prompts(self) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, text, is_default, created_at, updated_at FROM prompts ORDER BY created_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_prompt(self, name: str, text: str, is_default: int = 0) -> str:
        prompt_id = str(uuid.uuid4())
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO prompts (id, name, text, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (prompt_id, name, text, is_default, now, now),
            )
            conn.commit()
        return prompt_id

    def update_prompt(self, prompt_id: str, name: str, text: str) -> bool:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE prompts SET name = ?, text = ?, updated_at = ? WHERE id = ? AND is_default = 0",
                (name, text, now, prompt_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_prompt(self, prompt_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM prompts WHERE id = ? AND is_default = 0", (prompt_id,)
            )
            conn.commit()
            return cursor.rowcount > 0


prompt_manager = PromptManager()
