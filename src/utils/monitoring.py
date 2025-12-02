from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from typing import Optional


class MonitoringHandler:
    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        
    def connect(self, db_path: str = "monitoring.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()
    
    def _create_tables(self):
        if not self.conn:
            return
            
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                duration_ms REAL NOT NULL,
                user_agent TEXT,
                ip_address TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT
            )
        """)
        self.conn.commit()
    
    def log_request(self, method: str, path: str, status_code: int, duration_ms: float, user_agent: str = "", ip_address: str = ""):
        if not self.conn:
            return
            
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO api_requests (timestamp, method, path, status_code, duration_ms, user_agent, ip_address) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), method, path, status_code, duration_ms, user_agent, ip_address)
        )
        self.conn.commit()
    
    def log_error(self, method: str, path: str, error_type: str, error_message: str = ""):
        if not self.conn:
            return
            
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO api_errors (timestamp, method, path, error_type, error_message) VALUES (?, ?, ?, ?, ?)",
            (time.time(), method, path, error_type, error_message)
        )
        self.conn.commit()
    
    def get_stats(self, hours: int = 24):
        if not self.conn:
            return {}
        
        cutoff_time = time.time() - (hours * 3600)
        cursor = self.conn.cursor()
        
        # Total requests
        cursor.execute("SELECT COUNT(*) FROM api_requests WHERE timestamp > ?", (cutoff_time,))
        total_requests = cursor.fetchone()[0]
        
        # Average response time
        cursor.execute("SELECT AVG(duration_ms) FROM api_requests WHERE timestamp > ?", (cutoff_time,))
        avg_response_time = cursor.fetchone()[0] or 0
        
        # Status code distribution
        cursor.execute("SELECT status_code, COUNT(*) FROM api_requests WHERE timestamp > ? GROUP BY status_code", (cutoff_time,))
        status_distribution = dict(cursor.fetchall())
        
        # Top endpoints
        cursor.execute("SELECT path, COUNT(*) as count FROM api_requests WHERE timestamp > ? GROUP BY path ORDER BY count DESC LIMIT 10", (cutoff_time,))
        top_endpoints = cursor.fetchall()
        
        # Recent errors
        cursor.execute("SELECT timestamp, method, path, error_type, error_message FROM api_errors WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 20", (cutoff_time,))
        recent_errors = [
            {
                "timestamp": datetime.fromtimestamp(row[0]).strftime("%Y-%m-%d %H:%M:%S"),
                "method": row[1],
                "path": row[2],
                "error_type": row[3],
                "error_message": row[4]
            }
            for row in cursor.fetchall()
        ]
        
        return {
            "total_requests": total_requests,
            "avg_response_time_ms": round(avg_response_time, 2),
            "status_distribution": status_distribution,
            "top_endpoints": [{"path": path, "count": count} for path, count in top_endpoints],
            "recent_errors": recent_errors,
            "timeframe_hours": hours
        }
    
    def shutdown(self):
        if self.conn:
            self.conn.close()
            self.conn = None
