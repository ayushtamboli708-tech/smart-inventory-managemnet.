import streamlit as st
import pandas as pd
import mysql.connector 
from mysql.connector import Error
import datetime

# =========================================
# 🔌 DATABASE CONNECTION HELPER
# =========================================
def get_db_connection():
    try:
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

# =========================================
# 🛒 NEW POP-UP MODAL (CURES THE SQUISH GLITCH)
# =========================================
@st.dialog("🛒 Create New Sale", width="large")
def create_sale_dialog():
    conn = get_db_connection()
    product_dict = {}
    if conn:
        cursor = conn.cursor(dictionary=True) 
        cursor.execute("SELECT product_id, sku, name, selling_price FROM products WHERE is_active = 1")
        for row in cursor.fetchall():
            label = f"{row['name']} ({row['sku']})"
            product_dict[label] = row
        cursor.close()
        conn.close()

    c1, c2, c3 = st.columns([4, 2, 2])
    with c1: sel_prod = st.selectbox("Product", ["Select..."] + list(product_dict.keys()))
    with c2: qty = st.number_input("Qty", 1, step=1)
    with c3:
        st.write("")
        st.write("") 
        if st.button("➕ Add Item", use_container_width=True):
            if sel_prod != "Select...":
                info = product_dict[sel_prod]
                st.session_state.current_sale_items.append({
                    "product_id": info['product_id'], "name": info['name'],
                    "price": float(info['selling_price']), "quantity": qty,
                    "total": float(info['selling_price']) * qty
                })
                st.rerun()

    # Cart Display
    if st.session_state.current_sale_items:
        st.write("---")
        cart_html = "<table class='custom-table'><thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead><tbody>"
        grand_total = 0
        for i in st.session_state.current_sale_items:
            grand_total += i['total']
            cart_html += f"<tr><td>{i['name']}</td><td>{i['quantity']}</td><td>₹{i['price']}</td><td>₹{i['total']}</td></tr>"
        cart_html += "</tbody></table>"
        st.markdown(cart_html, unsafe_allow_html=True)
        st.markdown(f"**Total: ₹{grand_total:,.2f}**")

        st.write("")
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("💾 Complete Sale", type="primary", use_container_width=True):
                conn = get_db_connection()
                if conn:
                    try:
                        cur = conn.cursor()
                        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        cur.execute("INSERT INTO sales (sale_date, total_amount) VALUES (%s, %s)", (now, grand_total))
                        sid = cur.lastrowid
                        
                        for x in st.session_state.current_sale_items:
                            # Using unit_price for the database schema match
                            cur.execute("INSERT INTO sale_items (sale_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)", 
                                        (sid, x['product_id'], x['quantity'], x['price']))
                            cur.execute("INSERT INTO inventory_ledger (product_id, transaction_type, reference_id, quantity_change, transaction_date) VALUES (%s, 'SALE', %s, %s, %s)", 
                                        (x['product_id'], sid, -x['quantity'], now))
                                        
                        conn.commit()
                        
                        st.session_state.toast_msg = "✅ Sale Completed Successfully!"
                        st.session_state.current_sale_items = []
                        st.rerun() # This safely closes the dialog!
                    except Exception as e: 
                        st.error(e)
                        conn.rollback()
                    finally: 
                        cur.close()
                        conn.close()
        with col_btn2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.current_sale_items = []
                st.rerun()

