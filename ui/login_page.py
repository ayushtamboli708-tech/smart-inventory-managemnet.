import streamlit as st
import mysql.connector
from mysql.connector import Error
import time

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

def show_login_screen():
    if 'show_owner_input' not in st.session_state:
        st.session_state.show_owner_input = False

    #  PERFECTLY CENTERED & BALANCED POS STYLING
    st.markdown("""
    <style>
        /* 1. Base App Background */
        .stApp {
            background-color: #FFFFFF !important;
        }
        
        /* 2. Hide clutter and vertically center EVERYTHING */
        [data-testid="stHeader"] { display: none; }
        .block-container { 
            padding-top: 15vh !important; /* 🔴 FORCES layout down from the roof */
            padding-bottom: 0 !important;
            max-width: 1000px !important; /* Keeps boxes close together */
        }

        /* 3. Left Side: RED Branding Panel */
        .brand-box {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            color: white;
            border-radius: 24px;
            padding: 40px;
            height: 500px !important; /* 🔴 LOCKED HEIGHT */
            margin-top: 0 !important; /* Flushes with right box */
            display: flex;
            flex-direction: column;
            justify-content: center;
            box-shadow: 0 10px 25px rgba(239, 68, 68, 0.2);
            box-sizing: border-box;
        }
        .brand-title { font-size: 58px; font-weight: 800; letter-spacing: -2px; margin-bottom: 10px; line-height: 1.1; text-align: center; }
        .brand-sub { font-size: 20px; color: rgba(255,255,255,0.8); font-weight: 400; letter-spacing: 1px; text-align: center; }
        .version-text { margin-top: 40px; font-size: 13px; color: rgba(255,255,255,0.7); text-align: center; }

        /* 4. Right Side: White Login Card */
        [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E5E7EB !important;
            border-radius: 24px !important;
            padding: 40px 30px !important;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.1) !important;
            height: 500px !important; /* 🔴 LOCKED HEIGHT */
            margin-top: 0 !important; /* Flushes with left box */
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            box-sizing: border-box !important;
        }

        /* 5. Giant Premium Buttons */
        .stButton > button {
            border-radius: 12px;
            padding: 24px 20px;
            font-size: 18px;
            font-weight: 600;
            transition: all 0.2s ease;
            border: none;
            width: 100%;
        }
        
        /* 🔥 OWNER BUTTON */
        [data-testid="stButton"] button[kind="primary"] {
            background-color: #ef4444; 
            color: white;
        }
        [data-testid="stButton"] button[kind="primary"]:hover {
            background-color: #dc2626; 
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(239, 68, 68, 0.3);
        }
        
        /* 🧑‍💼 STAFF / BACK BUTTON */
        [data-testid="stButton"] button[kind="secondary"] {
            background-color: #F3F4F6; 
            color: #111827 !important; 
            border: 1px solid #D1D5DB;
        }
        [data-testid="stButton"] button[kind="secondary"]:hover {
            background-color: #E5E7EB; 
            transform: translateY(-2px);
            border: 1px solid #9CA3AF;
        }

        /* 6. Clean Inputs */
        .stTextInput input {
            background-color: #FFFFFF !important;
            border: 1px solid #D1D5DB !important;
            color: #111827 !important;
            border-radius: 8px !important;
            padding: 14px !important;
        }
        .stTextInput input:focus {
            border-color: #ef4444 !important; 
            box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2) !important;
        }
        .stTextInput label { color: #4B5563 !important; font-weight: 500 !important; }
        
        /* Ensure all typography on the right side is dark */
        [data-testid="stVerticalBlockBorderWrapper"] p, 
        [data-testid="stVerticalBlockBorderWrapper"] h1, 
        [data-testid="stVerticalBlockBorderWrapper"] h2 { 
            color: #111827 !important; 
        }
    </style>
    """, unsafe_allow_html=True)

    #  Split Layout 
    c1, c2 = st.columns([1, 1], gap="large")

    #  LEFT SIDE
    with c1:
        st.markdown("""
        <div class='brand-box'>
            <div class='brand-title'>STOCKWISE</div>
            <div class='brand-sub'>Fast. Simple. Reliable.</div>
            <div class='version-text'>Stockwise Enterprise POS v2.0</div>
        </div>
        """, unsafe_allow_html=True)

    #  RIGHT SIDE:
    with c2:
        with st.container(border=True):
            
            if not st.session_state.show_owner_input:
                # --- MAIN BUTTON VIEW ---
                st.markdown("<h2 style='margin-top:0; font-weight:800; text-align:center;'>Terminal Access</h2>", unsafe_allow_html=True)
                st.markdown("<p style='color:#6B7280; font-size:14px; margin-bottom: 30px; text-align:center;'>Select your role to continue.</p>", unsafe_allow_html=True)

                if st.button("🧑‍💼 Log in as Staff", type="secondary"):
                    st.session_state.authenticated = True
                    st.session_state.role = "Staff"
                    st.session_state.user_name = "Staff Member"
                    st.rerun()
                st.markdown("<p style='text-align:center; color:#9CA3AF; font-size:12px; margin-top:-10px; margin-bottom:20px;'>Quick access for standard operations</p>", unsafe_allow_html=True)

                if st.button("👑 Log in as Owner", type="primary"):
                    st.session_state.show_owner_input = True
                    st.rerun()
                st.markdown("<p style='text-align:center; color:#9CA3AF; font-size:12px; margin-top:-10px; margin-bottom:10px;'>Requires secure password</p>", unsafe_allow_html=True)

            else:
                # --- PASSWORD VIEW ---
                st.markdown("<h2 style='margin-top:0; font-weight:800; text-align:center;'>Owner Login</h2>", unsafe_allow_html=True)
                st.markdown("<p style='color:#6B7280; font-size:14px; margin-bottom: 20px; text-align:center;'>Enter credentials to unlock terminal.</p>", unsafe_allow_html=True)

                username = st.text_input("Username", placeholder="Enter username", label_visibility="collapsed")
                password = st.text_input("Password", type="password", placeholder="Enter password", label_visibility="collapsed")

                st.write("")
                if st.button("🔓 Unlock Terminal", type="primary"):
                    conn = get_db_connection()
                    if conn:
                        cursor = conn.cursor(dictionary=True)
                        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s AND role = 'Owner'", (username, password))
                        user = cursor.fetchone()
                        cursor.close()
                        conn.close()

                        if user:
                            st.markdown("<p style='color:#10b981; font-weight:600; text-align:center; margin-top:10px;'>Authentication successful. Loading...</p>", unsafe_allow_html=True)
                            time.sleep(0.6)
                            st.session_state.authenticated = True
                            st.session_state.role = "Owner"
                            st.session_state.user_name = username
                            st.session_state.show_owner_input = False 
                            st.rerun()
                        else:
                            st.markdown("<p style='color:#ef4444; font-size:14px; text-align:center; margin-top:10px;'>Incorrect username or password.</p>", unsafe_allow_html=True)

                st.write("")
                if st.button("← Back to Select Role", type="secondary"):
                    st.session_state.show_owner_input = False
                    st.rerun()