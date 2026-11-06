"""Single source of truth for application CSS."""

from __future__ import annotations

import streamlit as st


def inject_global_styles() -> None:
    st.markdown(
        """
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" />
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .stApp { font-family: 'Inter', sans-serif; background-color: #F8FAFC; color: #1F2937; }

        [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E5E7EB; }
        [data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child { display: none !important; }
        [data-testid="stRadio"] > div[role="radiogroup"] > label {
            background-color: transparent; color: #4B5563 !important; padding: 12px 15px !important;
            border-radius: 8px !important; border: 1px solid transparent; transition: all 0.2s;
            margin-bottom: 4px; display: block;
        }
        [data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
            background-color: #F3F4F6 !important; color: #111827 !important; transform: translateX(5px);
        }

        .dashboard-card {
            background-color: #FFFFFF !important; border: 1px solid #E5E7EB; border-radius: 12px;
            padding: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 20px;
            transition: all 0.3s ease; height: 100%;
        }
        .dashboard-card:hover { transform: translateY(-4px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); border-color: #BFDBFE; }

        .kpi-val { font-size: 28px; font-weight: 700; color: #111827; margin-top: 5px; }
        .kpi-lbl { font-size: 13px; font-weight: 600; text-transform: uppercase; color: #6B7280; }
        .kpi-num { font-size: 24px; font-weight: 700; color: #111827; margin-top: 5px; margin-bottom: 0; }
        .kpi-label { font-size: 13px; color: #6B7280; font-weight: 500; text-transform: uppercase; }

        .st-key-fab_main { position: fixed; bottom: 40px; right: 40px; z-index: 9999; }
        .st-key-fab_main button {
            background-color: #2563EB; color: white; border-radius: 30px; height: 60px; width: 60px; border: none;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4); display: flex; align-items: center; justify-content: center;
        }
        .st-key-fab_main button span { display: none; }
        .st-key-fab_main button::before { content: "analytics"; font-family: 'Material Symbols Rounded'; font-size: 28px; color: white; }
        .st-key-fab_main button:hover { width: 150px; justify-content: flex-start; padding-left: 20px; }
        .st-key-fab_main button:hover::after { content: "Forecast"; font-family: 'Inter'; font-weight: 600; margin-left: 10px; white-space: nowrap; }

        .section-title {
            font-size: 18px; font-weight: 600; color: #374151;
            margin: 20px 0 10px 0; border-bottom: 2px solid #E5E7EB; padding-bottom: 8px;
        }
        .page-header { font-size: 24px; font-weight: 700; color: #111827; display: flex; flex-direction: column; }
        .page-sub { font-size: 14px; color: #6B7280; font-weight: 400; margin-top: -5px; margin-bottom: 20px; }

        .custom-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
        .custom-table th {
            font-size: 13px; color: #6B7280; background-color: #F9FAFB; padding: 12px 15px;
            text-align: left; border-bottom: 1px solid #E5E7EB; font-weight: 600; text-transform: uppercase;
        }
        .custom-table td {
            font-size: 14px; color: #111827; padding: 12px 15px;
            border-bottom: 1px solid #E5E7EB; font-weight: 500;
        }

        .status-completed, .status-received {
            background-color: #D1FAE5; color: #065F46; padding: 4px 10px; border-radius: 12px;
            font-size: 12px; font-weight: 600; display: inline-flex; gap: 4px;
        }
        .status-pending {
            background-color: #FEF3C7; color: #92400E; padding: 4px 10px; border-radius: 12px;
            font-size: 12px; font-weight: 600; display: inline-flex; gap: 4px;
        }
        .status-cancelled, .status-refunded {
            background-color: #FEE2E2; color: #991B1B; padding: 4px 10px; border-radius: 12px;
            font-size: 12px; font-weight: 600; display: inline-flex; gap: 4px;
        }
        .sev-high { background-color: #FEE2E2; color: #991B1B; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .sev-med { background-color: #FEF3C7; color: #92400E; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .sev-low { background-color: #DBEAFE; color: #1E3A8A; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .search-result { background: #EFF6FF; border: 1px solid #BFDBFE; padding: 20px; border-radius: 12px; margin-bottom: 25px; }

        .stApp { overflow-y: scroll !important; }
        .stTextInput input, .stNumberInput input { border-radius: 6px; border: 1px solid #E5E7EB; }

        /* Login */
        .brand-box {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            color: white; border-radius: 24px; padding: 40px; height: 520px !important;
            margin-top: 0 !important; display: flex; flex-direction: column;
            justify-content: center; box-shadow: 0 10px 25px rgba(239, 68, 68, 0.2);
            box-sizing: border-box;
        }
        .brand-title { font-size: 58px; font-weight: 800; letter-spacing: -2px; margin-bottom: 10px; line-height: 1.1; text-align: center; }
        .brand-sub { font-size: 20px; color: rgba(255,255,255,0.8); font-weight: 400; letter-spacing: 1px; text-align: center; }
        .version-text { margin-top: 40px; font-size: 13px; color: rgba(255,255,255,0.7); text-align: center; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF !important; border: 1px solid #E5E7EB !important;
            border-radius: 24px !important; padding: 40px 30px !important;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.1) !important;
            height: 520px !important; margin-top: 0 !important; display: flex !important;
            flex-direction: column !important; justify-content: center !important;
            box-sizing: border-box !important;
        }
        .stTextInput input:focus { border-color: #ef4444 !important; box-shadow: 0 0 0 2px rgba(239,68,68,0.2) !important; }
        [data-testid="stVerticalBlockBorderWrapper"] p,
        [data-testid="stVerticalBlockBorderWrapper"] h1,
        [data-testid="stVerticalBlockBorderWrapper"] h2 { color: #111827 !important; }
    </style>
    """,
        unsafe_allow_html=True,
    )


def inject_page_styles() -> None:
    """Kept for imports; global styles are injected once in app.py."""
    return None
