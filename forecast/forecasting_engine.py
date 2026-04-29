import streamlit as st
import pandas as pd
import numpy as np
import math
import mysql.connector # 🔴 RESTORED: Native MySQL
from mysql.connector import Error
from statsmodels.tsa.statespace.sarimax import SARIMAX
import holidays
import datetime
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

# 
#  DATABASE CONNECTION
# 
def get_db_connection():
    try:
        # Connects securely using Streamlit Secrets
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            port=st.secrets["mysql"]["port"],
            database=st.secrets["mysql"]["database"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"]
        )
    except Error as e:
        st.error(f"Database Connection Failed: {e}")
        return None
    except Error as e:
        print(f"Database Connection Failed: {e}")
        return None

# 
# DASHBOARD DATA FETCHING
# 
def get_dashboard_summary():
    conn = get_db_connection()
    dashboard_data = {
        "kpi": {"active": 0, "all": 0, "low": 0, "out": 0, "reorder": 0},
        "health": {"score": 100, "qty_hand": 0, "po_value": 0},
        "top_selling": pd.DataFrame(columns=["Product", "Sales"]),
        "alerts": pd.DataFrame(),
        "forecast_preview": pd.DataFrame({"Day": range(1, 8), "Expected Sales": [0]*7})
    }

    if not conn: return dashboard_data

    try:
        cursor = conn.cursor(dictionary=True) 

        cursor.execute("SELECT COUNT(*) as count FROM products WHERE is_active = 1")
        dashboard_data["kpi"]["active"] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM products")
        dashboard_data["kpi"]["all"] = cursor.fetchone()['count']

        stock_query = """
            SELECT p.product_id, p.name, p.sku, IFNULL(p.reorder_threshold, 10) as reorder_threshold, 
                   IFNULL(SUM(il.quantity_change), 0) as current_stock
            FROM products p
            LEFT JOIN inventory_ledger il ON p.product_id = il.product_id
            WHERE p.is_active = 1
            GROUP BY p.product_id, p.name, p.sku, p.reorder_threshold
        """
        cursor.execute(stock_query)
        stock_data = cursor.fetchall()
        
        if stock_data:
            df_stock = pd.DataFrame(stock_data)
            out_stock = df_stock[df_stock['current_stock'] <= 0]
            low_stock = df_stock[(df_stock['current_stock'] > 0) & (df_stock['current_stock'] <= df_stock['reorder_threshold'])]
            
            dashboard_data["kpi"]["out"] = len(out_stock)
            dashboard_data["kpi"]["low"] = len(low_stock)
            dashboard_data["kpi"]["reorder"] = len(out_stock) + len(low_stock)
            
            healthy_items = dashboard_data["kpi"]["active"] - dashboard_data["kpi"]["reorder"]
            if dashboard_data["kpi"]["active"] > 0:
                dashboard_data["health"]["score"] = int((healthy_items / dashboard_data["kpi"]["active"]) * 100)
            
            alerts_df = df_stock[df_stock['current_stock'] <= df_stock['reorder_threshold']]
            dashboard_data["alerts"] = alerts_df.sort_values(by='current_stock').head(5)

        try:
            cursor.execute("SELECT SUM(total_amount) as total FROM purchases WHERE status = 'PENDING'")
            res = cursor.fetchone()
            dashboard_data["health"]["po_value"] = float(res['total']) if res and res['total'] else 0.0
        except: pass

        try:
            cursor.execute("SELECT SUM(quantity_change) as qty FROM inventory_ledger")
            res = cursor.fetchone()
            dashboard_data["health"]["qty_hand"] = float(res['qty']) if res and res['qty'] else 0.0
        except: pass

        try:
            cursor.execute("""
                SELECT p.name as Product, SUM(si.quantity) as Sales 
                FROM sale_items si JOIN products p ON si.product_id = p.product_id 
                GROUP BY p.product_id ORDER BY Sales DESC LIMIT 5
            """)
            chart_data = cursor.fetchall()
            if chart_data: dashboard_data["top_selling"] = pd.DataFrame(chart_data)
            else: dashboard_data["top_selling"] = pd.DataFrame({"Product": ["No Sales"], "Sales": [1]})
        except: pass

        try:
            
            cursor.execute("""
                SELECT forecast_date as Day, SUM(predicted_demand) as 'Expected Sales'
                FROM forecasts WHERE forecast_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
                GROUP BY forecast_date ORDER BY forecast_date ASC
            """)
            f_data = cursor.fetchall()
            if f_data: dashboard_data["forecast_preview"] = pd.DataFrame(f_data)
            else:
                dashboard_data["forecast_preview"] = pd.DataFrame({
                    "Day": pd.date_range(start=datetime.date.today(), periods=7), 
                    "Expected Sales": [12, 18, 14, 22, 28, 35, 20]
                })
        except: pass

        cursor.close()
        conn.close()

    except Error as e:
        print(f"Error fetching dashboard data: {e}")
        if conn: conn.close()

    return dashboard_data

