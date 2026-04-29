import streamlit as st

st.set_page_config(page_title="Stockwise", layout="wide", initial_sidebar_state="expanded", page_icon="📦")

import pandas as pd
import plotly.express as px
import mysql.connector
from mysql.connector import Error, IntegrityError
import os
import time

# --- IMPORT FUNCTIONS ---
def get_engine():
    try:
        from forecast.forecasting_engine import get_dashboard_summary, run_full_analysis
        return get_dashboard_summary, run_full_analysis
    except ImportError:
        st.error("Forecasting Engine not found.")
        return None, None

# 
# (AUTHENTICATION CHECK)
# 
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.role = None
    st.session_state.user_name = None

if not st.session_state.authenticated:
    # If they aren't logged in, show ONLY the login screen and STOP rendering everything else.
    from ui.login_page import show_login_screen
    show_login_screen()
    st.stop() 

# 
#  DB CONNECTION
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
        st.error(f"Database Connection Failed: {e}")
        return None

# 
#  ADMIN SETTINGS DIALOG (OWNER ONLY)
# 
@st.dialog("⚙️ Admin Settings: User Management", width="large")
def show_admin_settings():
    st.markdown("### 👑 Manage Owners")
    st.write("Add a new Owner account below. Owners have full delete privileges and can see this menu.")
    
    with st.form("add_owner_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("New Username*", placeholder="e.g. manager_jane")
        with col2:
            new_password = st.text_input("New Password*", type="password")
            
        if st.form_submit_button("➕ Create Owner Account", type="primary", use_container_width=True):
            if not new_username or not new_password:
                st.error("Username and Password are required.")
            else:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute(
                            "INSERT INTO users (username, password, role) VALUES (%s, %s, 'Owner')",
                            (new_username, new_password)
                        )
                        conn.commit()
                        st.success(f"Successfully created new Owner account: {new_username}")
                        time.sleep(1.5)
                        st.rerun()
                    except IntegrityError:
                        st.error("That username already exists! Please choose another.")
                    except Error as e:
                        st.error(f"Database Error: {e}")
                    finally:
                        cursor.close()
                        conn.close()

    st.write("---")
    st.markdown("### 📋 Current Owners")
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username FROM users WHERE role = 'Owner'")
        owners = cursor.fetchall()
        
        if owners:
            for owner in owners:
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"<div style='padding-top:8px; font-weight:600;'>👤 {owner['username']}</div>", unsafe_allow_html=True)
                with c2:
                    # Security logic: Prevent users from deleting themselves!
                    is_current_user = (owner['username'] == st.session_state.user_name)
                    
                    if st.button("🗑️ Remove", key=f"del_user_{owner['user_id']}", disabled=is_current_user, use_container_width=True):
                        try:
                            cursor.execute("DELETE FROM users WHERE user_id = %s", (owner['user_id'],))
                            conn.commit()
                            st.success(f"Removed owner {owner['username']}")
                            time.sleep(1)
                            st.rerun()
                        except Error as e:
                            st.error(f"Could not delete: {e}")
                            conn.rollback()

        cursor.close()
        conn.close()

