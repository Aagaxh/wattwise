import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from database import get_db_connection
from models import get_settings, get_appliances, get_goal

def get_energy_df(user_id):
    """Load energy records for user into a Pandas DataFrame."""
    conn = get_db_connection()
    query = '''
        SELECT id, user_id, appliance_name, date, hour, power_watts, usage_hours, energy_kwh, room
        FROM energy_records
        WHERE user_id = ?
        ORDER BY date ASC, hour ASC
    '''
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df['energy_kwh'] = pd.to_numeric(df['energy_kwh'], errors='coerce').fillna(0.0)
        df['power_watts'] = pd.to_numeric(df['power_watts'], errors='coerce').fillna(0.0)
        df['hour'] = pd.to_numeric(df['hour'], errors='coerce').astype(int)
    return df

def get_dashboard_summary(user_id):
    df = get_energy_df(user_id)
    settings = get_settings(user_id)
    tariff = settings.get('tariff_rate', 8.0)
    curr = settings.get('currency', '₹')

    if df.empty:
        return {
            "total_energy_kwh": 0.0,
            "estimated_bill": f"{curr}0",
            "highest_consumer": {"name": "None", "kwh": 0.0, "percentage": 0},
            "peak_usage_window": "N/A",
            "monthly_savings_potential": f"{curr}0",
            "consumption_trend": [],
            "appliance_comparison": [],
            "appliance_contribution": [],
            "peak_timeline": [],
            "ai_insight": "No data available yet. Please add appliances or upload a dataset to see analytics.",
            "recent_alerts": [],
            "stats": {"daily_avg_kwh": 0, "max_day_kwh": 0}
        }

    # Total energy across the 30-day recorded window
    total_kwh = round(float(df['energy_kwh'].sum()), 2)
    # Energy cost + fixed charges
    energy_cost = total_kwh * tariff
    fixed_charges = settings.get('fixed_charges', 100.0)
    tax_rate = settings.get('tax_rate', 5.0)
    total_bill = round(energy_cost + fixed_charges + ((energy_cost + fixed_charges) * (tax_rate / 100.0)), 2)

    # Appliance aggregation
    app_group = df.groupby('appliance_name')['energy_kwh'].sum().sort_values(ascending=False)
    highest_app = app_group.index[0] if not app_group.empty else "None"
    highest_kwh = round(float(app_group.iloc[0]), 2) if not app_group.empty else 0.0
    highest_pct = round((highest_kwh / total_kwh * 100), 1) if total_kwh > 0 else 0.0

    # Hourly peak detection
    hourly_group = df.groupby('hour')['energy_kwh'].sum()
    peak_hour = int(hourly_group.idxmax()) if not hourly_group.empty else 20
    # Window: 2 hours before to 2 hours after peak hour, clamped to 0-23
    w_start = max(0, peak_hour - 2)
    w_end = min(23, peak_hour + 2)
    start_fmt = f"{(w_start % 12) or 12} {'AM' if w_start < 12 else 'PM'}"
    end_fmt = f"{(w_end % 12) or 12} {'AM' if w_end < 12 else 'PM'}"
    peak_window_str = f"{start_fmt} – {end_fmt}"

    # Savings potential: 15% reduction in top consumer + 10% on other heavy appliances
    potential_savings_kwh = (highest_kwh * 0.15) + ((total_kwh - highest_kwh) * 0.08)
    potential_savings_val = round(potential_savings_kwh * tariff, 2)

    # Consumption trend: Daily aggregation
    daily_group = df.groupby(df['date'].dt.strftime('%Y-%m-%d'))['energy_kwh'].sum().reset_index()
    consumption_trend = [
        {
            "date": row['date'],
            "kwh": round(float(row['energy_kwh']), 2),
            "cost": round(float(row['energy_kwh']) * tariff, 2)
        }
        for _, row in daily_group.iterrows()
    ]

    # Appliance comparison & contribution
    appliance_comparison = []
    appliance_contribution = []
    for app_name, kwh in app_group.items():
        pct = round((kwh / total_kwh * 100), 1) if total_kwh > 0 else 0
        appliance_comparison.append({
            "appliance": app_name,
            "kwh": round(float(kwh), 2),
            "cost": round(float(kwh) * tariff, 2),
            "percentage": pct
        })
        appliance_contribution.append({
            "name": app_name,
            "value": round(float(kwh), 2),
            "percentage": pct
        })

    # Hourly timeline (Area chart for 24 hours average)
    num_days = df['date'].nunique() or 1
    peak_timeline = []
    for h in range(24):
        h_kwh = float(hourly_group.get(h, 0.0)) / num_days
        h_label = f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"
        peak_timeline.append({
            "hour": h,
            "hour_label": h_label,
            "kwh": round(h_kwh, 2)
        })

    # AI Insight text
    ai_insight = (
        f"{highest_app} is your single largest electricity driver, accounting for {highest_pct}% "
        f"({highest_kwh} kWh) of total household consumption. Your peak load consistently occurs between "
        f"{peak_window_str}. Shifting flexible tasks outside this window and moderating {highest_app} "
        f"can save up to {curr}{potential_savings_val:.0f}/month."
    )

    # Get recent anomalies for quick dashboard alerts
    anomalies = detect_anomalies(user_id)
    recent_alerts = anomalies[:3] if anomalies else []

    daily_avg = round(total_kwh / num_days, 2)
    max_day = round(float(daily_group['energy_kwh'].max()), 2) if not daily_group.empty else 0.0

    return {
        "total_energy_kwh": total_kwh,
        "estimated_bill": f"{curr}{total_bill:,.0f}",
        "raw_estimated_bill": total_bill,
        "highest_consumer": {
            "name": highest_app,
            "kwh": highest_kwh,
            "percentage": highest_pct
        },
        "peak_usage_window": peak_window_str,
        "monthly_savings_potential": f"{curr}{potential_savings_val:,.0f}",
        "raw_savings_potential": potential_savings_val,
        "consumption_trend": consumption_trend,
        "appliance_comparison": appliance_comparison,
        "appliance_contribution": appliance_contribution,
        "peak_timeline": peak_timeline,
        "ai_insight": ai_insight,
        "recent_alerts": recent_alerts,
        "stats": {
            "daily_avg_kwh": daily_avg,
            "max_day_kwh": max_day,
            "num_days": num_days
        }
    }

