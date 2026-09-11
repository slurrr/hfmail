import sqlite3
from pathlib import Path
from datetime import datetime
from hfmail.config import get_db_path

def get_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                sender TEXT,
                recipient TEXT,
                subject TEXT,
                body_text TEXT,
                body_html TEXT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                category TEXT,            -- 'important', 'promotion', 'spam', 'unsubscribed'
                is_read INTEGER DEFAULT 0, -- 0 = unread, 1 = read
                list_unsubscribe_mailto TEXT,
                list_unsubscribe_url TEXT,
                unsubscribed_at TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT,       -- 'sender', 'subject'
                pattern TEXT,            -- matching pattern (case-insensitive)
                action TEXT              -- 'important', 'spam', 'unsubscribed'
            )
        """)
        
        conn.commit()

def save_email(email_data):
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO emails (
                    message_id, sender, recipient, subject, body_text, body_html, 
                    category, is_read, list_unsubscribe_mailto, list_unsubscribe_url, 
                    received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email_data.get("message_id"),
                email_data.get("sender"),
                email_data.get("recipient"),
                email_data.get("subject"),
                email_data.get("body_text"),
                email_data.get("body_html"),
                email_data.get("category", "important"),
                email_data.get("is_read", 0),
                email_data.get("list_unsubscribe_mailto"),
                email_data.get("list_unsubscribe_url"),
                email_data.get("received_at", datetime.now().isoformat())
            ))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Email already exists, skip or return existing
            cursor.execute("SELECT id FROM emails WHERE message_id = ?", (email_data.get("message_id"),))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

def get_emails(category=None, unread_only=False, search_query=None, limit=50, offset=0):
    init_db()
    query = "SELECT * FROM emails WHERE 1=1"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
    if unread_only:
        query += " AND is_read = 0"
    if search_query:
        query += " AND (subject LIKE ? OR sender LIKE ? OR body_text LIKE ?)"
        like_pattern = f"%{search_query}%"
        params.extend([like_pattern, like_pattern, like_pattern])
        
    query += " ORDER BY received_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def get_email(email_id):
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def mark_as_read(email_id, is_read=1):
    init_db()
    with get_connection() as conn:
        conn.execute("UPDATE emails SET is_read = ? WHERE id = ?", (is_read, email_id))
        conn.commit()

def delete_email(email_id):
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
        conn.commit()

def update_category(email_id, category):
    init_db()
    with get_connection() as conn:
        conn.execute("UPDATE emails SET category = ? WHERE id = ?", (category, email_id))
        conn.commit()

def mark_unsubscribed(email_id):
    init_db()
    now_str = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute("""
            UPDATE emails 
            SET category = 'unsubscribed', unsubscribed_at = ? 
            WHERE id = ?
        """, (now_str, email_id))
        conn.commit()

# Filter management
def add_filter(pattern_type, pattern, action):
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO filters (pattern_type, pattern, action)
            VALUES (?, ?, ?)
        """, (pattern_type, pattern.lower(), action))
        conn.commit()
        return cursor.lastrowid

def get_filters():
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM filters")
        return [dict(row) for row in cursor.fetchall()]

def remove_filter(filter_id):
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM filters WHERE id = ?", (filter_id,))
        conn.commit()