# 
#  CSS STYLING
# 
st.markdown("""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" />
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    .stApp { font-family: 'Inter', sans-serif; background-color: #F8FAFC; color: #1F2937; }

    /* SIDEBAR */
    [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E5E7EB; }
    [data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child { display: none !important; }
    [data-testid="stRadio"] > div[role="radiogroup"] > label {
        background-color: transparent; color: #4B5563 !important; padding: 12px 15px !important;
        border-radius: 8px !important; border: 1px solid transparent; transition: all 0.2s; margin-bottom: 4px; display: block;
    }
    [data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
        background-color: #F3F4F6 !important; color: #111827 !important; transform: translateX(5px);
    }
    
    /* DASHBOARD CARDS */
    .dashboard-card { 
        background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 20px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05); transition: all 0.3s ease; height: 100%;
    }
    .dashboard-card:hover { transform: translateY(-4px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); border-color: #BFDBFE; }
    
    .kpi-val { font-size: 28px; font-weight: 700; color: #111827; margin-top: 5px; }
    .kpi-lbl { font-size: 13px; font-weight: 600; text-transform: uppercase; color: #6B7280; }

    /* FLOATING BUTTON */
    .st-key-fab_main { position: fixed; bottom: 40px; right: 40px; z-index: 9999; }
    .st-key-fab_main button {
        background-color: #2563EB; color: white; border-radius: 30px; height: 60px; width: 60px; border: none;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4); display: flex; align-items: center; justify-content: center;
    }
    .st-key-fab_main button span { display: none; }
    .st-key-fab_main button::before { content: "analytics"; font-family: 'Material Symbols Rounded'; font-size: 28px; color: white; }
    .st-key-fab_main button:hover { width: 150px; justify-content: flex-start; padding-left: 20px; }
    .st-key-fab_main button:hover::after { content: "Forecast"; font-family: 'Inter'; font-weight: 600; margin-left: 10px; white-space: nowrap;}

    .section-title { font-size: 16px; font-weight: 700; color: #111827; margin: 25px 0 15px 0; }
    .custom-table { width: 100%; border-collapse: collapse; }
    .custom-table th { background: #F8FAFC; padding: 12px; text-align: left; color: #64748B; border-bottom: 1px solid #E2E8F0; }
    .custom-table td { padding: 12px; border-bottom: 1px solid #F1F5F9; font-size: 13px; }
    .search-result { background: #EFF6FF; border: 1px solid #BFDBFE; padding: 20px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.1); }
</style>
""", unsafe_allow_html=True)

# 
#  KPI POP-UP
# 
@st.dialog("📊 Inventory Details", width="large")
def show_kpi_details(kpi_type):
    conn = get_db_connection()
    if not conn: return
    
    st.markdown(f"### {kpi_type}")
    query = ""
    
    if kpi_type == "Low Stock":
        query = "SELECT name, sku, category, IFNULL(reorder_threshold, 10) as threshold, (SELECT IFNULL(SUM(quantity_change), 0) FROM inventory_ledger il WHERE il.product_id = p.product_id) as stock FROM products p WHERE is_active = 1 HAVING stock <= threshold AND stock > 0"
    elif kpi_type == "Out of Stock":
        query = "SELECT name, sku, category, (SELECT IFNULL(SUM(quantity_change), 0) FROM inventory_ledger il WHERE il.product_id = p.product_id) as stock FROM products p WHERE is_active = 1 HAVING stock <= 0"
    elif kpi_type == "Active Products":
        query = "SELECT name, sku, category, selling_price FROM products WHERE is_active = 1"
    elif kpi_type == "Reorder Needed":
        query = "SELECT name, sku, category, IFNULL(reorder_threshold, 10) as threshold, (SELECT IFNULL(SUM(quantity_change), 0) FROM inventory_ledger il WHERE il.product_id = p.product_id) as stock FROM products p WHERE is_active = 1 HAVING stock <= threshold"
    
    if query:
        try:
            df = pd.read_sql(query, conn)
            if not df.empty: 
                if 'stock' in df.columns: df['stock'] = df['stock'].astype(int)
                if 'threshold' in df.columns: df['threshold'] = df['threshold'].astype(int)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else: 
                st.info("No items found.")
        except Exception as e:
            st.error(f"Error loading data: {e}")
    conn.close()