def get_appliance_analysis(user_id):
    df = get_energy_df(user_id)
    settings = get_settings(user_id)
    tariff = settings.get('tariff_rate', 8.0)
    curr = settings.get('currency', '₹')
    appliances_meta = {a['name']: a for a in get_appliances(user_id)}

    if df.empty:
        return {"rankings": [], "summary_insight": "No appliance data found."}

    total_kwh = float(df['energy_kwh'].sum())
    num_days = max(1, df['date'].nunique())

    # Group by appliance
    app_group = df.groupby('appliance_name').agg(
        total_kwh=('energy_kwh', 'sum'),
        avg_power=('power_watts', 'mean'),
        avg_hours=('usage_hours', 'sum') # total usage hours across days
    ).reset_index()

    app_group = app_group.sort_values(by='total_kwh', ascending=False)

    rankings = []
    for rank, row in enumerate(app_group.itertuples(), start=1):
        name = row.appliance_name
        tot_kwh = float(row.total_kwh)
        pct = round((tot_kwh / total_kwh * 100), 1) if total_kwh > 0 else 0
        meta = appliances_meta.get(name, {})
        power = meta.get('power_watts', round(float(row.avg_power), 0))
        hours_per_day = meta.get('usage_hours', round(float(row.avg_hours) / num_days, 1))
        daily_kwh = round(tot_kwh / num_days, 2)
        weekly_kwh = round(daily_kwh * 7, 2)
        monthly_kwh = round(daily_kwh * 30, 2)
        monthly_cost = round(monthly_kwh * tariff, 2)

        # Recommendation per appliance
        saving_tip = f"Operate efficiently. Clean filters or reduce daily run time by 30-45 minutes."
        if "air conditioner" in name.lower() or "ac" in name.lower():
            saving_tip = "Set thermostat to 24°C instead of 18°C-20°C to reduce compressor power by 18-24%."
        elif "refrigerator" in name.lower() or "fridge" in name.lower():
            saving_tip = "Ensure door gasket is sealed tightly and allow 2 inches of ventilation behind the coils."
        elif "water heater" in name.lower() or "geyser" in name.lower():
            saving_tip = "Turn off 10 minutes before shower end; install a timer switch to prevent accidental continuous heating."
        elif "washing machine" in name.lower():
            saving_tip = "Wash with full loads on cold-water cycles; air dry clothes when sunny."
        elif "tv" in name.lower() or "television" in name.lower():
            saving_tip = "Disable quick-start standby modes which consume 15W phantom power continuously."

        rankings.append({
            "rank": rank,
            "name": name,
            "category": meta.get('category', 'General'),
            "room": meta.get('room', 'Household'),
            "power_watts": power,
            "usage_hours": hours_per_day,
            "daily_kwh": daily_kwh,
            "weekly_kwh": weekly_kwh,
            "monthly_kwh": monthly_kwh,
            "percentage": pct,
            "estimated_monthly_cost": monthly_cost,
            "currency": curr,
            "saving_tip": saving_tip
        })

    top = rankings[0] if rankings else None
    summary_insight = (
        f"{top['name']} contributes {top['percentage']}% of total household energy consumption, "
        f"costing approximately {curr}{top['estimated_monthly_cost']:,.0f}/month."
        if top else "No appliances found."
    )

    return {
        "rankings": rankings,
        "summary_insight": summary_insight
    }

