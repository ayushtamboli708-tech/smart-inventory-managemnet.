import streamlit as st
import pandas as pd
import mysql.connector # 🔴 RESTORED: Native MySQL
from mysql.connector import Error
import datetime
import time

#  DATABASE CONNECTION 
def get_db_connection():
    try:
        # ☁️ Connects securely using Streamlit Secrets
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
# POP-UP DIALOGS
# 
@st.dialog("🛒 Quick Add to Purchase")
def show_reorder_dialog(ro_data):
    st.markdown(f"### {ro_data['product']}")
    st.info(f"**ML Suggested Quantity:** {ro_data['suggested_qty']} units")
    
    st.write("Add this item to your Purchase Cart. You can adjust the quantity and cost below.")
    
    default_cost = float(ro_data.get('selling_price', 0)) * 0.70
    
    adj_qty = st.number_input("Order Quantity", min_value=1, value=int(ro_data['suggested_qty']), step=1)
    cost_price = st.number_input("Unit Cost Price (₹)", min_value=0.0, value=default_cost, step=1.0)
    
    if st.button("Add to Purchase Cart", type="primary", use_container_width=True):
        if 'current_purchase_items' not in st.session_state:
            st.session_state.current_purchase_items = []
        
        st.session_state.current_purchase_items.append({
            "product_id": ro_data['product_id'],
            "name": ro_data['product'],
            "cost_price": cost_price,
            "price": cost_price, 
            "quantity": adj_qty,
            "total": cost_price * adj_qty
        })
        
        st.session_state.show_new_purchase_form = True
        
        st.success("✅ Added to Cart! Navigate to 'Purchases' to complete.")
        time.sleep(1.5)
        st.rerun()

@st.dialog("📋 Alert Details", width="large")
def show_kpi_details(title, data_list, col_mapping):
    st.markdown(f"### {title}")
    
    if not data_list:
        st.success("No items in this category. Everything looks great!")
    else:
        df = pd.DataFrame(data_list)
        display_df = df[list(col_mapping.keys())].rename(columns=col_mapping)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
    if st.button("Close", use_container_width=True):
        st.rerun()

