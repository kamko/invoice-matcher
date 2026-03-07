#!/usr/bin/env python3
"""Migration script for Invoice Matcher v2 architecture simplification.

This script:
1. Backs up vendor_aliases, known_transactions, pdf_cache from existing DB
2. Drops old tables (monthly_reconciliation, invoice_payments, reconciliation_sessions)
3. Creates new schema (invoices, transactions)
4. Restores preserved data
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "invoice_matcher.db"
BACKUP_PATH = DATA_DIR / f"invoice_matcher_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"


def backup_database():
    """Create a full backup of the existing database."""
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"Database backed up to: {BACKUP_PATH}")
    else:
        print("No existing database found, creating fresh.")


def get_connection():
    """Get SQLite connection."""
    return sqlite3.connect(DB_PATH)


def migrate():
    """Run the migration."""
    print("=" * 60)
    print("Invoice Matcher v2 Migration")
    print("=" * 60)

    # Step 1: Backup
    print("\n[1/5] Backing up database...")
    backup_database()

    conn = get_connection()
    cursor = conn.cursor()

    # Step 2: Check what tables exist
    print("\n[2/5] Checking existing tables...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [row[0] for row in cursor.fetchall()]
    print(f"  Existing tables: {existing_tables}")

    # Step 3: Backup data from tables we want to preserve
    print("\n[3/5] Preserving data from tables...")

    # Backup vendor_aliases
    vendor_aliases = []
    if 'vendor_aliases' in existing_tables:
        cursor.execute("SELECT * FROM vendor_aliases")
        vendor_aliases = cursor.fetchall()
        cursor.execute("PRAGMA table_info(vendor_aliases)")
        va_cols = [col[1] for col in cursor.fetchall()]
        print(f"  - vendor_aliases: {len(vendor_aliases)} records")

    # Backup known_transactions
    known_transactions = []
    if 'known_transactions' in existing_tables:
        cursor.execute("SELECT * FROM known_transactions")
        known_transactions = cursor.fetchall()
        cursor.execute("PRAGMA table_info(known_transactions)")
        kt_cols = [col[1] for col in cursor.fetchall()]
        print(f"  - known_transactions: {len(known_transactions)} records")

    # Backup pdf_cache
    pdf_cache = []
    if 'pdf_cache' in existing_tables:
        cursor.execute("SELECT * FROM pdf_cache")
        pdf_cache = cursor.fetchall()
        cursor.execute("PRAGMA table_info(pdf_cache)")
        pc_cols = [col[1] for col in cursor.fetchall()]
        print(f"  - pdf_cache: {len(pdf_cache)} records")

    # Backup app_settings
    app_settings = []
    if 'app_settings' in existing_tables:
        cursor.execute("SELECT * FROM app_settings")
        app_settings = cursor.fetchall()
        print(f"  - app_settings: {len(app_settings)} records")

    # Step 4: Drop old tables and create new schema
    print("\n[4/5] Dropping old tables and creating new schema...")

    # Tables to drop (old architecture)
    tables_to_drop = [
        'monthly_reconciliations',
        'invoice_payments',
        'reconciliation_sessions',
        'known_transaction_matches',
    ]

    for table in tables_to_drop:
        if table in existing_tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"  - Dropped: {table}")

    # Also drop existing vendor_aliases, known_transactions, pdf_cache to recreate with new schema
    for table in ['vendor_aliases', 'known_transactions', 'pdf_cache', 'app_settings']:
        if table in existing_tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"  - Dropped for recreation: {table}")

    # Create new schema
    print("  - Creating new tables...")

    # app_settings
    cursor.execute("""
        CREATE TABLE app_settings (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT,
            updated_at DATETIME
        )
    """)

    # invoices (new)
    cursor.execute("""
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gdrive_file_id VARCHAR(255),
            receipt_index INTEGER DEFAULT 0,
            filename VARCHAR(255) NOT NULL,
            vendor VARCHAR(255),
            amount DECIMAL(12,2),
            invoice_date DATE,
            payment_type VARCHAR(20),
            vs VARCHAR(50),
            iban VARCHAR(50),
            is_credit_note BOOLEAN DEFAULT 0,
            status VARCHAR(20) DEFAULT 'unmatched',
            transaction_id VARCHAR(100),
            created_at DATETIME,
            UNIQUE(gdrive_file_id, receipt_index),
            UNIQUE(transaction_id)
        )
    """)
    cursor.execute("CREATE INDEX ix_invoices_gdrive ON invoices(gdrive_file_id)")
    cursor.execute("CREATE INDEX ix_invoices_transaction ON invoices(transaction_id)")
    print("  - Created: invoices")

    # transactions (new)
    cursor.execute("""
        CREATE TABLE transactions (
            id VARCHAR(100) PRIMARY KEY,
            date DATE NOT NULL,
            amount DECIMAL(12,2) NOT NULL,
            currency VARCHAR(3) DEFAULT 'CZK',
            counter_account VARCHAR(100),
            counter_name VARCHAR(255),
            vs VARCHAR(50),
            note TEXT,
            type VARCHAR(20),
            raw_type VARCHAR(100),
            status VARCHAR(20) DEFAULT 'unmatched',
            known_rule_id INTEGER,
            skip_reason VARCHAR(255),
            fetched_at DATETIME,
            FOREIGN KEY(known_rule_id) REFERENCES known_transactions(id)
        )
    """)
    cursor.execute("CREATE INDEX ix_transactions_date ON transactions(date)")
    print("  - Created: transactions")

    # known_transactions
    cursor.execute("""
        CREATE TABLE known_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type VARCHAR(20) NOT NULL,
            vendor_pattern VARCHAR(255),
            note_pattern VARCHAR(255),
            amount DECIMAL(12,2),
            amount_min DECIMAL(12,2),
            amount_max DECIMAL(12,2),
            vs_pattern VARCHAR(50),
            counter_account VARCHAR(100),
            reason VARCHAR(500) NOT NULL,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME
        )
    """)
    print("  - Created: known_transactions")

    # vendor_aliases
    cursor.execute("""
        CREATE TABLE vendor_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_vendor VARCHAR(255) NOT NULL,
            invoice_vendor VARCHAR(255) NOT NULL,
            source VARCHAR(50) NOT NULL,
            confidence_count INTEGER DEFAULT 1 NOT NULL,
            created_at DATETIME NOT NULL,
            last_confirmed_at DATETIME NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX ix_vendor_aliases_trans ON vendor_aliases(transaction_vendor)")
    cursor.execute("CREATE INDEX ix_vendor_aliases_inv ON vendor_aliases(invoice_vendor)")
    print("  - Created: vendor_aliases")

    # pdf_cache
    cursor.execute("""
        CREATE TABLE pdf_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gdrive_file_id VARCHAR(255) UNIQUE NOT NULL,
            filename VARCHAR(255) NOT NULL,
            content BLOB NOT NULL,
            file_size INTEGER NOT NULL,
            md5_checksum VARCHAR(32),
            cached_at DATETIME NOT NULL,
            last_accessed_at DATETIME NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX ix_pdf_cache_gdrive ON pdf_cache(gdrive_file_id)")
    print("  - Created: pdf_cache")

    # Step 5: Restore preserved data
    print("\n[5/5] Restoring preserved data...")

    # Restore app_settings
    for row in app_settings:
        cursor.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            row
        )
    print(f"  - Restored app_settings: {len(app_settings)} records")

    # Restore known_transactions (map old columns to new)
    # New schema columns: id, rule_type, vendor_pattern, note_pattern, amount, amount_min, amount_max, vs_pattern, counter_account, reason, is_active, created_at, updated_at
    new_kt_cols = ['id', 'rule_type', 'vendor_pattern', 'note_pattern', 'amount', 'amount_min', 'amount_max', 'vs_pattern', 'counter_account', 'reason', 'is_active', 'created_at', 'updated_at']
    for row in known_transactions:
        # Create dict from old data
        old_data = dict(zip(kt_cols, row))
        # Map to new columns, using defaults for missing
        new_data = {
            'id': old_data.get('id'),
            'rule_type': old_data.get('rule_type', 'vendor'),
            'vendor_pattern': old_data.get('vendor_pattern'),
            'note_pattern': old_data.get('note_pattern'),
            'amount': old_data.get('amount'),
            'amount_min': old_data.get('amount_min'),
            'amount_max': old_data.get('amount_max'),
            'vs_pattern': old_data.get('vs_pattern'),
            'counter_account': old_data.get('counter_account'),
            'reason': old_data.get('reason', 'Migrated rule'),
            'is_active': old_data.get('is_active', True),
            'created_at': old_data.get('created_at', datetime.now().isoformat()),
            'updated_at': old_data.get('updated_at'),
        }
        cols = ', '.join(new_kt_cols)
        placeholders = ', '.join(['?' for _ in new_kt_cols])
        values = [new_data[c] for c in new_kt_cols]
        cursor.execute(f"INSERT INTO known_transactions ({cols}) VALUES ({placeholders})", values)
    print(f"  - Restored known_transactions: {len(known_transactions)} records")

    # Restore vendor_aliases (map old columns to new)
    # New schema columns: id, transaction_vendor, invoice_vendor, source, confidence_count, created_at, last_confirmed_at
    new_va_cols = ['id', 'transaction_vendor', 'invoice_vendor', 'source', 'confidence_count', 'created_at', 'last_confirmed_at']
    for row in vendor_aliases:
        old_data = dict(zip(va_cols, row))
        new_data = {
            'id': old_data.get('id'),
            'transaction_vendor': old_data.get('transaction_vendor', ''),
            'invoice_vendor': old_data.get('invoice_vendor', ''),
            'source': old_data.get('source', 'migrated'),
            'confidence_count': old_data.get('confidence_count', 1),
            'created_at': old_data.get('created_at', datetime.now().isoformat()),
            'last_confirmed_at': old_data.get('last_confirmed_at', datetime.now().isoformat()),
        }
        cols = ', '.join(new_va_cols)
        placeholders = ', '.join(['?' for _ in new_va_cols])
        values = [new_data[c] for c in new_va_cols]
        cursor.execute(f"INSERT INTO vendor_aliases ({cols}) VALUES ({placeholders})", values)
    print(f"  - Restored vendor_aliases: {len(vendor_aliases)} records")

    # Restore pdf_cache
    for row in pdf_cache:
        placeholders = ', '.join(['?' for _ in row])
        cols = ', '.join(pc_cols)
        cursor.execute(f"INSERT INTO pdf_cache ({cols}) VALUES ({placeholders})", row)
    print(f"  - Restored pdf_cache: {len(pdf_cache)} records")

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print(f"Backup saved to: {BACKUP_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