# 
#  FORECASTING POP-UP 
# 
@st.dialog("🔮 ML Demand Forecast", width="large")
def show_forecast_dialog():
    h_col1, h_col2 = st.columns([3, 1])
    with h_col1: st.markdown("### Next 7 Days Demand")
    with h_col2:
        if st.button("🔄 Recalculate ML", use_container_width=True, type="primary"):
            with st.spinner("ML is analyzing sales and stock..."):
                _, run_full_analysis = get_engine()
                if run_full_analysis: run_full_analysis()
            st.rerun()

    search = st.text_input("Filter", placeholder="Search by Name or SKU...", label_visibility="collapsed")
    
    conn = get_db_connection()
    if conn:
        q = """SELECT 
                p.product_id, p.name, p.sku, p.selling_price, 
                COALESCE(SUM(f.predicted_demand), 0) as demand, 
                COALESCE(MAX(rs.recommended_quantity), 0) as qty,
                (SELECT IFNULL(SUM(quantity_change), 0) FROM inventory_ledger WHERE product_id = p.product_id) as current_stock
               FROM products p 
               LEFT JOIN forecasts f ON p.product_id=f.product_id AND f.forecast_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY) 
               LEFT JOIN reorder_suggestions rs ON p.product_id=rs.product_id AND rs.status='PENDING' 
               WHERE p.is_active=1 
               GROUP BY p.product_id 
               ORDER BY qty DESC"""
        cursor = conn.cursor(dictionary=True)
        cursor.execute(q)
        data = cursor.fetchall()
        conn.close()
        
        if search: 
            s = search.lower()
            data = [d for d in data if s in d['name'].lower() or s in d['sku'].lower()]
        
        h1, h2, h3, h4 = st.columns([3, 2, 2, 2])
        h1.caption("PRODUCT & SHELF STOCK")
        h2.caption("DEMAND (7D)")
        h3.caption("REORDER QTY(Monthly)")
        h4.caption("ACTION")
        st.divider()
        
        for r in data:
            qty = int(r['qty'])
            color = "#EF4444" if qty > 20 else "#F59E0B" if qty > 0 else "#10B981"
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            
            c1.markdown(f"**{r['name']}**<br><span style='font-size:12px; color:#6B7280;'>Physical Shelf: <b>{int(r['current_stock'])}</b></span>", unsafe_allow_html=True)
            c2.markdown(f"<div style='padding-top:10px;'>{int(r['demand'])}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div style='padding-top:10px;'><span style='color:{color}; font-weight:bold'>{qty}</span></div>", unsafe_allow_html=True)
            
            if qty > 0:
                with c4:
                    st.write("")
                    if st.button("Add 🛒", key=f"cart_{r['product_id']}"):
                        if 'current_purchase_items' not in st.session_state: st.session_state.current_purchase_items = []
                        price = float(r['selling_price']) if r['selling_price'] else 0.0
                        st.session_state.current_purchase_items.append({
                            "product_id": r['product_id'], "name": r['name'], "cost_price": price, "quantity": qty, "total": price * qty
                        })
                        st.session_state.nav_selection = "Purchases"
                        st.session_state.show_new_purchase_form = True
                        st.rerun()
            st.divider()

# 
#  SIDEBAR
# 
with st.sidebar:
    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    
    st.markdown(f"""
        <div style="padding-bottom: 30px; padding-left: 10px;">
            <span style="font-size: 24px; font-weight: 700; color: #111827; letter-spacing: -0.5px;">Stockwise</span>
        </div>
    """, unsafe_allow_html=True)
    
    menu = {"Dashboard":"Dashboard", "Alerts":"Alerts", "Sales":"Sales", "Products":"Products", "Purchases":"Purchases"}
    if "nav_selection" not in st.session_state: st.session_state.nav_selection = "Dashboard"
    
    sel = st.radio("Nav", list(menu.keys()), index=list(menu.keys()).index(st.session_state.nav_selection), label_visibility="collapsed")
    if sel != st.session_state.nav_selection: st.session_state.nav_selection = sel; st.rerun()

    st.markdown("<div style='min-height: 45vh;'></div>", unsafe_allow_html=True)
    st.write("---")
    
    #  OWNER SETTINGS
    if st.session_state.role == "Owner":
        if st.button("⚙️ Admin Settings", use_container_width=True):
            show_admin_settings()
            
    # LOGOUT BUTTON 
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.role = None
        st.session_state.user_name = None
        st.rerun()

# 
#  HEADER
# 
c1, c2 = st.columns([4, 1])
with c1: 
    st.markdown(f"<h2 style='margin:0; padding-top: 5px;'>{st.session_state.nav_selection}</h2>", unsafe_allow_html=True)
