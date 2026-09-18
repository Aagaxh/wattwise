import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
import pandas as pd
import io
import csv
import werkzeug.security

from database import init_db, get_db_connection
from models import (
    get_user_by_email, get_user_by_id, create_user,
    get_appliances, get_appliance, add_appliance, update_appliance, delete_appliance,
    get_settings, update_settings, get_goal, update_goal
)
from analytics import (
    get_dashboard_summary, get_appliance_analysis, get_energy_analytics,
    get_peak_usage_analysis, detect_anomalies, calculate_bill,
    get_intelligent_recommendations, handle_advisor_query, generate_report_data
)
from sample_data import seed_sample_data

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Auto-initialize DB and check if demo data exists on start
with app.app_context():
    init_db()
    conn = get_db_connection()
    user = conn.execute('SELECT id FROM users WHERE email = "demo@wattwise.com"').fetchone()
    records = conn.execute('SELECT COUNT(*) as count FROM energy_records').fetchone()
    conn.close()
    if not user or not records or records['count'] == 0:
        print("Initializing and seeding demo dataset...")
        seed_sample_data()

def get_current_user_id():
    """Helper to extract user_id from Authorization header or default to Demo User (id=1)."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            # Simple demo token format: "demo-user-<id>" or int
            if token.startswith('demo-user-'):
                return int(token.replace('demo-user-', ''))
            return int(token)
        except Exception:
            return 1
    return 1

# ================= AUTH ROUTES ================= #

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    # Guest Demo Bypass
    if data.get('is_guest', False) or email == 'demo@wattwise.com' and (password == 'demo123' or not password):
        user = get_user_by_email('demo@wattwise.com')
        if not user:
            seed_sample_data()
            user = get_user_by_email('demo@wattwise.com')
        return jsonify({
            "status": "success",
            "token": f"demo-user-{user['id']}",
            "user": {"id": user['id'], "name": user['name'], "email": user['email']}
        })

    user = get_user_by_email(email)
    if not user or not werkzeug.security.check_password_hash(user['password_hash'], password):
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401

    return jsonify({
        "status": "success",
        "token": f"demo-user-{user['id']}",
        "user": {"id": user['id'], "name": user['name'], "email": user['email']}
    })

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not name or not email or not password:
        return jsonify({"status": "error", "message": "Name, email, and password are required"}), 400

    if get_user_by_email(email):
        return jsonify({"status": "error", "message": "An account with this email already exists"}), 409

    user_id = create_user(name, email, password)
    return jsonify({
        "status": "success",
        "token": f"demo-user-{user_id}",
        "user": {"id": user_id, "name": name, "email": email}
    }), 201

@app.route('/api/auth/me', methods=['GET'])
def get_me():
    user_id = get_current_user_id()
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
    return jsonify({"status": "success", "user": user})

# ================= APPLIANCES CRUD ================= #

@app.route('/api/appliances', methods=['GET'])
def list_appliances():
    user_id = get_current_user_id()
    settings = get_settings(user_id)
    tariff = settings.get('tariff_rate', 8.0)
    curr = settings.get('currency', '₹')

    appliances = get_appliances(user_id)
    # Calculate daily/monthly kWh and estimated cost for each appliance
    result = []
    for app_item in appliances:
        p = float(app_item['power_watts'])
        h = float(app_item['usage_hours'])
        days = int(app_item.get('days', 30))
        daily_kwh = round((p * h) / 1000.0, 3)
        monthly_kwh = round((p * h * days) / 1000.0, 2)
        est_cost = round(monthly_kwh * tariff, 2)

        item_dict = dict(app_item)
        item_dict['daily_kwh'] = daily_kwh
        item_dict['monthly_kwh'] = monthly_kwh
        item_dict['estimated_cost'] = est_cost
        item_dict['currency'] = curr
        result.append(item_dict)

    return jsonify({"status": "success", "appliances": result})

@app.route('/api/appliances', methods=['POST'])
def create_appliance():
    user_id = get_current_user_id()
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({"status": "error", "message": "Appliance name is required"}), 400

    new_id = add_appliance(user_id, data)
    return jsonify({"status": "success", "message": "Appliance added successfully", "id": new_id}), 201

@app.route('/api/appliances/<int:appliance_id>', methods=['PUT'])
def edit_appliance(appliance_id):
    user_id = get_current_user_id()
    data = request.get_json() or {}
    update_appliance(appliance_id, user_id, data)
    return jsonify({"status": "success", "message": "Appliance updated successfully"})

@app.route('/api/appliances/<int:appliance_id>', methods=['DELETE'])
def remove_appliance(appliance_id):
    user_id = get_current_user_id()
    delete_appliance(appliance_id, user_id)
    return jsonify({"status": "success", "message": "Appliance deleted successfully"})

# ================= DASHBOARD & ANALYTICS ================= #

@app.route('/api/dashboard', methods=['GET'])
def dashboard_overview():
    user_id = get_current_user_id()
    summary = get_dashboard_summary(user_id)
    return jsonify({"status": "success", "data": summary})

@app.route('/api/appliance-analysis', methods=['GET'])
def appliance_analysis():
    user_id = get_current_user_id()
    data = get_appliance_analysis(user_id)
    return jsonify({"status": "success", "data": data})

@app.route('/api/analytics', methods=['GET'])
def energy_analytics():
    user_id = get_current_user_id()
    filter_type = request.args.get('filter', 'last30')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    data = get_energy_analytics(user_id, filter_type=filter_type, start_date=start_date, end_date=end_date)
    return jsonify({"status": "success", "data": data})

@app.route('/api/peak-usage', methods=['GET'])
def peak_usage():
    user_id = get_current_user_id()
    data = get_peak_usage_analysis(user_id)
    return jsonify({"status": "success", "data": data})

@app.route('/api/anomalies', methods=['GET'])
def anomalies():
    user_id = get_current_user_id()
    alerts = detect_anomalies(user_id)
    return jsonify({"status": "success", "data": alerts})

@app.route('/api/recommendations', methods=['GET'])
def recommendations():
    user_id = get_current_user_id()
    recs = get_intelligent_recommendations(user_id)
    return jsonify({"status": "success", "data": recs})

@app.route('/api/advisor/chat', methods=['POST'])
def advisor_chat():
    user_id = get_current_user_id()
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({"status": "error", "message": "Query cannot be empty"}), 400

    response_text = handle_advisor_query(user_id, query)
    return jsonify({"status": "success", "answer": response_text})

# ================= BILL ESTIMATOR ================= #

@app.route('/api/bill/calculate', methods=['POST'])
def calculate_bill_endpoint():
    user_id = get_current_user_id()
    data = request.get_json() or {}
    kwh = data.get('consumption_kwh')
    tariff = data.get('tariff_rate')
    fixed = data.get('fixed_charges')
    tax = data.get('tax_rate')

    result = calculate_bill(
        user_id,
        consumption_kwh=float(kwh) if kwh is not None else None,
        custom_tariff=float(tariff) if tariff is not None else None,
        custom_fixed=float(fixed) if fixed is not None else None,
        custom_tax=float(tax) if tax is not None else None
    )
    return jsonify({"status": "success", "data": result})

# ================= DATASET UPLOAD ================= #

@app.route('/api/upload', methods=['POST'])
def upload_dataset():
    user_id = get_current_user_id()

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No file selected"}), 400

    if not file.filename.endswith('.csv'):
        return jsonify({"status": "error", "message": "Only CSV files are supported"}), 400

    try:
        df_uploaded = pd.read_csv(file)
        required_cols = {'date', 'appliance', 'usage_hours', 'power_watts', 'hour'}
        col_map = {c.lower().strip(): c for c in df_uploaded.columns}

        # Check required columns
        missing = [c for c in required_cols if c not in col_map]
        if missing:
            return jsonify({
                "status": "error",
                "message": f"CSV missing required columns: {', '.join(missing)}. Required: date, appliance, usage_hours, power_watts, hour"
            }), 400

        # Normalize column names
        df_norm = pd.DataFrame()
        df_norm['date'] = pd.to_datetime(df_uploaded[col_map['date']]).dt.strftime('%Y-%m-%d')
        df_norm['appliance_name'] = df_uploaded[col_map['appliance']].astype(str).str.strip()
        df_norm['usage_hours'] = pd.to_numeric(df_uploaded[col_map['usage_hours']], errors='coerce').fillna(1.0)
        df_norm['power_watts'] = pd.to_numeric(df_uploaded[col_map['power_watts']], errors='coerce').fillna(100.0)
        df_norm['hour'] = pd.to_numeric(df_uploaded[col_map['hour']], errors='coerce').fillna(12).astype(int)
        df_norm['room'] = df_uploaded[col_map['room']].astype(str) if 'room' in col_map else 'Household'
        df_norm['energy_kwh'] = (df_norm['power_watts'] * df_norm['usage_hours']) / 1000.0

        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete existing energy_records and appliances for clean replacement or append
        replace_mode = request.form.get('replace', 'true').lower() == 'true'
        if replace_mode:
            cursor.execute('DELETE FROM energy_records WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM appliances WHERE user_id = ?', (user_id,))

        # Insert records into DB
        records_to_insert = [
            (user_id, row['appliance_name'], row['date'], int(row['hour']), float(row['power_watts']),
             float(row['usage_hours']), round(float(row['energy_kwh']), 4), row['room'])
            for _, row in df_norm.iterrows()
        ]

        cursor.executemany('''
            INSERT INTO energy_records (user_id, appliance_name, date, hour, power_watts, usage_hours, energy_kwh, room)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', records_to_insert)

        # Also auto-populate appliances table based on uploaded dataset
        app_summary = df_norm.groupby('appliance_name').agg({
            'power_watts': 'mean',
            'usage_hours': 'mean',
            'room': 'first'
        }).reset_index()

        for _, app_row in app_summary.iterrows():
            cursor.execute('''
                INSERT INTO appliances (user_id, name, category, power_watts, usage_hours, days, room)
                VALUES (?, ?, 'Uploaded', ?, ?, 30, ?)
            ''', (user_id, app_row['appliance_name'], round(float(app_row['power_watts']), 1),
                  round(float(app_row['usage_hours']), 1), app_row['room']))

        conn.commit()
        conn.close()

        total_rows = len(records_to_insert)
        total_kwh = round(float(df_norm['energy_kwh'].sum()), 2)

        return jsonify({
            "status": "success",
            "message": f"Successfully analyzed and imported {total_rows} records ({total_kwh} kWh).",
            "imported_rows": total_rows,
            "total_kwh": total_kwh,
            "unique_appliances": int(df_norm['appliance_name'].nunique()),
            "date_range": f"{df_norm['date'].min()} to {df_norm['date'].max()}"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to parse CSV: {str(e)}"}), 400

# ================= REPORTS & EXPORT ================= #

@app.route('/api/reports/summary', methods=['GET'])
def report_summary():
    user_id = get_current_user_id()
    data = generate_report_data(user_id)
    return jsonify({"status": "success", "data": data})

@app.route('/api/reports/export-csv', methods=['GET'])
def export_csv():
    user_id = get_current_user_id()
    conn = get_db_connection()
    df = pd.read_sql_query('''
        SELECT date, appliance_name as appliance, hour, power_watts, usage_hours, energy_kwh, room
        FROM energy_records
        WHERE user_id = ?
        ORDER BY date ASC, hour ASC
    ''', conn, params=(user_id,))
    conn.close()

    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=wattwise_energy_export.csv"
    response.headers["Content-type"] = "text/csv"
    return response

@app.route('/api/system/sample-csv', methods=['GET'])
def download_sample_csv():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_energy_data.csv')
    if not os.path.exists(csv_path):
        seed_sample_data()
    return send_file(csv_path, as_attachment=True, download_name='sample_energy_data.csv', mimetype='text/csv')

# ================= GOALS & SETTINGS ================= #

@app.route('/api/goals', methods=['GET', 'POST'])
def handle_goals():
    user_id = get_current_user_id()
    if request.method == 'POST':
        data = request.get_json() or {}
        update_goal(user_id, data)
        return jsonify({"status": "success", "message": "Goals updated successfully"})

    # GET
    goal = get_goal(user_id)
    dashboard = get_dashboard_summary(user_id)
    current_kwh = dashboard.get('total_energy_kwh', 0.0)
    target_kwh = goal.get('monthly_target_kwh', 200.0)
    red_pct = goal.get('reduction_pct', 15.0)
    budget_target = goal.get('budget_target', 1800.0)

    # Progress calculation
    progress_pct = round((current_kwh / target_kwh * 100), 1) if target_kwh > 0 else 0.0
    status = "On Track" if current_kwh <= target_kwh else "Over Budget"

    settings = get_settings(user_id)
    tariff = settings.get('tariff_rate', 8.0)
    curr = settings.get('currency', '₹')

    return jsonify({
        "status": "success",
        "data": {
            "monthly_target_kwh": target_kwh,
            "reduction_pct": red_pct,
            "budget_target": budget_target,
            "current_consumption_kwh": current_kwh,
            "progress_pct": progress_pct,
            "status": status,
            "currency": curr,
            "estimated_current_bill": dashboard.get('raw_estimated_bill', 0.0),
            "target_bill_limit": budget_target
        }
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    user_id = get_current_user_id()
    if request.method == 'POST':
        data = request.get_json() or {}
        update_settings(user_id, data)
        return jsonify({"status": "success", "message": "Settings updated successfully"})

    settings = get_settings(user_id)
    return jsonify({"status": "success", "data": settings})

@app.route('/api/system/reset-demo', methods=['POST'])
def reset_demo():
    seed_sample_data()
    return jsonify({"status": "success", "message": "Demo data reset successfully to 30-day baseline."})

if __name__ == '__main__':
    print("Starting WattWise Flask API server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
