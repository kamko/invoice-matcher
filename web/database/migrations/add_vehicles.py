"""Migration: add user-managed vehicles and link existing vehicle expenses."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> bool:
    """Create vehicles, add invoice linkage, and backfill known registrations."""
    conn = sqlite3.connect(db_path)
    changed = False
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name VARCHAR(100) NOT NULL,
                registration VARCHAR(16) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                CONSTRAINT uq_vehicle_user_registration UNIQUE (user_id, registration)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_vehicles_user_id ON vehicles (user_id)"
        )

        invoice_columns = {
            column[1]
            for column in conn.execute("PRAGMA table_info(invoices)").fetchall()
        }
        if "vehicle_id" not in invoice_columns:
            conn.execute(
                "ALTER TABLE invoices ADD COLUMN vehicle_id INTEGER REFERENCES vehicles(id)"
            )
            changed = True
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_invoices_vehicle_id ON invoices (vehicle_id)"
        )

        registrations = conn.execute(
            """
            SELECT DISTINCT user_id, vehicle_registration
            FROM invoices
            WHERE user_id IS NOT NULL
              AND vehicle_registration IS NOT NULL
              AND TRIM(vehicle_registration) <> ''
            """
        ).fetchall()
        for user_id, registration in registrations:
            before = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO vehicles (user_id, name, registration, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (user_id, registration, registration),
            )
            if conn.total_changes > before:
                changed = True

        before = conn.total_changes
        conn.execute(
            """
            UPDATE invoices
            SET vehicle_id = (
                SELECT vehicles.id
                FROM vehicles
                WHERE vehicles.user_id = invoices.user_id
                  AND vehicles.registration = invoices.vehicle_registration
            )
            WHERE vehicle_id IS NULL
              AND vehicle_registration IS NOT NULL
            """
        )
        if conn.total_changes > before:
            changed = True

        conn.commit()
        return changed
    finally:
        conn.close()