def get_energy_analytics(user_id, filter_type='last30', start_date=None, end_date=None):
    df = get_energy_df(user_id)
    settings = get_settings(user_id)
    tariff = settings.get('tariff_rate', 8.0)
    curr = settings.get('currency', '₹')

    if df.empty:
        return {
            "daily_trend": [],
            "weekly_comparison": [],
            "monthly_trend": [],
            "appliance_donut": [],
            "hourly_area": [],
            "bill_trend": [],
            "stats": {"avg_daily_kwh": 0, "max_daily_kwh": 0, "min_daily_kwh": 0, "total_kwh": 0, "avg_daily_cost": 0}
        }

    max_date = df['date'].max()

    # Apply date filters
    if filter_type == 'today':
        df_filtered = df[df['date'] == max_date]
    elif filter_type == 'last7':
        cutoff = max_date - timedelta(days=6)
        df_filtered = df[df['date'] >= cutoff]
    elif filter_type == 'this_month':
        df_filtered = df[(df['date'].dt.month == max_date.month) & (df['date'].dt.year == max_date.year)]
    elif filter_type == 'custom' and start_date and end_date:
        df_filtered = df[(df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))]
    else: # last30 default
        cutoff = max_date - timedelta(days=29)
        df_filtered = df[df['date'] >= cutoff]

    if df_filtered.empty:
        df_filtered = df

    # 1. Daily Trend
    daily_df = df_filtered.groupby(df_filtered['date'].dt.strftime('%Y-%m-%d'))['energy_kwh'].sum().reset_index()
    daily_trend = [
        {"date": r['date'], "kwh": round(float(r['energy_kwh']), 2), "cost": round(float(r['energy_kwh']) * tariff, 2)}
        for _, r in daily_df.iterrows()
    ]

    # 2. Weekly comparison
    df_filtered_copy = df_filtered.copy()
    df_filtered_copy['week'] = df_filtered_copy['date'].dt.strftime('Wk %U')
    weekly_df = df_filtered_copy.groupby('week')['energy_kwh'].sum().reset_index()
    weekly_comparison = [
        {"week": r['week'], "kwh": round(float(r['energy_kwh']), 2), "cost": round(float(r['energy_kwh']) * tariff, 2)}
        for _, r in weekly_df.iterrows()
    ]

    # 3. Monthly Trend (group by Month Year)
    df_filtered_copy['month'] = df_filtered_copy['date'].dt.strftime('%b %Y')
    monthly_df = df_filtered_copy.groupby('month', sort=False)['energy_kwh'].sum().reset_index()
    monthly_trend = [
        {"month": r['month'], "kwh": round(float(r['energy_kwh']), 2), "cost": round(float(r['energy_kwh']) * tariff, 2)}
        for _, r in monthly_df.iterrows()
    ]

    # 4. Appliance Donut
    total_filt_kwh = float(df_filtered['energy_kwh'].sum())
    app_filt = df_filtered.groupby('appliance_name')['energy_kwh'].sum().sort_values(ascending=False)
    appliance_donut = [
        {
            "name": name,
            "value": round(float(kwh), 2),
            "percentage": round((kwh / total_filt_kwh * 100), 1) if total_filt_kwh > 0 else 0
        }
        for name, kwh in app_filt.items()
    ]

    # 5. Hourly Area (0-23 average)
    num_days_filt = max(1, df_filtered['date'].nunique())
    hourly_filt = df_filtered.groupby('hour')['energy_kwh'].sum()
    hourly_area = [
        {
            "hour": h,
            "time_label": f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}",
            "kwh": round(float(hourly_filt.get(h, 0.0)) / num_days_filt, 2)
        }
        for h in range(24)
    ]

    # 6. Estimated Bill Trend (by date)
    bill_trend = [
        {
            "date": r['date'],
            "energy_cost": round(float(r['energy_kwh']) * tariff, 2),
            "cumulative_bill": round(daily_df.loc[:i, 'energy_kwh'].sum() * tariff, 2)
        }
        for i, r in daily_df.iterrows()
    ]

    # Stats
    total_kwh_stat = round(total_filt_kwh, 2)
    avg_daily_kwh = round(total_filt_kwh / num_days_filt, 2)
    max_daily_kwh = round(float(daily_df['energy_kwh'].max()), 2) if not daily_df.empty else 0.0
    min_daily_kwh = round(float(daily_df['energy_kwh'].min()), 2) if not daily_df.empty else 0.0
    avg_daily_cost = round(avg_daily_kwh * tariff, 2)

    return {
        "daily_trend": daily_trend,
        "weekly_comparison": weekly_comparison,
        "monthly_trend": monthly_trend,
        "appliance_donut": appliance_donut,
        "hourly_area": hourly_area,
        "bill_trend": bill_trend,
        "stats": {
            "avg_daily_kwh": avg_daily_kwh,
            "max_daily_kwh": max_daily_kwh,
            "min_daily_kwh": min_daily_kwh,
            "total_kwh": total_kwh_stat,
            "avg_daily_cost": avg_daily_cost,
            "total_days": num_days_filt,
            "currency": curr
        }
    }

