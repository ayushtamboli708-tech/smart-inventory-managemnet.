import streamlit as st
import pandas as pd
import mysql.connector # 🔴 RESTORED: Native MySQL
from mysql.connector import Error, IntegrityError
import time

# 
#  DATABASE CONNECTION HELPER
# 
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
        st.error(f"DB Error: {e}")
        return None

def show_product_page():
    # --- CSS STYLING ---
    st.markdown("""
    <style>
        .page-header { font-size: 24px; font-weight: 700; color: #111827; }
        .page-sub { font-size: 14px; color: #6B7280; font-weight: 400; margin-top: -5px; margin-bottom: 20px;}
        .dashboard-card { background-color: #FFFFFF !important; border: 1px solid #E5E7EB; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 20px;}
    </style>
    """, unsafe_allow_html=True)

    # --- STATE INITIALIZATION ---
    if 'show_product_form' not in st.session_state: 
        st.session_state.show_product_form = False
    if 'edit_product_data' not in st.session_state: 
        st.session_state.edit_product_data = None

    # 
    # 1️⃣ HEADER
    # 
    c1, c2 = st.columns([4, 1])
    with c1: 
        st.markdown("<div class='page-header'>Products<div class='page-sub'>Manage your inventory catalog</div></div>", unsafe_allow_html=True)
    with c2: 
       # security check
        if st.session_state.role == "Owner":
            if st.button("➕ New Product", type="primary", use_container_width=True):
                st.session_state.show_product_form = True
                st.session_state.edit_product_data = None
                st.rerun()

    # 
    # 2️⃣ ADD / EDIT FORM
    # 
    # security check
    if st.session_state.show_product_form and st.session_state.role == "Owner":
        is_edit = st.session_state.edit_product_data is not None
        p_data = st.session_state.edit_product_data if is_edit else {}
        
        with st.container(border=True):
            st.markdown(f"### {'✏️ Edit Product' if is_edit else '✨ Add New Product'}")
            
            with st.form("prod_form"):
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    sku = st.text_input("SKU*", value=p_data.get('sku', ''), disabled=is_edit)
                    name = st.text_input("Product Name*", value=p_data.get('name', ''))
                    
                    # Safe Indexing for Dropdowns
                    cats = ["Dairy", "Bakery", "Beverages", "Electronics", "Apparel", "Other", "Vegetables", "Snacks", "Grocery", "Personal Care"]
                    c_val = p_data.get('category', 'Other')
                    c_idx = cats.index(c_val) if c_val in cats else 0
                    cat = st.selectbox("Category", cats, index=c_idx)
                    
                    units = ["Pc", "Ltr", "Kg", "Box", "Dozen"]
                    u_val = p_data.get('unit', 'Pc')
                    u_idx = units.index(u_val) if u_val in units else 0
                    unit = st.selectbox("Unit", units, index=u_idx)

                with f_col2:
                    price = st.number_input("Selling Price (₹)", min_value=0.0, value=float(p_data.get('selling_price', 0.0)))
                    reorder = st.number_input("Reorder Threshold", min_value=0, value=int(p_data.get('reorder_threshold', 10)))
                    active = st.checkbox("Active Status", value=bool(p_data.get('is_active', True)))

                # Form Submission
                if st.form_submit_button("💾 Save Product", type="primary", use_container_width=True):
                    if not sku or not name:
                        st.error("SKU and Name are required!")
                    else:
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            try:
                                if is_edit:
                                    cursor.execute("""
                                        UPDATE products 
                                        SET name=%s, category=%s, unit=%s, selling_price=%s, reorder_threshold=%s, is_active=%s 
                                        WHERE sku=%s
                                    """, (name, cat, unit, price, reorder, active, sku))
                                else:
                                    cursor.execute("""
                                        INSERT INTO products (sku, name, category, unit, selling_price, reorder_threshold, is_active) 
                                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                                    """, (sku, name, cat, unit, price, reorder, active))
                                
                                conn.commit()
                                st.success("✅ Product Saved Successfully!")
                                st.session_state.show_product_form = False
                                time.sleep(0.5)
                                st.rerun()
                            except Error as e:
                                st.error(f"Failed to save: {e}")
                            finally:
                                cursor.close()
                                conn.close()

            if st.button("Cancel"):
                st.session_state.show_product_form = False
                st.rerun()
                
        st.write("---")

    # 
    # 🚀 BULK UPLOAD (CSV)
    #security check
    if not st.session_state.show_product_form and st.session_state.role == "Owner":
        with st.expander("📂 Bulk Upload Products (CSV)"):
            st.write("Upload a CSV file to add multiple products at once. Required columns: `SKU`, `Name`, `Category`, `Unit`, `Price`, `Reorder_Pt`")
            
            uploaded_file = st.file_uploader("Choose a CSV file", type="csv", label_visibility="collapsed")
            
            if uploaded_file is not None:
                try:
                    df_upload = pd.read_csv(uploaded_file)
                    st.write("Preview of uploaded data:")
                    st.dataframe(df_upload.head(3), use_container_width=True)
                    
                    if st.button("🚀 Process & Save Batch", type="primary"):
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            success_count = 0
                            error_count = 0
                            
                            for index, row in df_upload.iterrows():
                                try:
                                    cursor.execute("""
                                        INSERT INTO products (sku, name, category, unit, selling_price, reorder_threshold, is_active) 
                                        VALUES (%s, %s, %s, %s, %s, %s, 1)
                                    """, (
                                        str(row['SKU']), str(row['Name']), str(row['Category']), 
                                        str(row['Unit']), float(row['Price']), int(row['Reorder_Pt'])
                                    ))
                                    success_count += 1
                                except IntegrityError:
                                    # SKU already exists, skip it
                                    error_count += 1
                                except Exception as e:
                                    error_count += 1
                                    
                            conn.commit()
                            cursor.close()
                            conn.close()
                            
                            st.success(f"✅ Successfully added {success_count} products!")
                            if error_count > 0:
                                st.warning(f"⚠️ Skipped {error_count} items (likely duplicate SKUs or missing data).")
                            time.sleep(2)
                            st.rerun()
                except Exception as e:
                    st.error(f"Error reading CSV file: {e}. Please ensure it matches the template format.")
                    
        st.write("---")

    # 
    #  FILTERS
    # 
    st.markdown("##### 🔍 Filter Products")
    filt_c1, filt_c2, filt_c3 = st.columns([2, 1, 1])
    
    with filt_c1:
        search_q = st.text_input("Search", placeholder="Search by Product Name or SKU...", label_visibility="collapsed")
    with filt_c2:
        cat_filt = st.selectbox("Category", ["All Categories", "Dairy", "Bakery", "Beverages", "Electronics", "Apparel", "Other", "Vegetables", "Snacks", "Grocery", "Personal Care"], label_visibility="collapsed")
    with filt_c3:
        status_filt = st.selectbox("Status", ["All Statuses", "Active", "Inactive"], label_visibility="collapsed")

    # 
    # 4️⃣ FETCH & DISPLAY TABLE 
    # 
    conn = get_db_connection()
    if conn:
        query = """
            SELECT 
                product_id, sku, name, category, unit, selling_price, reorder_threshold, is_active,
                (SELECT IFNULL(SUM(quantity_change), 0) FROM inventory_ledger WHERE product_id = products.product_id) as stock_qty
            FROM products 
            WHERE 1=1
        """
        params = []
        
        if search_q:
            query += " AND (name LIKE %s OR sku LIKE %s)"
            params.extend([f"%{search_q}%", f"%{search_q}%"])
        if cat_filt != "All Categories":
            query += " AND category = %s"
            params.append(cat_filt)
        if status_filt == "Active":
            query += " AND is_active = 1"
        elif status_filt == "Inactive":
            query += " AND is_active = 0"
            
        query += " ORDER BY product_id DESC"
        
        df = pd.read_sql(query, conn, params=tuple(params))
        
        if not df.empty:
            display_df = df.copy()
            display_df['selling_price'] = display_df['selling_price'].apply(lambda x: f"₹{x:,.2f}")
            display_df['Status'] = display_df['is_active'].apply(lambda x: "🟢 Active" if x else "🔴 Inactive")
            display_df['stock_qty'] = display_df['stock_qty'].astype(int)
            
            display_df = display_df[['sku', 'name', 'category', 'stock_qty', 'unit', 'selling_price', 'reorder_threshold', 'Status']]
            display_df.columns = ['SKU', 'Name', 'Category', 'Stock Qty', 'Unit', 'Price', 'Reorder Pt', 'Status']
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # 
            # 5️⃣ ACTION MENU 
            # 
            # security check
            if st.session_state.role == "Owner":
                st.markdown("<br>", unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown("##### ⚙️ Product Actions")
                    
                    act_c1, act_c2, act_c3, act_c4 = st.columns([3, 1, 1, 1])
                    
                    records = df.to_dict('records')
                    prod_options = {f"[{r['sku']}] {r['name']}": r for r in records}
                    
                    with act_c1:
                        selected_action_prod = st.selectbox("Select Product to Modify:", options=["Select..."] + list(prod_options.keys()), label_visibility="collapsed")
                    
                    if selected_action_prod != "Select...":
                        target_product = prod_options[selected_action_prod]
                        p_id = target_product['product_id']
                        
                        # EDIT BUTTON
                        with act_c2:
                            if st.button("✏️ Edit", use_container_width=True):
                                st.session_state.edit_product_data = target_product
                                st.session_state.show_product_form = True
                                st.rerun()
                                
                        # TOGGLE BUTTON
                        with act_c3:
                            if target_product['is_active']:
                                if st.button("🔴 Deactivate", use_container_width=True):
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE products SET is_active = 0 WHERE product_id = %s", (p_id,))
                                    conn.commit()
                                    cursor.close()
                                    st.rerun()
                            else:
                                if st.button("🟢 Activate", use_container_width=True):
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE products SET is_active = 1 WHERE product_id = %s", (p_id,))
                                    conn.commit()
                                    cursor.close()
                                    st.rerun()

                        #  HARD DELETE BUTTON
                        with act_c4:
                            if st.button("🗑️ Hard Delete", type="primary", use_container_width=True, help="WARNING: This permanently wipes the product and all its history."):
                                cursor = conn.cursor()
                                try:
                                    cursor.execute("DELETE FROM reorder_suggestions WHERE product_id = %s", (p_id,))
                                    cursor.execute("DELETE FROM forecasts WHERE product_id = %s", (p_id,))
                                    cursor.execute("DELETE FROM inventory_ledger WHERE product_id = %s", (p_id,))
                                    cursor.execute("DELETE FROM sale_items WHERE product_id = %s", (p_id,))
                                    cursor.execute("DELETE FROM purchase_items WHERE product_id = %s", (p_id,))
                                    cursor.execute("DELETE FROM products WHERE product_id = %s", (p_id,))
                                    
                                    conn.commit()
                                    st.toast("Product permanently deleted.", icon="🚨")
                                    time.sleep(1)
                                    st.rerun()
                                except Error as e:
                                    st.error(f"Cannot delete product due to database constraints: {e}")
                                    conn.rollback()
                                finally:
                                    cursor.close()

        else:
            st.info("No products found matching your filters.")
            
        conn.close()