# ==========================================
# 🧠 PART 2: AI TRAINING & PREDICTION LOGIC
# ==========================================
def get_sales_history(product_id, conn):
   
    query = """
        SELECT DATE(sale_date) as date, SUM(quantity) as qty
        FROM sale_items si JOIN sales s ON si.sale_id = s.sale_id
        WHERE si.product_id = %s AND DATE(s.sale_date) >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
        GROUP BY DATE(sale_date) ORDER BY date ASC
    """
    df = pd.read_sql(query, conn, params=(product_id,))
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df['qty'] = df['qty'].clip(lower=0) 
        full_range = pd.date_range(start=df.index.min(), end=datetime.date.today(), freq='D')
        df = df.reindex(full_range, fill_value=0)
    return df

def get_exogenous_vars(date_index):
    in_holidays = holidays.India(years=date_index.year.unique()) 
    exog = pd.DataFrame(index=date_index)
    exog['is_weekend'] = (exog.index.dayofweek >= 5).astype(int)
    exog['is_holiday'] = exog.index.map(lambda x: 1 if x in in_holidays else 0)
    return exog

def generate_weekly_forecast(product_id):
    conn = get_db_connection()
    if not conn: return False
    
    try:
        df = get_sales_history(product_id, conn)
        
        hist_avg = float(df['qty'].mean()) if not df.empty else 0.0
        if pd.isna(hist_avg) or hist_avg == float('inf') or hist_avg == float('-inf'):
            hist_avg = 0.0
        hist_avg = min(max(hist_avg, 0.0), 999999.99) 
        
        use_fallback = False
        if len(df) < 14:
            use_fallback = True
        else:
            try:
                exog_train = get_exogenous_vars(df.index)
                model = SARIMAX(df['qty'], exog=exog_train, order=(1, 1, 1), seasonal_order=(1, 1, 0, 7),
                                enforce_stationarity=False, enforce_invertibility=False)
                results = model.fit(disp=False)
                future_dates = pd.date_range(start=datetime.date.today() + datetime.timedelta(days=1), periods=28, freq='D')
                exog_future = get_exogenous_vars(future_dates)
                forecast_obj = results.get_forecast(steps=28, exog=exog_future)
                
                forecast_df = pd.DataFrame({
                    'forecast_date': future_dates,
                    'predicted_demand': forecast_obj.predicted_mean.values
                })
                
                forecast_df['predicted_demand'] = forecast_df['predicted_demand'].fillna(0)
                forecast_df['predicted_demand'] = forecast_df['predicted_demand'].replace([np.inf, -np.inf], 0)
                forecast_df['predicted_demand'] = forecast_df['predicted_demand'].clip(lower=0, upper=999999.99)
                
                if forecast_df['predicted_demand'].max() >= 999999.0:
                    use_fallback = True
                    
            except Exception as model_err:
                print(f"Model error for product {product_id}, using fallback: {model_err}")
                use_fallback = True

        if use_fallback:
            dates = pd.date_range(start=datetime.date.today() + datetime.timedelta(days=1), periods=28, freq='D')
            forecast_df = pd.DataFrame({'forecast_date': dates, 'predicted_demand': [hist_avg]*28})

        cursor = conn.cursor()
     
        cursor.execute("DELETE FROM forecasts WHERE product_id = %s", (product_id,))
        for _, row in forecast_df.iterrows():
            val = float(row['predicted_demand'])
            if pd.isna(val) or val == float('inf'): val = 0.0
            
            sql = """INSERT INTO forecasts (product_id, forecast_date, avg_daily_demand, predicted_demand, model_type) VALUES (%s, %s, %s, %s, 'SARIMA')"""
            cursor.execute(sql, (int(product_id), row['forecast_date'].strftime('%Y-%m-%d'), float(hist_avg), val))
        conn.commit()
        cursor.close()
        
        week1_demand = float(forecast_df.head(7)['predicted_demand'].sum())
        month_demand = float(forecast_df['predicted_demand'].sum())
        
        calculate_reorder_suggestion(product_id, week1_demand, month_demand, conn)
        return True

    except Exception as e:
        print(f"Fatal error forecasting for Product ID {product_id}: {e}")
        return False
    finally:
        if conn: conn.close()