def get_peak_usage_analysis(user_id):
    df = get_energy_df(user_id)
    if df.empty:
        return {
            "hourly_curve": [],
            "highest_hour": "N/A",
            "peak_period": "N/A",
            "low_period": "N/A",
            "peak_appliances": [],
            "explanation": "No hourly data available."
        }

    num_days = max(1, df['date'].nunique())
    # Group by hour to find average hourly load
    hourly_totals = df.groupby('hour')['energy_kwh'].sum()
    hourly_avg = hourly_totals / num_days

    # Identify top 4 continuous peak hours
    rolling_4h = hourly_avg.rolling(4, min_periods=1).mean()
    peak_end_hour = int(rolling_4h.idxmax())
    peak_start_hour = max(0, peak_end_hour - 3)

    highest_h = int(hourly_avg.idxmax())
    highest_h_val = round(float(hourly_avg.max()), 2)

    low_h = int(hourly_avg.idxmin())

    fmt_hour = lambda h: f"{(h % 12) or 12}:00 {'AM' if h < 12 else 'PM'}"
    peak_period_str = f"{fmt_hour(peak_start_hour)} – {fmt_hour(min(23, peak_end_hour + 1))}"
    low_period_str = f"{fmt_hour(max(0, low_h - 2))} – {fmt_hour(min(23, low_h + 2))}"
    highest_hour_str = f"{fmt_hour(highest_h)} ({highest_h_val} kWh avg)"

    # Hourly curve dataset
    hourly_curve = []
    for h in range(24):
        val = round(float(hourly_avg.get(h, 0.0)), 2)
        is_peak = (peak_start_hour <= h <= peak_end_hour)
        hourly_curve.append({
            "hour": h,
            "time_label": fmt_hour(h),
            "kwh": val,
            "is_peak": is_peak
        })

    # Filter df during peak hours to find overlapping appliances
    peak_df = df[df['hour'].between(peak_start_hour, peak_end_hour)]
    peak_app_group = peak_df.groupby('appliance_name').agg(
        peak_kwh=('energy_kwh', 'sum'),
        power=('power_watts', 'mean'),
        room=('room', 'first')
    ).reset_index()

    total_peak_kwh = float(peak_df['energy_kwh'].sum())
    peak_app_group = peak_app_group.sort_values(by='peak_kwh', ascending=False)

    peak_appliances = []
    for row in peak_app_group.itertuples():
        share = round((row.peak_kwh / total_peak_kwh * 100), 1) if total_peak_kwh > 0 else 0
        peak_appliances.append({
            "appliance": row.appliance_name,
            "power_watts": int(row.power),
            "room": row.room or "General",
            "peak_contribution_pct": share,
            "peak_daily_kwh": round(float(row.peak_kwh) / num_days, 2)
        })

    explanation = (
        f"Peak electricity usage is concentrated between {peak_period_str}. During this 4-hour window, "
        f"multiple high-power loads (such as {', '.join([p['appliance'] for p in peak_appliances[:3]])}) "
        f"overlap simultaneously, creating a sharp surge on your circuit and multiplying bill costs. "
        f"Delaying the washing machine or dishwashing cycle until 10:30 PM can immediately flatten this peak by up to 22%."
    )

    return {
        "hourly_curve": hourly_curve,
        "highest_hour": highest_hour_str,
        "peak_period": peak_period_str,
        "low_period": low_period_str,
        "peak_appliances": peak_appliances,
        "explanation": explanation
    }