# 
# ALERT PAGE FUNCTION
# 
def show_alert_page():
    # --- CSS STYLING ---
    st.markdown("""
    <style>
        .page-header { font-size: 24px; font-weight: 700; color: #111827; display: flex; flex-direction: column; }
        .page-sub { font-size: 14px; color: #6B7280; font-weight: 400; margin-top: -5px; margin-bottom: 20px;}
        .dashboard-card { background-color: #FFFFFF !important; border: 1px solid #E5E7EB; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 5px;}
        .custom-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
        .custom-table th { font-size: 13px; color: #6B7280; background-color: #F9FAFB; padding: 12px 15px; text-align: left; border-bottom: 1px solid #E5E7EB; font-weight: 600; text-transform: uppercase;}
        .custom-table td { font-size: 14px; color: #111827; padding: 12px 15px; border-bottom: 1px solid #E5E7EB; font-weight: 500;}
        .sev-high { background-color: #FEE2E2; color: #991B1B; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;}
        .sev-med { background-color: #FEF3C7; color: #92400E; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;}
        .sev-low { background-color: #DBEAFE; color: #1E3A8A; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;}
        .kpi-num { font-size: 28px; font-weight: 700; color: #111827; margin-top: 5px; margin-bottom: 0px; }
        .kpi-label { font-size: 13px; color: #6B7280; font-weight: 500; text-transform: uppercase; }
        .section-title { font-size: 18px; font-weight: 600; color: #374151; margin: 20px 0 10px 0; border-bottom: 2px solid #E5E7EB; padding-bottom: 8px;}
    </style>
    """, unsafe_allow_html=True)

    if 'alerts_muted' not in st.session_state:
        st.session_state.alerts_muted = False

    # 
    #  2️TOP SECTION & HEADER
    # 
    top_col1, top_col2 = st.columns([4, 1])
    with top_col1:
        st.markdown("<div class='page-header'>Alerts & Notifications<div class='page-sub'>Monitor inventory issues and stock risks</div></div>", unsafe_allow_html=True)
    with top_col2:
        if st.button("✔️ Mark All as Read", use_container_width=True):
            st.session_state.alerts_muted = True
            st.toast("Alerts silenced for this session.", icon="✅")
            st.rerun()

    # 
    #  FETCH EXACT DATA FROM DB
    # 
    conn = get_db_connection()
    low_stock_data = []
    reorder_data = []
    overstock_data = []
    
    out_of_stock_count = 0

    if conn:
        # 🔴 RESTORED: MySQL dictionary cursor
        cursor = conn.cursor(dictionary=True)
        
        stock_query = """
            SELECT p.product_id, p.sku, p.name, p.selling_price, IFNULL(p.reorder_threshold, 10) as reorder_lvl,
                   IFNULL(SUM(il.quantity_change), 0) as current_stock
            FROM products p
            LEFT JOIN inventory_ledger il ON p.product_id = il.product_id
            WHERE p.is_active = 1
            GROUP BY p.product_id, p.sku, p.name, p.selling_price, p.reorder_threshold
        """
        cursor.execute(stock_query)
        inventory_items = cursor.fetchall()
        
        reorder_query = """
            SELECT rs.product_id, p.name, p.sku, p.selling_price, rs.recommended_quantity
            FROM reorder_suggestions rs
            JOIN products p ON rs.product_id = p.product_id
            WHERE rs.status = 'PENDING' AND p.is_active = 1
        """
        cursor.execute(reorder_query)
        ml_reorders = cursor.fetchall()
        
        cursor.close()
        conn.close()

        # Process Low Stock & Overstock
        for item in inventory_items:
            stock = float(item['current_stock'])
            reorder_lvl = float(item['reorder_lvl'])
            
            if stock <= reorder_lvl:
                severity = "🔴 HIGH" if stock <= 0 else "🟡 MEDIUM"
                sev_class = "sev-high" if stock <= 0 else "sev-med"
                msg = "Out of stock!" if stock <= 0 else "Stock critically low"
                
                if stock <= 0: out_of_stock_count += 1
                
                low_stock_data.append({
                    "product": f"{item['name']} ({item['sku']})",
                    "stock": stock,
                    "reorder_level": reorder_lvl,
                    "message": msg,
                    "severity_html": f"<span class='{sev_class}'>{severity}</span>"
                })

            if stock > (reorder_lvl * 5) and stock > 50:
                value_locked = stock * float(item['selling_price'] if item['selling_price'] else 0)
                overstock_data.append({
                    "product": item['name'],
                    "days_of_stock": "Overstocked",
                    "value_locked": value_locked,
                    "severity_html": "<span class='sev-low'>🔵 LOW</span>"
                })

        # Process ML Reorders directly from DB (Action column data removed)
        for ro in ml_reorders:
            reorder_data.append({
                "product_id": ro['product_id'],
                "sku": ro['sku'],
                "product": ro['name'],
                "selling_price": float(ro['selling_price'] if ro['selling_price'] else 0),
                "suggested_qty": int(ro['recommended_quantity']),
                "vendor": "Primary Supplier"
            })

    if not st.session_state.alerts_muted and out_of_stock_count > 0:
        st.toast(f"🚨 CRITICAL: {out_of_stock_count} items are completely OUT OF STOCK!", icon="⚠️")

    # 
    # 8️⃣ ALERT KPI CARDS
    # 
    k1, k2, k3 = st.columns(3)
    
    with k1:
        st.markdown(f"<div class='dashboard-card' style='border-left: 4px solid #EF4444;'><div class='kpi-label'>Low Stock Items</div><div class='kpi-num'>{len(low_stock_data)}</div></div>", unsafe_allow_html=True)
        if st.button("🔍", key="btn_ls", help="View Low Stock Details"):
            show_kpi_details("📉 Low Stock Products", low_stock_data, {"product": "Product", "stock": "Current Stock", "reorder_level": "Threshold", "message": "Issue"})
            
    with k2:
        st.markdown(f"<div class='dashboard-card' style='border-left: 4px solid #F59E0B;'><div class='kpi-label'>ML Reorder Required</div><div class='kpi-num'>{len(reorder_data)}</div></div>", unsafe_allow_html=True)
        if st.button("🔍", key="btn_ro", help="View Reorder Suggestions"):
            show_kpi_details("🛒 Reorder Suggestions", reorder_data, {"product": "Product", "suggested_qty": "Suggested Order (Units)", "vendor": "Vendor"})

    with k3:
        st.markdown(f"<div class='dashboard-card' style='border-left: 4px solid #3B82F6;'><div class='kpi-label'>Overstock Items</div><div class='kpi-num'>{len(overstock_data)}</div></div>", unsafe_allow_html=True)
        if st.button("🔍", key="btn_os", help="View Overstock Details"):
            show_kpi_details("📦 Overstock Items", overstock_data, {"product": "Product", "days_of_stock": "Status", "value_locked": "Value Locked (₹)"})

    # 
    # 4️⃣ FILTERS
    # 
    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    f_col1, f_col2, f_col3 = st.columns([1, 1, 2])
    with f_col1:
        alert_filter = st.selectbox("Alert Type", ["All Alerts", "Low Stock", "Reorder Required", "Overstock"])
    with f_col2:
        sev_filter = st.selectbox("Severity", ["All", "High", "Medium", "Low"])
    
    st.write("---")

    # 
    # DYNAMIC ALERT TABLES RENDERING
    # 

    if alert_filter == "All Alerts" and not low_stock_data and not reorder_data and not overstock_data:
        st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
        st.success("🎉 **Fantastic!** You have zero active alerts. Your inventory is perfectly optimized.")

    # --- TABLE 1: LOW STOCK ALERTS ---
    if alert_filter == "Low Stock" or (alert_filter == "All Alerts" and low_stock_data):
        st.markdown("<div class='section-title'>📉 Low Stock Alerts</div>", unsafe_allow_html=True)
        if low_stock_data:
            ls_html = "<div class='dashboard-card' style='padding:0;'><table class='custom-table'><thead><tr><th>Product</th><th>Current Stock</th><th>Reorder Level</th><th>Message</th><th>Severity</th></tr></thead><tbody>"
            for row in low_stock_data:
                if sev_filter == "High" and "HIGH" not in row['severity_html']: continue
                if sev_filter == "Medium" and "MEDIUM" not in row['severity_html']: continue
                
                stock_color = "#EF4444" if row['stock'] <= 0 else "#F59E0B"
                ls_html += f"<tr><td style='font-weight:600;'>{row['product']}</td><td style='color:{stock_color}; font-weight:bold;'>{int(row['stock'])}</td><td>{int(row['reorder_level'])}</td><td>{row['message']}</td><td>{row['severity_html']}</td></tr>"
            ls_html += "</tbody></table></div>"
            st.markdown(ls_html, unsafe_allow_html=True)
        else:
            st.success("✅ No low stock alerts! Your inventory is healthy.")

    # --- TABLE 2: REORDER SUGGESTIONS ---
    if alert_filter == "Reorder Required" or (alert_filter == "All Alerts" and reorder_data):
        st.markdown("<div class='section-title'>🛒 ML Reorder Suggestions</div>", unsafe_allow_html=True)
        if reorder_data:
            ro_html = "<div class='dashboard-card' style='padding:0;'><table class='custom-table'><thead><tr><th>Product</th><th>Suggested Order</th><th>Vendor</th></tr></thead><tbody>"
            for row in reorder_data:
                ro_html += f"<tr><td style='font-weight:600;'>{row['product']}</td><td><span style='background-color:#F3F4F6; padding: 4px 8px; border-radius:4px; font-weight:600;'>{row['suggested_qty']} units</span></td><td>{row['vendor']}</td></tr>"
            ro_html += "</tbody></table></div>"
            st.markdown(ro_html, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            with st.container(border=True):
                st.write("⚙️ **Reorder Actions**")
                act_col1, act_col2 = st.columns([3, 1])
                
                reorder_dict = {f"{r['product']} ({r['sku']}) - {r['suggested_qty']} units": r for r in reorder_data}
                
                with act_col1:
                    selected_ro = st.selectbox("Select a product to reorder:", options=["Select Product..."] + list(reorder_dict.keys()), label_visibility="collapsed")
                
                with act_col2:
                    if selected_ro != "Select Product...":
                        if st.button("🛒 Draft Purchase Order", use_container_width=True, type="primary"):
                            show_reorder_dialog(reorder_dict[selected_ro])
        else:
            st.info("No reorder suggestions at this time.")

    # --- TABLE 3: OVERSTOCK WARNINGS ---
    if alert_filter == "Overstock" or (alert_filter == "All Alerts" and overstock_data):
        st.markdown("<div class='section-title'>📦 Overstock Warnings</div>", unsafe_allow_html=True)
        if overstock_data:
            os_html = "<div class='dashboard-card' style='padding:0;'><table class='custom-table'><thead><tr><th>Product</th><th>Status</th><th>Value Locked</th><th>Severity</th></tr></thead><tbody>"
            for row in overstock_data:
                if sev_filter in ["High", "Medium"]: continue 
                
                os_html += f"<tr><td style='font-weight:600;'>{row['product']}</td><td>{row['days_of_stock']}</td><td style='color:#374151; font-weight:600;'>₹{row['value_locked']:,.2f}</td><td>{row['severity_html']}</td></tr>"
            os_html += "</tbody></table></div>"
            st.markdown(os_html, unsafe_allow_html=True)
        else:
            st.info("No overstock warnings. Capital efficiency is looking good!")