# =========================================
# MAIN SALES PAGE FUNCTION
# =========================================
def show_sales_page():
    # --- CSS STYLING ---
    st.markdown("""
    <style>
        .page-header { font-size: 24px; font-weight: 700; color: #111827; }
        .dashboard-card { background-color: #FFFFFF !important; border: 1px solid #E5E7EB; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 20px;}
        .custom-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
        .custom-table th { font-size: 13px; color: #6B7280; background-color: #F9FAFB; padding: 12px 15px; text-align: left; border-bottom: 1px solid #E5E7EB; font-weight: 600; text-transform: uppercase;}
        .custom-table td { font-size: 14px; color: #111827; padding: 12px 15px; border-bottom: 1px solid #E5E7EB; font-weight: 500;}
        .status-completed { background-color: #D1FAE5; color: #065F46; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;}
        .kpi-num { font-size: 24px; font-weight: 700; color: #111827; margin-top: 5px; margin-bottom: 0px; }
        .kpi-label { font-size: 13px; color: #6B7280; font-weight: 500; text-transform: uppercase; }
        .stTextInput input, .stNumberInput input { border-radius: 6px; border: 1px solid #E5E7EB; }
    </style>
    """, unsafe_allow_html=True)

    # --- STATE MANAGEMENT ---
    if 'current_sale_items' not in st.session_state:
        st.session_state.current_sale_items = []

    # Fire notifications safely on reload
    if 'toast_msg' in st.session_state:
        st.toast(st.session_state.toast_msg)
        del st.session_state.toast_msg

    # =========================================
    # HEADER
    # =========================================
    c1, c2 = st.columns([4, 1])
    with c1: st.markdown("<div class='page-header'>Sales</div>", unsafe_allow_html=True)
    with c2:
        # 🔴 OPENS THE NEW BEAUTIFUL MODAL
        if st.button("➕ New Sale", type="primary", use_container_width=True):
            create_sale_dialog()

    # =========================================
    # SEARCH & FILTER
    # =========================================
    st.write("---")
    c1, c2 = st.columns([3, 1])
    with c1:
        search_term = st.text_input("Search", placeholder="🔍 Search Sale ID (e.g. 10) or Product Name (e.g. Milk)", label_visibility="collapsed")
    with c2:
        date_filter = st.selectbox("Date", ["All Time", "Today", "Last 7 Days"], label_visibility="collapsed")

    # =========================================
    # SALES TABLE
    # =========================================
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT s.sale_id, s.sale_date, s.total_amount, COUNT(si.id) as items_count
            FROM sales s
            LEFT JOIN sale_items si ON s.sale_id = si.sale_id
            LEFT JOIN products p ON si.product_id = p.product_id
            WHERE 1=1
        """
        params = []

        if search_term:
            term = f"%{search_term}%"
            query += " AND (s.sale_id LIKE %s OR p.name LIKE %s)"
            params.extend([term, term])

        # 🔴 FIXED TIMEZONE ISSUE: We explicitly send your computer's "Today" date
        today_date = datetime.date.today()
        if date_filter == "Today":
            query += " AND DATE(s.sale_date) = %s"
            params.append(today_date)
        elif date_filter == "Last 7 Days":
            query += " AND s.sale_date >= %s"
            params.append(today_date - datetime.timedelta(days=7))

        # 🔴 FIXED THE PARADOX: We sort by ID, completely ignoring the fake time generations
        query += " GROUP BY s.sale_id, s.sale_date, s.total_amount ORDER BY s.sale_id DESC"

        cursor.execute(query, tuple(params))
        sales = cursor.fetchall()
        
        if sales:
            html = "<div class='dashboard-card' style='padding:0'><table class='custom-table'><thead><tr><th>ID</th><th>Date</th><th>Items</th><th>Total</th><th>Status</th></tr></thead><tbody>"
            for s in sales:
                raw_date = s['sale_date']
                try:
                    dt_obj = pd.to_datetime(raw_date)
                    date_str = dt_obj.strftime("%d %b %Y, %I:%M %p")
                except:
                    date_str = str(raw_date)
                    
                html += f"<tr><td style='color:#3B82F6; font-weight:600;'>SALE-{s['sale_id']}</td><td>{date_str}</td><td>{s['items_count']}</td><td>₹{float(s['total_amount']):,.2f}</td><td><span class='status-completed'>Completed</span></td></tr>"
            html += "</tbody></table></div>"
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.info("No sales found.")

        # =========================================
        # SUMMARY
        # =========================================
        st.write("---")
        total_rev = sum(float(x['total_amount'] or 0) for x in sales)
        c1, c2 = st.columns(2)
        c1.metric("Total Revenue", f"₹{total_rev:,.2f}")
        c2.metric("Total Transactions", len(sales))
        
        cursor.close()
        conn.close()