def detect_anomalies(user_id):
    """Detect statistical and rule-based anomalies in energy records."""
    df = get_energy_df(user_id)
    if df.empty:
        return []

    anomalies = []
    alert_id = 1

    # 1. Per-Appliance Daily Moving Average & Surge Detection
    # Aggregate by date and appliance
    daily_app = df.groupby(['appliance_name', df['date'].dt.strftime('%Y-%m-%d')])['energy_kwh'].sum().reset_index()

    for app_name, group in daily_app.groupby('appliance_name'):
        if len(group) < 5:
            continue
        group = group.sort_values('date').copy()
        # 7-day rolling baseline
        group['rolling_mean'] = group['energy_kwh'].rolling(7, min_periods=3).mean()
        group['rolling_std'] = group['energy_kwh'].rolling(7, min_periods=3).std().fillna(0.1)

        # Look for spikes on any day where actual is significantly above baseline
        for idx, row in group.iterrows():
            actual = float(row['energy_kwh'])
            expected = float(row['rolling_mean'])
            std = float(row['rolling_std'])
            if expected > 0:
                dev_pct = round(((actual - expected) / expected) * 100, 1)
                z_score = (actual - expected) / (std if std > 0 else 0.1)

                if dev_pct >= 25.0 and actual > 0.5:
                    severity = "High" if dev_pct >= 50.0 else "Medium"
                    reason = f"Unusual sustained operation or thermostat failure causing continuous compressor/heating cycle."
                    action = f"Inspect {app_name} door seals, thermostat settings, or power switches."

                    if "refrigerator" in app_name.lower():
                        reason = f"Refrigerator consumption increased by {dev_pct}% compared to normal baseline. Possible causes: Door left ajar, damaged magnetic gasket, or dust-clogged condenser coils."
                        action = f"Check door seal with paper test, clean rear condenser coils, and verify internal temperature setting."
                    elif "air conditioner" in app_name.lower():
                        reason = f"Air Conditioner usage exceeded normal daily average by {dev_pct}%. Possible causes: Extremely low temperature setting, dirty air filters, or refrigerant leak."
                        action = f"Clean air filters, set temperature to 24°C, and ensure bedroom windows/doors are properly closed."
                    elif "water heater" in app_name.lower():
                        reason = f"Water Heater ran for longer than normal morning schedule (+{dev_pct}%). Possible causes: Switched on and forgotten, or internal thermostat stuck."
                        action = f"Turn off heater immediately after use or install an automated 45-minute countdown cut-off timer."

                    anomalies.append({
                        "id": alert_id,
                        "severity": severity,
                        "appliance": app_name,
                        "detected_date": row['date'],
                        "expected_kwh": round(expected, 2),
                        "actual_kwh": round(actual, 2),
                        "deviation_pct": dev_pct,
                        "possible_reason": reason,
                        "suggested_action": action
                    })
                    alert_id += 1

    # 2. Check for Overnight Unusual Heavy Usage (between 1 AM and 5 AM)
    night_df = df[df['hour'].between(1, 4)]
    heavy_night = night_df[night_df['power_watts'] >= 800]
    if not heavy_night.empty:
        night_summary = heavy_night.groupby(['appliance_name', heavy_night['date'].dt.strftime('%Y-%m-%d')])['energy_kwh'].sum().reset_index()
        for _, r in night_summary.head(3).iterrows():
            anomalies.append({
                "id": alert_id,
                "severity": "Low",
                "appliance": r['appliance_name'],
                "detected_date": r['date'],
                "expected_kwh": 0.0,
                "actual_kwh": round(float(r['energy_kwh']), 2),
                "deviation_pct": 100.0,
                "possible_reason": f"High wattage equipment ({r['appliance_name']}) active between 1:00 AM – 5:00 AM.",
                "suggested_action": f"Verify if overnight operation was intentional or if appliance was left running inadvertently."
            })
            alert_id += 1

    # Sort anomalies by detected_date descending, then severity
    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    anomalies.sort(key=lambda x: (x['detected_date'], -severity_order.get(x['severity'], 3)), reverse=True)
    return anomalies

