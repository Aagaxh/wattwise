import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db_connection
import werkzeug.security

def get_user_by_email(email):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT id, name, email, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(name, email, password):
    conn = get_db_connection()
    password_hash = werkzeug.security.generate_password_hash(password)
    try:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
            (name, email, password_hash)
        )
        user_id = cursor.lastrowid
        # Seed default settings and goals for new user
        cursor.execute(
            'INSERT INTO settings (user_id, tariff_rate, currency, fixed_charges, additional_charges, tax_rate, theme) VALUES (?, 8.0, "₹", 100.0, 50.0, 5.0, "dark")',
            (user_id,)
        )
        cursor.execute(
            'INSERT INTO goals (user_id, monthly_target_kwh, reduction_pct, budget_target) VALUES (?, 200.0, 15.0, 1700.0)',
            (user_id,)
        )
        conn.commit()
        return user_id
    finally:
        conn.close()

def get_appliances(user_id):
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM appliances WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_appliance(appliance_id, user_id):
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM appliances WHERE id = ? AND user_id = ?', (appliance_id, user_id)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_appliance(user_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO appliances (user_id, name, category, power_watts, usage_hours, days, room, start_time, end_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        data.get('name'),
        data.get('category', 'Other'),
        float(data.get('power_watts', 100)),
        float(data.get('usage_hours', 1)),
        int(data.get('days', 30)),
        data.get('room', 'General'),
        data.get('start_time', ''),
        data.get('end_time', '')
    ))
    new_id = cursor.lastrowid

    # If this appliance has no records in energy_records, generate corresponding records for the last 30 days
    # so that new appliances immediately contribute to charts and calculations!
    power = float(data.get('power_watts', 100))
    hours = float(data.get('usage_hours', 1))
    daily_kwh = (power * hours) / 1000.0
    app_name = data.get('name')
    room = data.get('room', 'General')

    # Get distinct dates from current energy_records
    date_rows = conn.execute('SELECT DISTINCT date FROM energy_records WHERE user_id = ? ORDER BY date', (user_id,)).fetchall()
    if date_rows:
        records = []
        hour_val = 19 # default active hour
        if data.get('start_time'):
            try:
                hour_val = int(data.get('start_time').split(':')[0])
            except Exception:
                hour_val = 19
        for dr in date_rows:
            records.append((user_id, app_name, dr['date'], hour_val, power, hours, daily_kwh, room))
        cursor.executemany('''
            INSERT INTO energy_records (user_id, appliance_name, date, hour, power_watts, usage_hours, energy_kwh, room)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', records)

    conn.commit()
    conn.close()
    return new_id

def update_appliance(appliance_id, user_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Get old name in case name was modified
    old = cursor.execute('SELECT name FROM appliances WHERE id = ? AND user_id = ?', (appliance_id, user_id)).fetchone()
    old_name = old['name'] if old else None

    cursor.execute('''
        UPDATE appliances
        SET name = ?, category = ?, power_watts = ?, usage_hours = ?, days = ?, room = ?, start_time = ?, end_time = ?
        WHERE id = ? AND user_id = ?
    ''', (
        data.get('name'),
        data.get('category', 'Other'),
        float(data.get('power_watts', 100)),
        float(data.get('usage_hours', 1)),
        int(data.get('days', 30)),
        data.get('room', 'General'),
        data.get('start_time', ''),
        data.get('end_time', ''),
        appliance_id,
        user_id
    ))

    # Update associated energy records if power/name changed
    if old_name:
        new_name = data.get('name')
        new_power = float(data.get('power_watts', 100))
        new_hours = float(data.get('usage_hours', 1))
        new_kwh = (new_power * new_hours) / 1000.0
        cursor.execute('''
            UPDATE energy_records
            SET appliance_name = ?, power_watts = ?, usage_hours = ?, energy_kwh = ?, room = ?
            WHERE user_id = ? AND appliance_name = ?
        ''', (new_name, new_power, new_hours, new_kwh, data.get('room', 'General'), user_id, old_name))

    conn.commit()
    conn.close()
    return True

def delete_appliance(appliance_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    old = cursor.execute('SELECT name FROM appliances WHERE id = ? AND user_id = ?', (appliance_id, user_id)).fetchone()
    if old:
        app_name = old['name']
        cursor.execute('DELETE FROM appliances WHERE id = ? AND user_id = ?', (appliance_id, user_id))
        cursor.execute('DELETE FROM energy_records WHERE user_id = ? AND appliance_name = ?', (user_id, app_name))
        conn.commit()
    conn.close()
    return True

def get_settings(user_id):
    conn = get_db_connection()
    settings = conn.execute('SELECT * FROM settings WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    if settings:
        return dict(settings)
    return {"tariff_rate": 8.0, "currency": "₹", "fixed_charges": 100.0, "additional_charges": 0.0, "tax_rate": 5.0, "theme": "dark"}

def update_settings(user_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO settings (user_id, tariff_rate, currency, fixed_charges, additional_charges, tax_rate, theme)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            tariff_rate = excluded.tariff_rate,
            currency = excluded.currency,
            fixed_charges = excluded.fixed_charges,
            additional_charges = excluded.additional_charges,
            tax_rate = excluded.tax_rate,
            theme = excluded.theme
    ''', (
        user_id,
        float(data.get('tariff_rate', 8.0)),
        data.get('currency', '₹'),
        float(data.get('fixed_charges', 100.0)),
        float(data.get('additional_charges', 0.0)),
        float(data.get('tax_rate', 5.0)),
        data.get('theme', 'dark')
    ))
    conn.commit()
    conn.close()
    return True

def get_goal(user_id):
    conn = get_db_connection()
    goal = conn.execute('SELECT * FROM goals WHERE user_id = ? ORDER BY id DESC LIMIT 1', (user_id,)).fetchone()
    conn.close()
    if goal:
        return dict(goal)
    return {"monthly_target_kwh": 200.0, "reduction_pct": 15.0, "budget_target": 1800.0}

def update_goal(user_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO goals (user_id, monthly_target_kwh, reduction_pct, budget_target)
        VALUES (?, ?, ?, ?)
    ''', (
        user_id,
        float(data.get('monthly_target_kwh', 200.0)),
        float(data.get('reduction_pct', 15.0)),
        float(data.get('budget_target', 1800.0))
    ))
    conn.commit()
    conn.close()
    return True
