import os
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smartdesk.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                category_confidence INTEGER NOT NULL DEFAULT 70,
                priority_confidence INTEGER NOT NULL DEFAULT 70,
                confidence INTEGER NOT NULL DEFAULT 70,
                status TEXT NOT NULL DEFAULT 'Open',
                assigned_to TEXT NOT NULL DEFAULT 'IT Team',
                sla_due_at TEXT,
                attachment_path TEXT,
                admin_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        migrate_tickets(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS update_ticket_timestamp
            AFTER UPDATE ON tickets
            BEGIN
                UPDATE tickets SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END
            """
        )
        seed_admin(conn)


def migrate_tickets(conn):
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()
    }
    migrations = {
        "category_confidence": "ALTER TABLE tickets ADD COLUMN category_confidence INTEGER NOT NULL DEFAULT 70",
        "priority_confidence": "ALTER TABLE tickets ADD COLUMN priority_confidence INTEGER NOT NULL DEFAULT 70",
        "confidence": "ALTER TABLE tickets ADD COLUMN confidence INTEGER NOT NULL DEFAULT 70",
        "assigned_to": "ALTER TABLE tickets ADD COLUMN assigned_to TEXT NOT NULL DEFAULT 'IT Team'",
        "sla_due_at": "ALTER TABLE tickets ADD COLUMN sla_due_at TEXT",
        "attachment_path": "ALTER TABLE tickets ADD COLUMN attachment_path TEXT",
    }
    for column, sql in migrations.items():
        if column not in columns:
            conn.execute(sql)


def seed_admin(conn):
    existing = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if existing:
        return

    admin_name = os.getenv("ADMIN_NAME", "SmartDesk Admin")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@smartdesk.local")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

    conn.execute(
        """
        INSERT INTO users (name, email, password_hash, role)
        VALUES (?, ?, ?, ?)
        """,
        (
            admin_name,
            admin_email,
            generate_password_hash(admin_password),
            "admin",
        ),
    )