def calculate_bill(user_id, consumption_kwh=None, custom_tariff=None, custom_fixed=None, custom_tax=None):
    settings = get_settings(user_id)
    curr = settings.get('currency', '₹')

    if consumption_kwh is None:
        df = get_energy_df(user_id)
        consumption_kwh = float(df['energy_kwh'].sum()) if not df.empty else 0.0

    tariff = float(custom_tariff) if custom_tariff is not None else float(settings.get('tariff_rate', 8.0))
    fixed = float(custom_fixed) if custom_fixed is not None else float(settings.get('fixed_charges', 100.0))
    addl = float(settings.get('additional_charges', 50.0))
    tax_pct = float(custom_tax) if custom_tax is not None else float(settings.get('tax_rate', 5.0))

    energy_cost = round(consumption_kwh * tariff, 2)
    subtotal = energy_cost + fixed + addl
    tax_amount = round(subtotal * (tax_pct / 100.0), 2)
    total_bill = round(subtotal + tax_amount, 2)

    # Savings simulation table: 5%, 10%, 15%, 20%, 25%, 30%
    savings_scenarios = []
    for pct in [5, 10, 15, 20, 25, 30]:
        saved_kwh = round(consumption_kwh * (pct / 100.0), 2)
        new_kwh = round(consumption_kwh - saved_kwh, 2)
        new_energy_cost = round(new_kwh * tariff, 2)
        new_subtotal = new_energy_cost + fixed + addl
        new_total = round(new_subtotal + (new_subtotal * (tax_pct / 100.0)), 2)
        saved_amount = round(total_bill - new_total, 2)
        savings_scenarios.append({
            "reduction_pct": pct,
            "reduced_kwh": saved_kwh,
            "projected_bill": new_total,
            "saved_amount": saved_amount
        })

    return {
        "consumption_kwh": round(consumption_kwh, 2),
        "tariff_rate": tariff,
        "energy_cost": energy_cost,
        "fixed_charges": fixed,
        "additional_charges": addl,
        "tax_percentage": tax_pct,
        "tax_amount": tax_amount,
        "estimated_total_bill": total_bill,
        "currency": curr,
        "savings_scenarios": savings_scenarios
    }

def get_intelligent_recommendations(user_id):
    """Generate dynamic, actionable energy-saving recommendations based on actual data."""
    df = get_energy_df(user_id)
    settings = get_settings(user_id)
    tariff = settings.get('tariff_rate', 8.0)
    curr = settings.get('currency', '₹')

    if df.empty:
        return []

    total_kwh = float(df['energy_kwh'].sum())
    app_totals = df.groupby('appliance_name')['energy_kwh'].sum().sort_values(ascending=False)
    recommendations = []

    # Recommendation 1: Highest consumer optimization
    if not app_totals.empty:
        top_app = app_totals.index[0]
        top_kwh = float(app_totals.iloc[0])
        # Reducing by 1 hour daily saves:
        daily_saving_kwh = (top_kwh / 30.0) * 0.20 # ~20% reduction
        monthly_saving_kwh = round(daily_saving_kwh * 30, 1)
        monthly_saving_cost = round(monthly_saving_kwh * tariff, 0)

        recommendations.append({
            "id": 1,
            "title": f"Reduce {top_app} runtime by 1 hour daily",
            "category": "High Impact",
            "impact_level": "High",
            "estimated_kwh_saving": monthly_saving_kwh,
            "estimated_cost_saving": f"{curr}{monthly_saving_cost:,.0f}",
            "description": f"{top_app} accounts for {round(top_kwh/total_kwh*100, 1)}% of your bill. Reducing daily usage by just 60 minutes or adjusting its operating settings delivers immediate savings.",
            "action_steps": [
                f"Set a reminder or smart plug timer to shut off {top_app} 1 hour earlier.",
                f"If cooling/heating, adjust thermostat by 1-2 degrees towards ambient temperature.",
                f"Ensure routine maintenance such as dust clearance and filter cleaning."
            ]
        })

    # Recommendation 2: Peak load shifting
    peak_analysis = get_peak_usage_analysis(user_id)
    peak_period = peak_analysis.get('peak_period', '6:00 PM – 10:00 PM')
    recommendations.append({
        "id": 2,
        "title": "Shift flexible heavy loads outside peak hours",
        "category": "Peak Shifting",
        "impact_level": "Medium",
        "estimated_kwh_saving": round(total_kwh * 0.08, 1),
        "estimated_cost_saving": f"{curr}{round(total_kwh * 0.08 * tariff, 0):,.0f}",
        "description": f"Your peak consumption occurs between {peak_period}. Heavy appliances running at the same time stress the circuit and fall under peak tariff rates.",
        "action_steps": [
            "Run the Washing Machine before 9:00 AM or on weekend mornings.",
            "Use the Microwave or heavy cooking appliances staggered rather than all during 8:00 PM.",
            "Charge laptops and power banks during low morning hours."
        ]
    })

    # Recommendation 3: Refrigerator optimization
    if "Refrigerator" in app_totals:
        fridge_kwh = float(app_totals["Refrigerator"])
        fridge_saving_cost = round(fridge_kwh * 0.15 * tariff, 0)
        recommendations.append({
            "id": 3,
            "title": "Calibrate Refrigerator temperature & seal inspection",
            "category": "Continuous Load",
            "impact_level": "Medium",
            "estimated_kwh_saving": round(fridge_kwh * 0.15, 1),
            "estimated_cost_saving": f"{curr}{fridge_saving_cost:,.0f}",
            "description": "Refrigerators operate 24/7. Setting them just 2 degrees colder than needed or letting gaskets leak adds up to 15-25% to their baseline load.",
            "action_steps": [
                "Maintain fridge compartment at 3°C to 4°C and freezer at -18°C.",
                "Leave at least 2 inches clearance behind the unit for coil heat dissipation.",
                "Avoid placing hot or warm food directly inside the refrigerator."
            ]
        })

    # Recommendation 4: Standby / Phantom Power Elimination
    recommendations.append({
        "id": 4,
        "title": "Eliminate Standby Phantom Loads",
        "category": "Efficiency",
        "impact_level": "Low",
        "estimated_kwh_saving": 12.0,
        "estimated_cost_saving": f"{curr}{round(12.0 * tariff, 0):,.0f}",
        "description": "Televisions, set-top boxes, laptops, and microwave clocks draw 5–15 Watts continuously even when switched off via remote control.",
        "action_steps": [
            "Use a master switch or surge protector to turn off media entertainment centers completely at night.",
            "Unplug phone and laptop chargers when devices reach 100%."
        ]
    })

    # Recommendation 5: Air Conditioner Temperature Optimization
    if "Air Conditioner" in app_totals:
        ac_kwh = float(app_totals["Air Conditioner"])
        ac_saving_cost = round(ac_kwh * 0.24 * tariff, 0)
        recommendations.append({
            "id": 5,
            "title": "Adopt 24°C Comfort Setting on Air Conditioner",
            "category": "Thermostat",
            "impact_level": "High",
            "estimated_kwh_saving": round(ac_kwh * 0.24, 1),
            "estimated_cost_saving": f"{curr}{ac_saving_cost:,.0f}",
            "description": "Each degree Celsius increase on your AC thermostat saves between 6% and 8% of compressor energy. 24°C provides optimal human comfort with dramatically lower bills.",
            "action_steps": [
                "Run ceiling fan at low speed in conjunction with AC at 24°C to distribute chilled air evenly.",
                "Use the AC Sleep / Eco mode to let temperature naturally raise by 1°C over 4 hours at night.",
                "Clean the mesh air filter every 2 weeks during summer."
            ]
        })

    return recommendations

