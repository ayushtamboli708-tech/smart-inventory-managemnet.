import streamlit as st
import pandas as pd
import mysql.connector 
from mysql.connector import Error
import datetime

# ==========================================
# 🔌 DATABASE CONNECTION (SAFE & STABLE)
# ==========================================
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

# ==========================================
# ⚡ HIGH-SPEED RAM CACHING (INVISIBLE)
# ==========================================
@st.cache_data(ttl=120, show_spinner=False)
def get_cached_vendors():
    conn = get_db_connection()
    res = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT vendor_id, name FROM vendors ORDER BY name ASC")
        res = cursor.fetchall()
        cursor.close()
        conn.close() # 🔴 SAFELY CLOSES CONNECTION
    return res

@st.cache_data(ttl=120, show_spinner=False)
def get_cached_products():
    conn = get_db_connection()
    res = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT product_id, sku, name FROM products WHERE is_active = 1")
        res = cursor.fetchall()
        cursor.close()
        conn.close() # 🔴 SAFELY CLOSES CONNECTION
    return res

# ==========================================
# 🚀 MEMORY-WIPING BACKGROUND CALLBACKS
# ==========================================
def cancel_purchase_callback():
    st.session_state.current_purchase_items = []
    if 'add_v_name' in st.session_state: del st.session_state['add_v_name']
    if 'add_p_label' in st.session_state: del st.session_state['add_p_label']
    if 'po_status' in st.session_state: del st.session_state['po_status']
    st.session_state.add_qty = 1
    st.session_state.add_cost = 0.0

def remove_item_callback(index):
    st.session_state.current_purchase_items.pop(index)

def add_item_callback(vendor_dict, product_dict):
    v_name = st.session_state.add_v_name
    p_label = st.session_state.add_p_label
    qty = st.session_state.add_qty
    cost = st.session_state.add_cost
    
    if v_name == "Select a vendor...":
        st.session_state.static_msg = ("error", "⚠️ Please select a vendor first!")
        return
    if p_label == "Select a product...":
        st.session_state.static_msg = ("error", "⚠️ Please select a product first!")
        return

    prod_info = product_dict[p_label]
    st.session_state.current_purchase_items.append({
        "vendor_id": vendor_dict[v_name],
        "vendor_name": v_name,
        "product_id": prod_info['product_id'],
        "name": prod_info['name'],
        "cost_price": cost,
        "quantity": qty,
        "total": cost * qty
    })
    
    st.session_state.add_p_label = "Select a product..."
    st.session_state.add_qty = 1
    st.session_state.add_cost = 0.0