with c2: 
    role_badge = "👑 Owner" if st.session_state.role == "Owner" else "🧑‍💼 Staff"
    st.markdown(f"<div style='text-align:right; font-weight:600; padding-top:10px;'>{role_badge} | {st.session_state.user_name}</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 
#  DASHBOARD PAGE
# 
if st.session_state.nav_selection == "Dashboard":
    
    dashboard_search = st.text_input("S", placeholder="🔍 Search any product...", label_visibility="collapsed")
    
    if dashboard_search:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            search_query = """
                SELECT p.name, p.sku, p.category, p.selling_price, 
                (SELECT IFNULL(SUM(quantity_change), 0) FROM inventory_ledger il WHERE il.product_id = p.product_id) as stock
                FROM products p
                WHERE p.name LIKE %s OR p.sku LIKE %s LIMIT 1
            """
            cursor.execute(search_query, (f"%{dashboard_search}%", f"%{dashboard_search}%"))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                st.markdown(f"""
                <div class='search-result'>
                    <h4 style='margin:0 0 10px 0;'>🔍 Quick Result: {result['name']}</h4>
                    <div style='display:flex; gap: 30px;'>
                        <div><b>SKU:</b> {result['sku']}</div>
                        <div><b>Category:</b> {result['category']}</div>
                        <div><b>Price:</b> ₹{result['selling_price']}</div>
                        <div><b>Current Stock:</b> <span style='color: {"#10B981" if result['stock'] > 10 else "#EF4444"}; font-weight:bold; font-size:16px;'>{int(result['stock'])}</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning(f"No product found matching '{dashboard_search}'")
        st.write("---")

    try:
        from forecast.forecasting_engine import get_dashboard_summary
        data = get_dashboard_summary()
    except ImportError:
        data = {"kpi": {"active": 0, "all": 0, "low": 0, "out": 0, "reorder": 0}, "health": {"score": 100, "qty_hand": 0, "po_value": 0}, "top_selling": pd.DataFrame(), "alerts": pd.DataFrame(), "forecast_preview": pd.DataFrame()}

    kpi, health, alerts, charts, forecast_df = data['kpi'], data['health'], data['alerts'], data['top_selling'], data['forecast_preview']

    # 1. KPI CARDS
    k1, k2, k3, k4 = st.columns(4)
    def render_kpi(col, title, val, color, icon, kpi_type):
        with col:
            st.markdown(f"""
            <div class='dashboard-card'>
                <div style='display:flex; justify-content:space-between;'>
                    <div><div class='kpi-lbl'>{title}</div><div class='kpi-val'>{val}</div></div>
                    <div style='font-size:28px;'>{icon}</div>
                </div>
            </div>""", unsafe_allow_html=True)
            if st.button("View List", key=f"btn_{title}", use_container_width=True):
                show_kpi_details(kpi_type)

    render_kpi(k1, "Low Stock", kpi['low'], "#F59E0B", "⚠️", "Low Stock")
    render_kpi(k2, "Out of Stock", kpi['out'], "#EF4444", "❌", "Out of Stock")
    render_kpi(k3, "Active Items", kpi['active'], "#10B981", "📦", "Active Products")
    render_kpi(k4, "Reorder Needed", kpi['reorder'], "#3B82F6", "🛒", "Reorder Needed")

    # 2. CHARTS
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("<div class='section-title'>Inventory Health</div>", unsafe_allow_html=True)
        score = health['score']
        clr = "#10B981" if score > 70 else "#F59E0B"
        st.markdown(f"""<div class='dashboard-card' style='height:280px; display:flex; flex-direction:column; justify-content:center;'>
            <div style='display:flex; justify-content:space-between;'><span>Score</span><span style='font-size:32px; font-weight:bold; color:{clr}'>{score}%</span></div>
            <div style='background:#F3F4F6; height:12px; border-radius:6px; margin:10px 0 30px;'><div style='width:{score}%; background:{clr}; height:100%; border-radius:6px;'></div></div>
            <div style='display:flex; justify-content:space-between; margin-bottom:10px;'><span>Qty on Hand</span><b>{int(health['qty_hand']):,}</b></div>
            <div style='display:flex; justify-content:space-between;'><span>Pending PO</span><b>₹{float(health['po_value']):,.2f}</b></div>
        </div>""", unsafe_allow_html=True)
    with c2:
        h, f = st.columns([2, 1])
        h.markdown("<div class='section-title'>Top Selling</div>", unsafe_allow_html=True)
        time_filter = f.selectbox("Period", ["All Time", "This Month"], label_visibility="collapsed")
        
        conn = get_db_connection()
        if conn and time_filter == "This Month":
            q = """SELECT p.name as Product, SUM(si.quantity) as Sales 
                   FROM sale_items si JOIN sales s ON si.sale_id=s.sale_id 
                   JOIN products p ON si.product_id=p.product_id 
                   WHERE MONTH(s.sale_date) = MONTH(CURDATE()) AND YEAR(s.sale_date) = YEAR(CURDATE())
                   GROUP BY p.product_id ORDER BY Sales DESC LIMIT 5"""
            try: charts = pd.read_sql(q, conn)
            except: pass
            conn.close()

        with st.container(border=True):
            if not charts.empty:
                fig = px.pie(charts, values='Sales', names='Product', hole=0.6, color_discrete_sequence=px.colors.qualitative.Prism)
                fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=230, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No sales data.")

    # 3. BOTTOM ROW
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1.5, 1])
    
    with c1:
        st.markdown("<div class='section-title'>Reorder Suggestions</div>", unsafe_allow_html=True)
        
        display_alerts = alerts
        if dashboard_search and not alerts.empty:
            s_term = dashboard_search.lower()
            display_alerts = alerts[alerts['name'].str.lower().contains(s_term) | alerts['sku'].str.lower().contains(s_term)]

        if not display_alerts.empty:
            st.dataframe(display_alerts[['name', 'sku', 'current_stock', 'reorder_threshold']], use_container_width=True, hide_index=True)
        else:
            st.markdown("<div class='dashboard-card' style='text-align:center; color:#6B7280; padding:40px;'>✅ No urgent reorders.</div>", unsafe_allow_html=True)

    with c2:
        h, f = st.columns([2, 1])
        h.markdown("<div class='section-title'>Demand Forecast</div>", unsafe_allow_html=True)
        conn = get_db_connection()
        opts = ["All Products"]
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT name FROM products WHERE is_active=1")
            opts += [row['name'] for row in cursor.fetchall()]
            conn.close()
        prod_filter = f.selectbox("Filter Product", opts, label_visibility="collapsed")
        
        if prod_filter != "All Products":
            conn = get_db_connection()
            if conn:
                try:
                    q = """SELECT f.forecast_date as Day, f.predicted_demand as 'Expected Sales' 
                           FROM forecasts f JOIN products p ON f.product_id=p.product_id 
                           WHERE p.name=%s AND f.forecast_date >= CURDATE() 
                           ORDER BY f.forecast_date ASC LIMIT 7"""
                    forecast_df = pd.read_sql(q, conn, params=(prod_filter,))
                except: pass
                conn.close()

            with st.container(border=True):
                if not forecast_df.empty:
                    forecast_df = forecast_df.sort_values(by="Day")
                    fig_l = px.line(forecast_df, x="Day", y="Expected Sales", color_discrete_sequence=["#8B5CF6"], markers=True)
                    fig_l.update_layout(margin=dict(t=20,b=20,l=20,r=20), height=240, xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#F3F4F6'))
                    st.plotly_chart(fig_l, use_container_width=True, config={'displayModeBar': False})
                else: st.info("Run forecast engine to see data.")

    # 4. FLOATING BUTTON
    if st.button(" ", key="fab_main", help="AI Forecast"): 
        show_forecast_dialog()

# 
#  PAGE ROUTING
# 
elif st.session_state.nav_selection == "Products":
    from ui.product_page import show_product_page
    show_product_page()
elif st.session_state.nav_selection == "Alerts":
    from ui.alert_page import show_alert_page
    show_alert_page()
elif st.session_state.nav_selection == "Sales":
    from ui.sales_page import show_sales_page
    show_sales_page()
elif st.session_state.nav_selection == "Purchases":
    from ui.purchase_page import show_purchase_page
    show_purchase_page()