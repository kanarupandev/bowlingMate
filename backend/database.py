import sqlite3
from typing import List, Dict, Any, Optional
import datetime

DB_NAME = "bowling.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bowl_num INTEGER,
            summary TEXT,
            speed_est TEXT,
            config TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # New table for persistent deliveries with cloud URLs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deliveries (
            id TEXT PRIMARY KEY,
            sequence INTEGER,
            cloud_video_url TEXT,
            cloud_thumbnail_url TEXT,
            release_timestamp REAL,
            speed TEXT,
            report TEXT,
            tips TEXT,
            status TEXT DEFAULT 'success',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def insert_summary(bowl_num: int, summary: str, speed_est: str, config: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO summaries (bowl_num, summary, speed_est, config)
        VALUES (?, ?, ?, ?)
    ''', (bowl_num, summary, speed_est, config))
    conn.commit()
    conn.close()

def get_summaries(limit: int = 5, config: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM summaries"
    params = []
    
    if config:
        query += " WHERE config = ?"
        params.append(config)
        
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_next_bowl_num() -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(bowl_num) FROM summaries")
    result = cursor.fetchone()
    conn.close()
    return (result[0] or 0) + 1


# ============ Delivery CRUD ============

def insert_delivery(
    delivery_id: str,
    sequence: int,
    cloud_video_url: str,
    cloud_thumbnail_url: str,
    release_timestamp: float = 0.0,
    speed: str = None,
    report: str = None,
    tips: str = None,
    status: str = "success"
):
    """Insert a new delivery with cloud URLs."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO deliveries 
        (id, sequence, cloud_video_url, cloud_thumbnail_url, release_timestamp, speed, report, tips, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (delivery_id, sequence, cloud_video_url, cloud_thumbnail_url, release_timestamp, speed, report, tips, status))
    conn.commit()
    conn.close()


def get_deliveries(limit: int = 50) -> List[Dict[str, Any]]:
    """Get all deliveries, newest first."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deliveries ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_delivery(delivery_id: str) -> Optional[Dict[str, Any]]:
    """Get a single delivery by ID."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_next_delivery_sequence() -> int:
    """Get next delivery sequence number."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(sequence) FROM deliveries")
    result = cursor.fetchone()
    conn.close()
    return (result[0] or 0) + 1