def handle_advisor_query(user_id, query):
    """Answer natural language user questions using actual live database statistics."""
    df = get_energy_df(user_id)
    settings = get_settings(user_id)
    curr = settings.get('currency', '₹')
    tariff = settings.get('tariff_rate', 8.0)
    query_lower = query.lower()

    if df.empty:
        return "I don't have enough recorded electricity data to answer your question yet. Please add household appliances or upload a CSV dataset to get started!"

    total_kwh = round(float(df['energy_kwh'].sum()), 1)
    app_totals = df.groupby('appliance_name')['energy_kwh'].sum().sort_values(ascending=False)
    top_app = app_totals.index[0]
    top_kwh = round(float(app_totals.iloc[0]), 1)
    top_pct = round((top_kwh / total_kwh * 100), 1)

    peak_info = get_peak_usage_analysis(user_id)
    peak_period = peak_info.get('peak_period', '6:00 PM – 10:00 PM')
    highest_hour = peak_info.get('highest_hour', '8:00 PM')

    anomalies = detect_anomalies(user_id)

    # Match common energy queries
    if any(w in query_lower for w in ["most", "highest", "top consumer", "maximum", "who consumes"]):
        return (
            f"Based on your recorded data, **{top_app}** is your highest electricity consumer, "
            f"using **{top_kwh} kWh** ({top_pct}% of your household total). "
            f"At your tariff rate of {curr}{tariff}/kWh, {top_app} alone costs approximately "
            f"**{curr}{round(top_kwh * tariff):,.0f}** for this recorded period."
        )

    elif any(w in query_lower for w in ["peak", "when", "time", "hour", "hours", "night"]):
        return (
            f"Your household electricity usage peaks between **{peak_period}**, with the highest spike recorded "
            f"around **{highest_hour}**. This is primarily driven by overlapping loads from "
            f"{', '.join([p['appliance'] for p in peak_info.get('peak_appliances', [])[:3]])}. "
            f"Shifting tasks like laundry or dishwasher cycles outside this window will significantly reduce strain and costs."
        )

    elif any(w in query_lower for w in ["reduce", "save", "lower bill", "how to save", "cut"]):
        savings_val = round(((top_kwh * 0.18) + (total_kwh * 0.07)) * tariff)
        return (
            f"Here are the 3 fastest ways to lower your electricity bill based on your specific usage:\n\n"
            f"1. **Optimize {top_app}**: Moderating its runtime by 1 hour daily or adjusting the thermostat setting can save up to **{curr}{round(top_kwh * 0.20 * tariff):,.0f}/month**.\n"
            f"2. **De-conflict Peak Hours ({peak_period})**: Avoid running laundry or heavy kitchen loads simultaneously with cooling.\n"
            f"3. **Eliminate Standby Power**: Switch off appliances from the wall socket to prevent phantom draw.\n\n"
            f"Following these steps can save you approximately **{curr}{savings_val:,.0f}** every month."
        )

    elif any(w in query_lower for w in ["ac", "air conditioner", "cooling"]):
        ac_kwh = float(app_totals.get("Air Conditioner", 0))
        if ac_kwh > 0:
            saving_1hr = round((ac_kwh / 30.0) * 0.2 * 30 * tariff)
            return (
                f"Your Air Conditioner accounts for **{round(ac_kwh/total_kwh*100, 1)}%** of your total electricity consumption ({round(ac_kwh, 1)} kWh). "
                f"Setting your thermostat to **24°C instead of 20°C** reduces compressor workload by up to 24%, "
                f"which translates to estimated savings of **{curr}{saving_1hr:,.0f} per month**! "
                f"Also remember to run your ceiling fan at low speed to circulate chilled air."
            )
        else:
            return "No specific Air Conditioner records were found in your current dataset. You can add one via the Appliance Management page!"

    elif any(w in query_lower for w in ["anomaly", "abnormal", "unusual", "fault", "spike", "monitor"]):
        if anomalies:
            top_a = anomalies[0]
            return (
                f"Yes, our anomaly detection system flagged **{len(anomalies)} unusual consumption events** in your records. "
                f"The most notable is for **{top_a['appliance']}** on {top_a['detected_date']}, where consumption surged by "
                f"**+{top_a['deviation_pct']}%** above expected normal ({top_a['actual_kwh']} kWh actual vs {top_a['expected_kwh']} kWh expected). "
                f"Possible reason: {top_a['possible_reason']} Action: {top_a['suggested_action']}"
            )
        else:
            return "All appliances are currently operating within their expected normal baseline ranges with no abnormal spikes detected."

    elif any(w in query_lower for w in ["bill", "cost", "tariff", "rupees", "how much"]):
        total_bill = round(total_kwh * tariff + 100 + ((total_kwh * tariff + 100) * 0.05))
        return (
            f"Your estimated electricity bill for the 30-day period is **{curr}{total_bill:,.0f}** "
            f"based on **{total_kwh} kWh** total consumption at {curr}{tariff}/kWh, plus fixed charges and taxes. "
            f"If you achieve a 15% reduction across major appliances, your bill would drop to **{curr}{round(total_bill * 0.85):,.0f}** "
            f"(saving **{curr}{round(total_bill * 0.15):,.0f}**)."
        )

    else:
        # General intelligent response
        return (
            f"Based on your current household profile ({len(app_totals)} active appliances, {total_kwh} kWh total consumption):\n\n"
            f"- **Top Consumer**: {top_app} ({top_pct}% of bill)\n"
            f"- **Peak Window**: {peak_period}\n"
            f"- **Current Estimated Bill**: {curr}{round(total_kwh * tariff):,.0f}\n"
            f"- **Recommended Action**: Monitor {top_app} closely and shift discretionary laundry or water heating away from evening peak hours."
        )

def generate_report_data(user_id):
    """Generate comprehensive audit report payload."""
    dashboard = get_dashboard_summary(user_id)
    appliances = get_appliance_analysis(user_id)
    peak = get_peak_usage_analysis(user_id)
    anomalies = detect_anomalies(user_id)
    bill = calculate_bill(user_id)
    recommendations = get_intelligent_recommendations(user_id)

    return {
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "user_id": user_id,
        "executive_summary": {
            "total_consumption_kwh": dashboard["total_energy_kwh"],
            "estimated_bill": dashboard["estimated_bill"],
            "highest_consumer": dashboard["highest_consumer"],
            "peak_period": peak["peak_period"],
            "potential_savings": dashboard["monthly_savings_potential"]
        },
        "appliances_breakdown": appliances["rankings"],
        "peak_analysis": peak,
        "anomalies_detected": anomalies,
        "bill_breakdown": bill,
        "recommendations": recommendations
    }
