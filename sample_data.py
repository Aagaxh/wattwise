import os
import sys
import csv
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import werkzeug.security
from database import get_db_connection, init_db

def seed_sample_data():
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Ensure Demo User Exists
    demo_email = 'demo@wattwise.com'
    cursor.execute('SELECT id FROM users WHERE email = ?', (demo_email,))
    user_row = cursor.fetchone()

    password_hash = werkzeug.security.generate_password_hash('demo123')
    if not user_row:
        cursor.execute('''
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
        ''', ('Demo User', demo_email, password_hash))
        user_id = cursor.lastrowid
    else:
        user_id = user_row['id']
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))

    # Clear existing data for user to reset cleanly
    cursor.execute('DELETE FROM appliances WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM energy_records WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM settings WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM goals WHERE user_id = ?', (user_id,))

    # 2. Insert Settings
    cursor.execute('''
        INSERT INTO settings (user_id, tariff_rate, currency, fixed_charges, additional_charges, tax_rate, theme)
        VALUES (?, 8.0, '₹', 100.0, 50.0, 5.0, 'dark')
    ''', (user_id,))

    # 3. Insert Goals
    cursor.execute('''
        INSERT INTO goals (user_id, monthly_target_kwh, reduction_pct, budget_target)
        VALUES (?, 190.0, 15.0, 1600.0)
    ''', (user_id,))

    # 4. Household Appliances Catalog
    appliances_data = [
        {"name": "Air Conditioner", "category": "Cooling", "power_watts": 1500, "usage_hours": 5.0, "days": 30, "room": "Master Bedroom", "start_time": "20:00", "end_time": "01:00"},
        {"name": "Refrigerator", "category": "Kitchen", "power_watts": 200, "usage_hours": 24.0, "days": 30, "room": "Kitchen", "start_time": "00:00", "end_time": "23:59"},
        {"name": "Water Heater", "category": "Heating", "power_watts": 2000, "usage_hours": 1.5, "days": 30, "room": "Bathroom", "start_time": "06:30", "end_time": "08:00"},
        {"name": "Washing Machine", "category": "Laundry", "power_watts": 500, "usage_hours": 1.2, "days": 30, "room": "Utility Room", "start_time": "09:00", "end_time": "10:15"},
        {"name": "Television", "category": "Entertainment", "power_watts": 120, "usage_hours": 4.5, "days": 30, "room": "Living Room", "start_time": "19:00", "end_time": "23:30"},
        {"name": "Ceiling Fan", "category": "Cooling", "power_watts": 75, "usage_hours": 14.0, "days": 30, "room": "Living & Bed", "start_time": "11:00", "end_time": "01:00"},
        {"name": "LED Lights", "category": "Lighting", "power_watts": 40, "usage_hours": 6.0, "days": 30, "room": "All Rooms", "start_time": "18:00", "end_time": "00:00"},
        {"name": "Laptop", "category": "Entertainment", "power_watts": 65, "usage_hours": 8.0, "days": 30, "room": "Home Office", "start_time": "10:00", "end_time": "18:00"},
        {"name": "Microwave", "category": "Kitchen", "power_watts": 1200, "usage_hours": 0.4, "days": 30, "room": "Kitchen", "start_time": "20:00", "end_time": "20:25"},
    ]

    for app in appliances_data:
        cursor.execute('''
            INSERT INTO appliances (user_id, name, category, power_watts, usage_hours, days, room, start_time, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, app["name"], app["category"], app["power_watts"], app["usage_hours"], app["days"], app["room"], app["start_time"], app["end_time"]))

    # 5. Generate 30 Days of Realistic Hourly Energy Records
    # Using anchor date: 2026-09-18
    end_date = datetime(2026, 9, 18)
    start_date = end_date - timedelta(days=29)

    records = []
    csv_rows = []

    # Daily baseline templates:
    # Hour -> active appliances with typical fraction of hour run
    for d in range(30):
        current_day = start_date + timedelta(days=d)
        date_str = current_day.strftime('%Y-%m-%d')
        is_weekend = current_day.weekday() >= 5
        day_index = d

        # Inject realistic anomalies:
        # Anomaly 1: Day 26 (3 days ago) - Refrigerator door seal failure / continuous run (+28% surge)
        fridge_anomaly = (day_index == 26)
        # Anomaly 2: Day 19 (10 days ago) - Heatwave AC over-usage (afternoon continuous run 13:00 - 18:00)
        ac_anomaly = (day_index == 19)
        # Anomaly 3: Day 12 (17 days ago) - Water heater left on for 4 hours
        heater_anomaly = (day_index == 12)

        for hour in range(24):
            # 1. Refrigerator runs every hour with compressor duty cycle ~ 40-50%
            fridge_cycle = 0.85 if fridge_anomaly else (0.45 + random.uniform(-0.05, 0.05))
            fridge_kwh = (200 * fridge_cycle) / 1000.0
            records.append((user_id, "Refrigerator", date_str, hour, 200, round(fridge_cycle, 2), round(fridge_kwh, 4), "Kitchen"))

            # 2. Air Conditioner: typically 20:00 to 01:00 (hours 20, 21, 22, 23, 0)
            ac_hours = [20, 21, 22, 23, 0]
            if ac_anomaly:
                ac_hours.extend([13, 14, 15, 16, 17, 18, 19])
            if hour in ac_hours:
                ac_cycle = 0.85 if is_weekend else 0.75
                ac_cycle += random.uniform(-0.05, 0.05)
                ac_kwh = (1500 * ac_cycle) / 1000.0
                records.append((user_id, "Air Conditioner", date_str, hour, 1500, round(ac_cycle, 2), round(ac_kwh, 4), "Master Bedroom"))

            # 3. Water Heater: morning 06:00 to 08:00 (hours 6, 7)
            heater_hours = [6, 7]
            if heater_anomaly:
                heater_hours.extend([8, 9, 10])
            if hour in heater_hours:
                h_cycle = 0.75 if hour == 6 or hour == 7 else 0.90
                h_kwh = (2000 * h_cycle) / 1000.0
                records.append((user_id, "Water Heater", date_str, hour, 2000, round(h_cycle, 2), round(h_kwh, 4), "Bathroom"))

            # 4. Television: evening 19:00 to 23:00 (hours 19, 20, 21, 22)
            if hour in [19, 20, 21, 22] or (is_weekend and hour in [14, 15, 16]):
                tv_cycle = 0.9 + random.uniform(-0.1, 0.1)
                tv_kwh = (120 * tv_cycle) / 1000.0
                records.append((user_id, "Television", date_str, hour, 120, round(tv_cycle, 2), round(tv_kwh, 4), "Living Room"))

            # 5. Washing Machine: 09:00 to 11:00 (hours 9, 10) mostly every 2nd day or weekend
            if (is_weekend or day_index % 2 == 0) and hour in [9, 10]:
                wm_cycle = 0.6
                wm_kwh = (500 * wm_cycle) / 1000.0
                records.append((user_id, "Washing Machine", date_str, hour, 500, round(wm_cycle, 2), round(wm_kwh, 4), "Utility Room"))

            # 6. Ceiling Fan: running hours 11:00 to 01:00
            if (hour >= 11 or hour <= 1):
                fan_cycle = 0.95
                fan_kwh = (75 * fan_cycle) / 1000.0
                records.append((user_id, "Ceiling Fan", date_str, hour, 75, round(fan_cycle, 2), round(fan_kwh, 4), "Living & Bed"))

            # 7. LED Lights: evening 18:00 to 23:00 (hours 18, 19, 20, 21, 22, 23)
            if 18 <= hour <= 23:
                light_cycle = 1.0
                light_kwh = (40 * light_cycle) / 1000.0
                records.append((user_id, "LED Lights", date_str, hour, 40, round(light_cycle, 2), round(light_kwh, 4), "All Rooms"))

            # 8. Laptop: 10:00 to 18:00 on weekdays, sporadic on weekends
            if (not is_weekend and 10 <= hour <= 17) or (is_weekend and hour in [11, 12, 16]):
                lap_cycle = 0.8
                lap_kwh = (65 * lap_cycle) / 1000.0
                records.append((user_id, "Laptop", date_str, hour, 65, round(lap_cycle, 2), round(lap_kwh, 4), "Home Office"))

            # 9. Microwave: lunch (12:00) and dinner (20:00)
            if hour in [12, 20]:
                mw_cycle = 0.25
                mw_kwh = (1200 * mw_cycle) / 1000.0
                records.append((user_id, "Microwave", date_str, hour, 1200, round(mw_cycle, 2), round(mw_kwh, 4), "Kitchen"))

    cursor.executemany('''
        INSERT INTO energy_records (user_id, appliance_name, date, hour, power_watts, usage_hours, energy_kwh, room)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', records)

    conn.commit()

    # Also generate sample_energy_data.csv for user CSV upload demo
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_energy_data.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'appliance', 'usage_hours', 'power_watts', 'hour', 'room'])
        for r in records:
            # r = (user_id, appliance_name, date_str, hour, power_watts, usage_hours, energy_kwh, room)
            writer.writerow([r[2], r[1], r[5], r[4], r[3], r[7]])

    conn.close()
    print(f"Seeded {len(records)} energy records successfully for user_id {user_id}.")
    print(f"Sample CSV generated at {csv_path}")

if __name__ == '__main__':
    seed_sample_data()
