import sqlite3
import uuid
import time
from pathlib import Path
from typing import List, Dict, Optional

from src.config import env_config

class ShareManager:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            self.base_dir = Path(env_config.DATA_DIR)
        else:
            self.base_dir = Path(data_dir)
            
        self.shares_dir = self.base_dir / "shares"
        self.shares_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.shares_dir / "metadata.db"
        self._init_db()

    def _get_connection(self):
        # Using timeout to handle concurrent accesses gracefully
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shares (
                    id TEXT PRIMARY KEY,
                    session_name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    file_path TEXT NOT NULL,
                    theme TEXT DEFAULT 'dark'
                )
            """)
            
            # Try to add 'theme' column to existing table to support older databases
            try:
                conn.execute("ALTER TABLE shares ADD COLUMN theme TEXT DEFAULT 'dark'")
            except sqlite3.OperationalError:
                pass # Column already exists
                
            conn.commit()

    def create_share(self, html_content: str, session_name: str, theme: str = 'dark') -> str:
        """
        Generates UUID, saves HTML to disk, updates metadata.
        Returns the new share ID.
        """
        share_id = str(uuid.uuid4())
        file_path = self.shares_dir / f"{share_id}.html"
        
        # Write HTML content to disk
        file_path.write_text(html_content, encoding="utf-8")
        
        created_at = time.time()
        
        # Update metadata
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO shares (id, session_name, created_at, file_path, theme) VALUES (?, ?, ?, ?, ?)",
                (share_id, session_name, created_at, str(file_path), theme)
            )
            conn.commit()
            
        return share_id

    def get_share_metadata(self, share_id: str) -> Optional[Dict]:
        """
        Returns the metadata for a given share_id or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, session_name, created_at, file_path, theme FROM shares WHERE id = ?",
                (share_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def list_shares(self) -> List[Dict]:
        """
        Returns all active shares, ordered by creation time descending.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, session_name, created_at, file_path, theme FROM shares ORDER BY created_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_share(self, share_id: str) -> bool:
        """
        Removes HTML file and metadata entry. Returns True if deleted, False if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT file_path FROM shares WHERE id = ?", (share_id,))
            row = cursor.fetchone()
            if not row:
                return False
                
            file_path = Path(row['file_path'])
            
            # Delete file if exists
            if file_path.exists():
                file_path.unlink()
                
            # Delete metadata
            conn.execute("DELETE FROM shares WHERE id = ?", (share_id,))
            conn.commit()
            
        return True