# REORDER ENGINE

def calculate_reorder_suggestion(product_id, week1_demand, month_demand, conn):
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch Real Physical Stock
        cursor.execute("SELECT IFNULL(SUM(quantity_change), 0) as stock FROM inventory_ledger WHERE product_id = %s", (int(product_id),))
        stock_res = cursor.fetchone()
        available_stock = float(stock_res['stock']) if stock_res else 0.0
        
        # 2. Fetch User's Static Reorder Threshold
        cursor.execute("SELECT IFNULL(reorder_threshold, 10) as thresh FROM products WHERE product_id = %s", (int(product_id),))
        thresh_res = cursor.fetchone()
        static_threshold = float(thresh_res['thresh']) if thresh_res else 10.0
        
        # 3. Calculate AI Targets
        safety_stock = float(week1_demand) * 0.20
        ai_required_stock = float(week1_demand) + safety_stock
        target_inventory = float(month_demand) + safety_stock
        
        # Trigger Condition
        trigger_point = max(ai_required_stock, static_threshold)
        
        reorder_qty = 0
        if available_stock <= trigger_point:
            raw_reorder = target_inventory - available_stock
            min_order = static_threshold * 2
            if raw_reorder < min_order:
                raw_reorder = min_order
                
            reorder_qty = int(raw_reorder) + (1 if raw_reorder % 1 > 0 else 0)

        # 4. Reorder Database Update
        current_time = datetime.datetime.now()
        
        cursor.execute("DELETE FROM reorder_suggestions WHERE product_id = %s", (int(product_id),))
        
        if reorder_qty > 0:
            sql = "INSERT INTO reorder_suggestions (product_id, recommended_quantity, generated_date, status) VALUES (%s, %s, %s, 'PENDING')"
            cursor.execute(sql, (int(product_id), reorder_qty, current_time))
            
        conn.commit()
        cursor.close()
        
    except Exception as e:
        print(f"Engine DB Error on Product {product_id}: {e}")
        if conn: conn.rollback()

def run_full_analysis():
    print("🚀 Starting Stockwise ML Engine...")
    conn = get_db_connection()
    if not conn: return
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT product_id, name FROM products WHERE is_active = 1")
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    
    count = 0
    for p in products:
        success = generate_weekly_forecast(p['product_id'])
        if success: count += 1
        
    print(f"✅ Analysis Complete. System updated for {count} active products.")

if __name__ == "__main__":
    run_full_analysis()