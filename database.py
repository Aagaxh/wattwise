import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wattwise.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Appliances Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appliances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            power_watts REAL NOT NULL,
            usage_hours REAL NOT NULL,
            days INTEGER DEFAULT 30,
            room TEXT,
            start_time TEXT,
            end_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    # Energy Records Table (Hourly & Daily records)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS energy_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            appliance_name TEXT NOT NULL,
            date TEXT NOT NULL,
            hour INTEGER NOT NULL,
            power_watts REAL NOT NULL,
            usage_hours REAL NOT NULL,
            energy_kwh REAL NOT NULL,
            room TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    # Settings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            tariff_rate REAL DEFAULT 8.0,
            currency TEXT DEFAULT '₹',
            fixed_charges REAL DEFAULT 100.0,
            additional_charges REAL DEFAULT 0.0,
            tax_rate REAL DEFAULT 5.0,
            theme TEXT DEFAULT 'dark',
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    # Goals Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            monthly_target_kwh REAL DEFAULT 200.0,
            reduction_pct REAL DEFAULT 15.0,
            budget_target REAL DEFAULT 1800.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully at:", DB_PATH)
