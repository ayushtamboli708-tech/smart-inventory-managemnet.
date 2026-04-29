# Stockwise - Predictive Inventory & ERP System 

An intelligent, ML-powered Point of Sale (POS) and Inventory Management system featuring SARIMA demand forecasting, role-based security, and automated stock alerts.

## ⚠️ Problem Statement
Small to medium retailers face two major profit-killers: running out of stock (losing sales) and overstocking (tying up capital). Manual reordering relies on guesswork, and managing these operations on shared systems often leads to staff accidentally modifying or deleting crucial product catalogs.

## 💡 Solution Overview
Stockwise unifies daily cashier operations with an AI-driven backend. It leverages historical sales data to predict future demand using machine learning, automatically triggers alerts before stock runs out, and securely separates regular staff from store owners to protect business-critical data.

## ⚙️ Key Features
* **Demand Forecasting (SARIMA):** Eliminates supply chain guesswork. The integrated ML engine analyzes past sales trends to predict future demand and generate suggested order quantities for each product.
* **Automated Smart Alerts:** A dedicated monitoring dashboard instantly identifies and categorizes inventory health, warning the team of "Low Stock", "Out of Stock", and "Overstock" situations based on custom reorder thresholds.
* **Role-Based Access Control (RBAC):** Strict security protocols separate 'Owner' and 'Staff' roles. Staff can rapidly process sales and purchases, while only Owners have the authority to add, activate, deactivate, or hard-delete the master product catalog.
* **Bulk Data Processing:** Save hours of manual data entry by uploading or downloading massive datasets of sales and purchases instantly via CSV import/export functions.
* **Smart Cart Multi-Vendor Routing:** Add items from multiple different suppliers into a single procurement cart; the system algorithmically splits the data and generates independent Purchase Orders in the background.

## 🛠️ Tech Stack
* **Language:** Python 3.9+
* **Frontend Framework:** Streamlit
* **Machine Learning:** `statsmodels` (SARIMA Time-Series Forecasting)
* **Database:** TiDB Cloud (MySQL)
* **Data Processing:** Pandas
* **Database Driver:** `mysql-connector-python`

##  Project Architecture

## 🧱 Project Architecture
```text
Stockwise2/
├── .streamlit/
│   └── secrets.toml            # Secure database credentials (Git-ignored)
├── forecast/
│   └── forecasting_engine.py   # SARIMA ML model for demand prediction
├── ui/
│   ├── alert_page.py           # Stock health and ML reorder suggestions
│   ├── login_page.py           # Role-Based Authentication gateway
│   ├── product_page.py         # Catalog management (Owner access only)
│   ├── purchase_page.py        # Procurement and smart-cart routing
│   └── sales_page.py           # POS checkout terminal
├── app.py                      # Main application router and state manager
└── requirements.txt            # Dependency management
```

## Installation

## ▶️ Setup & Installation
You can run this system locally in under 5 minutes.

## ▶️ Setup & Installation
You can run this system locally in under 5 minutes.

**1. Clone the repository:**
```bash
git clone [https://github.com/ayushtamboli708-tech/smart-inventory-managemnet.git](https://github.com/ayushtamboli708-tech/smart-inventory-managemnet.git)
cd smart-inventory-managemnet
```

**2. Install dependencies:**
```bash
pip install -r requirements.txt
```

**3. Configure Secure Cloud Credentials:**

```toml
[mysql]
host = "your-database-host.com"
port = 4000
database = "your_db_name"
user = "your_username"
password = "your_password"
```

**4. Launch the application:**
```bash
streamlit run app.py
```

## 📸 Screenshots

**1. Dashboard**
![Dashboard View](images/Screenshot%202026-04-30%20001404.png)

**2. Login Page**
![Login Page View](images/Screenshot%202026-04-30%20001313.png)

**3. Product Page**
![Product Page View](images/Screenshot%202026-04-30%20005042.png)

**4. Alert Page**
![Alert Page View](images/Screenshot%202026-04-30%20001427.png)


## Learnings & Engineering Challenges

1. Integrating Machine Learning with Web UIs: Running complex SARIMA forecasting models can freeze a web interface. I had to architect the forecasting_engine.py to efficiently process Pandas dataframes without bottlenecking the main Streamlit UI thread.

2. Securing UI State Management: Implementing RBAC required strict session-state management. I engineered the app router to dynamically hide entire pages (like product_page.py) and disable critical buttons based on the login token, ensuring Staff could never bypass their permissions.

3. Solving the "N+1 Database Problem": Initially, saving a multi-item purchase order took over 5 seconds due to sequential database pings. I rewrote the SQL logic to use cursor.executemany(), compressing the data into tuples and batch-inserting it in a single payload, dropping save times by 90%.


## Limitations & Future Improvements

1. Automated PDF Invoicing: Currently, reporting relies on CSV exports. Future updates will include programmatic PDF generation for immediate Purchase Order emailing.

2. Single-Tenant Architecture: The current database schema is designed for a single organization. To evolve this into a true SaaS product, a company_id column must be injected into all tables alongside a secure multi-tenant routing layer.

3. Scheduled Model Retraining: The SARIMA model currently calculates dynamically. For massive datasets, this should be moved to a scheduled background cron-job to pre-calculate forecasts overnight.
## Contributing

Contributions, issues, and feature requests are welcome! If you want to make major changes, please open a discussion first to ensure we are aligned on the architecture.


## Authors

Ayush Tamboli * 🎓 Final Year Computer Science Student

💻 GitHub: @ayushtamboli708-tech

***