def save_purchase_callback(po_date, po_status):
    cart = st.session_state.current_purchase_items
    if not cart:
        st.session_state.static_msg = ("warning", "⚠️ Cart is empty!")
        return

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            p_datetime = datetime.datetime.combine(po_date, datetime.datetime.now().time()).strftime('%Y-%m-%d %H:%M:%S')
            
            vendor_groups = {}
            for item in cart:
                vid = item['vendor_id']
                if vid not in vendor_groups:
                    vendor_groups[vid] = {'total': 0, 'items': []}
                vendor_groups[vid]['total'] += item['total']
                vendor_groups[vid]['items'].append(item)
            
            for vid, data in vendor_groups.items():
                cursor.execute(
                    "INSERT INTO purchases (vendor_id, purchase_date, total_amount, status) VALUES (%s, %s, %s, %s)", 
                    (vid, p_datetime, data['total'], po_status)
                )
                purchase_id = cursor.lastrowid
                
                items_data = [
                    (purchase_id, item['product_id'], item['quantity'], item['cost_price']) 
                    for item in data['items']
                ]
                cursor.executemany(
                    "INSERT INTO purchase_items (purchase_id, product_id, quantity, cost_price) VALUES (%s, %s, %s, %s)",
                    items_data
                )
                
                if po_status == 'RECEIVED':
                    ledger_data = [
                        (item['product_id'], 'PURCHASE', purchase_id, item['quantity'], p_datetime)
                        for item in data['items']
                    ]
                    cursor.executemany(
                        "INSERT INTO inventory_ledger (product_id, transaction_type, reference_id, quantity_change, transaction_date) VALUES (%s, %s, %s, %s, %s)",
                        ledger_data
                    )
            
            conn.commit()
            num_pos = len(vendor_groups)
            st.session_state.static_msg = ("success", f"✅ {num_pos} Purchase Order(s) created successfully!")
            st.session_state.current_purchase_items = [] 
            
            if 'add_v_name' in st.session_state: del st.session_state['add_v_name']
            if 'add_p_label' in st.session_state: del st.session_state['add_p_label']
            if 'po_status' in st.session_state: del st.session_state['po_status']
            st.session_state.add_qty = 1
            st.session_state.add_cost = 0.0
            
        except Error as e:
            st.session_state.static_msg = ("error", f"❌ Error creating purchase: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close() # 🔴 SAFELY CLOSES CONNECTION

def mark_received_callback(po_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("UPDATE purchases SET status = 'RECEIVED' WHERE purchase_id = %s", (po_id,))
            cursor.execute("SELECT product_id, quantity FROM purchase_items WHERE purchase_id = %s", (po_id,))
            po_items = cursor.fetchall()
            
            curr_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for itm in po_items:
                cursor.execute(
                    "INSERT INTO inventory_ledger (product_id, transaction_type, reference_id, quantity_change, transaction_date) VALUES (%s, 'PURCHASE', %s, %s, %s)",
                    (itm['product_id'], po_id, itm['quantity'], curr_time)
                )
            conn.commit()
            st.session_state.static_msg = ("success", "✅ Purchase marked as Received! Inventory updated.")
        except Error as e:
            st.session_state.static_msg = ("error", f"❌ Database Error: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close() # 🔴 SAFELY CLOSES CONNECTION

# ==========================================
# 🏢 DIALOG FOR NEW VENDOR
# ==========================================
@st.dialog("🏢 Add New Vendor")
def add_vendor_dialog():
    with st.form("add_vendor_form", clear_on_submit=True):
        v_col1, v_col2 = st.columns(2)
        with v_col1:
            new_v_name = st.text_input("Vendor Name*")
            new_v_contact = st.text_input("Contact (Phone/Email)")
        with v_col2:
            new_v_lead = st.number_input("Lead Time (Days)", min_value=0, step=1, value=0)
            new_v_address = st.text_input("Address")
        
        if st.form_submit_button("Save Vendor", type="primary", use_container_width=True):
            if not new_v_name:
                st.error("Vendor Name is required!")
            else:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute(
                            "INSERT INTO vendors (name, contact, address, lead_time_days) VALUES (%s, %s, %s, %s)",
                            (new_v_name, new_v_contact, new_v_address, new_v_lead)
                        )
                        conn.commit()
                        get_cached_vendors.clear() 
                        st.session_state.newly_added_vendor = new_v_name
                        st.session_state.static_msg = ("success", f"✅ Vendor '{new_v_name}' added successfully!")
                        st.rerun() 
                    except Error as e:
                        st.error(f"Error adding vendor: {e}")
                    finally:
                        cursor.close()
                        conn.close() # 🔴 SAFELY CLOSES CONNECTION

# ==========================================
# 🛒 DIALOG FOR NEW PURCHASE ORDER 
# ==========================================
@st.dialog("🛒 Create Multi-Vendor Order", width="large")
def create_purchase_dialog():
    vendor_list_data = get_cached_vendors()
    product_list_data = get_cached_products()
    
    vendor_dict = {v['name']: v['vendor_id'] for v in vendor_list_data}
    product_dict = {f"{p['name']} ({p['sku']})": p for p in product_list_data}

    po_col1, po_col2 = st.columns(2)
    with po_col1:
        po_date = st.date_input("Global Purchase Date", datetime.date.today(), key="po_date")
    with po_col2:
        po_status = st.selectbox("Global Status", ["RECEIVED", "PENDING", "CANCELLED"], key="po_status")
        
    st.write("---")

    v_col, p_col, q_col, c_col, b_col = st.columns([2, 2.5, 1, 1, 1.5])
    with v_col:
        v_options = ["Select a vendor..."] + list(vendor_dict.keys())
        default_v_idx = 0
        if 'newly_added_vendor' in st.session_state and st.session_state.newly_added_vendor in vendor_dict:
            default_v_idx = v_options.index(st.session_state.newly_added_vendor)
            del st.session_state.newly_added_vendor
        st.selectbox("Vendor", v_options, index=default_v_idx, key="add_v_name")
            
    with p_col:
        st.selectbox("Product", options=["Select a product..."] + list(product_dict.keys()), key="add_p_label")
    with q_col:
        st.number_input("Qty", min_value=1, step=1, key="add_qty")
    with c_col:
        st.number_input("Cost (₹)", min_value=0.0, step=1.0, key="add_cost")
    with b_col:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        st.button("➕ Add Item", use_container_width=True, on_click=add_item_callback, args=(vendor_dict, product_dict))

    grand_total = 0 
    if st.session_state.current_purchase_items:
        st.write("")
        st.markdown("#### Smart Cart")
        
        h0, h1, h2, h3, h4, h5 = st.columns([2, 2.5, 1, 1, 1, 0.5])
        h0.markdown("**Vendor**")
        h1.markdown("**Product**")
        h2.markdown("**Qty**")
        h3.markdown("**Cost**")
        h4.markdown("**Total**")
        h5.markdown("")
        st.markdown("<hr style='margin: 5px 0'>", unsafe_allow_html=True)

        for i, item in enumerate(st.session_state.current_purchase_items):
            grand_total += item['total']
            c0, c1, c2, c3, c4, c5 = st.columns([2, 2.5, 1, 1, 1, 0.5])
            c0.write(item['vendor_name'])
            c1.write(item['name'])
            c2.write(f"{item['quantity']}")
            c3.write(f"₹{item['cost_price']:,.2f}")
            c4.write(f"₹{item['total']:,.2f}")
            c5.button("🗑️", key=f"del_item_{i}", on_click=remove_item_callback, args=(i,))
            st.markdown("<hr style='margin: 0; opacity: 0.1'>", unsafe_allow_html=True)
        
        st.markdown(f"""
        <div style='text-align: right; padding: 15px; background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; margin-top: 10px;'>
            <span style='font-size: 16px; font-weight: 600; color: #166534;'>Grand Total: ₹{grand_total:,.2f}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            if st.button("💾 Save Orders", type="primary", use_container_width=True, on_click=save_purchase_callback, args=(po_date, po_status)):
                st.rerun() 
        with s_col2:
            if st.button("Cancel", use_container_width=True, on_click=cancel_purchase_callback):
                st.rerun() 

# ==========================================
# 🛒 MAIN PURCHASE PAGE FUNCTION
# ==========================================
def show_purchase_page():
    st.markdown("""
    <style>
        .stApp { overflow-y: scroll !important; }
        .page-header { font-size: 24px; font-weight: 700; color: #111827; display: flex; flex-direction: column; }
        .page-sub { font-size: 14px; color: #6B7280; font-weight: 400; margin-top: -5px; margin-bottom: 20px;}
        .dashboard-card { background-color: #FFFFFF !important; border: 1px solid #E5E7EB; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 20px;}
        .table-container { overflow-x: auto; display: block; width: 100%; }
        .custom-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; min-width: 800px; }
        .custom-table th { font-size: 13px; color: #6B7280; background-color: #F9FAFB; padding: 12px 15px; text-align: left; border-bottom: 1px solid #E5E7EB; font-weight: 600; text-transform: uppercase;}
        .custom-table td { font-size: 14px; color: #111827; padding: 12px 15px; border-bottom: 1px solid #E5E7EB; font-weight: 500;}
        .status-received { background-color: #D1FAE5; color: #065F46; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;}
        .status-pending { background-color: #FEF3C7; color: #92400E; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;}
        .status-cancelled { background-color: #FEE2E2; color: #991B1B; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;}
        .kpi-num { font-size: 24px; font-weight: 700; color: #111827; margin-top: 5px; margin-bottom: 0px; }
        .kpi-label { font-size: 13px; color: #6B7280; font-weight: 500; text-transform: uppercase; }
        .stTextInput input, .stNumberInput input { border-radius: 6px; border: 1px solid #E5E7EB; }
    </style>
    """, unsafe_allow_html=True)

    if 'current_purchase_items' not in st.session_state:
        st.session_state.current_purchase_items = []

    msg_zone = st.empty()
    if 'static_msg' in st.session_state:
        m_type, text = st.session_state.static_msg
        if m_type == "success": msg_zone.success(text)
        elif m_type == "warning": msg_zone.warning(text)
        elif m_type == "error": msg_zone.error(text)
        del st.session_state.static_msg

    # ==========================================
    # MAIN PAGE HEADER & ACTIONS
    # ==========================================
    top_col1, top_col2, top_col3 = st.columns([3, 1, 1])
    with top_col1:
        st.markdown("<div class='page-header'>Purchases<div class='page-sub'>Manage stock procurement and vendor orders</div></div>", unsafe_allow_html=True)
    with top_col2:
        if st.button("🏢 Add Vendor", use_container_width=True):
            add_vendor_dialog()
    with top_col3:
        if st.button("➕ New Purchase", type="primary", use_container_width=True):
            create_purchase_dialog()

    st.write("---")

    # ==========================================
    # ⚡ SAFE CONNECTION FOR MAIN PAGE
    # ==========================================
    # 1. Fetch RAM data FIRST before opening main connection
    vendor_list_data = get_cached_vendors()
    vendor_options = ["All"] + [v['name'] for v in vendor_list_data]

    # 2. Open DB connection safely
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor(dictionary=True)

    search_col, filter_vendor_col, filter_status_col = st.columns([4, 2, 2])
    with search_col:
        search_term = st.text_input("🔍 Search PO or Vendor", label_visibility="collapsed", placeholder="🔍 Search PO ID or Vendor...")
    with filter_vendor_col:
        filter_vendor = st.selectbox("Vendor Filter", vendor_options, label_visibility="collapsed")
    with filter_status_col:
        filter_status = st.selectbox("Status Filter", ["All", "PENDING", "RECEIVED", "CANCELLED"], label_visibility="collapsed")

    query = """
        SELECT p.purchase_id, p.purchase_date, p.total_amount, p.status, v.name as vendor_name,
               COUNT(pi.id) as items_count
        FROM purchases p
        LEFT JOIN vendors v ON p.vendor_id = v.vendor_id
        LEFT JOIN purchase_items pi ON p.purchase_id = pi.purchase_id
        WHERE 1=1
    """
    params = []
    
    if search_term:
        if search_term.isdigit() or search_term.upper().startswith("PO-"):
            num_part = search_term.upper().replace("PO-", "")
            if num_part.isdigit():
                query += " AND p.purchase_id = %s"
                params.append(int(num_part))
        else:
            query += " AND v.name LIKE %s"
            params.append(f"%{search_term}%")
            
    if filter_vendor != "All":
        query += " AND v.name = %s"
        params.append(filter_vendor)
        
    if filter_status != "All":
        query += " AND p.status = %s"
        params.append(filter_status)

    query += " GROUP BY p.purchase_id, p.purchase_date, p.total_amount, p.status, v.name ORDER BY p.purchase_id DESC"
    
    cursor.execute(query, tuple(params))
    purchase_records = cursor.fetchall()
    
    if purchase_records:
        html_table = "<div class='dashboard-card' style='padding: 0;'><div class='table-container'><table class='custom-table'><thead><tr><th>PO ID</th><th>Date</th><th>Vendor</th><th>Items</th><th>Total Amount</th><th>Status</th></tr></thead><tbody>"
        
        for row in purchase_records:
            formatted_id = f"PO-{row['purchase_id']:03d}"
            raw_date = str(row['purchase_date']) if row['purchase_date'] else "N/A"
            try:
                formatted_date = pd.to_datetime(raw_date).strftime("%d %b %Y, %I:%M %p")
            except:
                formatted_date = raw_date
                
            total_amt = float(row['total_amount']) if row['total_amount'] else 0.0
            vendor_name = row['vendor_name'] if row['vendor_name'] else "Unknown Vendor"
            
            status_raw = row['status']
            if status_raw == 'RECEIVED':
                status_html = "<span class='status-received'>🟢 Received</span>"
            elif status_raw == 'PENDING':
                status_html = "<span class='status-pending'>🟡 Pending</span>"
            else:
                status_html = "<span class='status-cancelled'>🔴 Cancelled</span>"

            html_table += f"<tr><td style='font-weight:600; color:#3B82F6;'>{formatted_id}</td><td>{formatted_date}</td><td>{vendor_name}</td><td>{row['items_count']}</td><td>₹{total_amt:,.2f}</td><td>{status_html}</td></tr>"

        html_table += "</tbody></table></div>"
        html_table += f"<div style='padding: 15px; font-size: 13px; color: #6B7280; text-align: center; border-top: 1px solid #E5E7EB;'>Showing {len(purchase_records)} purchases</div></div>"
        
        st.markdown(html_table, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.write("⚙️ **Purchase Actions**")
            act_col1, act_col2 = st.columns([3, 1])
            
            po_action_dict = {f"PO-{r['purchase_id']:03d} | {r['vendor_name']} ({r['status']})": r for r in purchase_records}
            
            with act_col1:
                selected_action_po = st.selectbox("Select a Purchase Order:", options=["Select PO..."] + list(po_action_dict.keys()), label_visibility="collapsed")
            
            with act_col2:
                if selected_action_po != "Select PO...":
                    selected_po_data = po_action_dict[selected_action_po]
                    
                    if selected_po_data['status'] == 'PENDING':
                        st.button("✅ Mark as Received", use_container_width=True, type="primary", 
                                  on_click=mark_received_callback, args=(selected_po_data['purchase_id'],))
                    elif selected_po_data['status'] == 'RECEIVED':
                        st.button("✔️ Already Received", disabled=True, use_container_width=True)
                    else:
                        st.button(f"🚫 {selected_po_data['status']}", disabled=True, use_container_width=True)

    else:
        st.info("No purchase orders found. Click '+ New Purchase' to create one.")

    st.write("---")
    st.markdown("<div class='page-sub' style='font-weight: 600; color:#111827;'>📊 Purchase Summary</div>", unsafe_allow_html=True)
    
    today = datetime.date.today()
    purchases_today_val = 0
    for r in purchase_records:
        if r['purchase_date']:
            try:
                if pd.to_datetime(r['purchase_date']).date() == today:
                    purchases_today_val += float(r['total_amount'] or 0)
            except: pass

    pending_orders_count = sum(1 for r in purchase_records if r['status'] == 'PENDING')
    total_procurement = sum(float(r['total_amount'] or 0) for r in purchase_records)
    
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        st.markdown(f"<div class='dashboard-card'><div class='kpi-label'>Purchases Today</div><div class='kpi-num'>₹{purchases_today_val:,.2f}</div></div>", unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"<div class='dashboard-card'><div class='kpi-label'>Pending Orders</div><div class='kpi-num'>{pending_orders_count}</div></div>", unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"<div class='dashboard-card'><div class='kpi-label'>Total Spend</div><div class='kpi-num'>₹{total_procurement:,.2f}</div></div>", unsafe_allow_html=True)

    cursor.close()
    conn.close() # 🔴 SAFELY CLOSES CONNECTION