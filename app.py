import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime, timedelta
import plotly.express as px
import os

# CONFIG
st.set_page_config(page_title="RVNP Attendance System", layout="wide", page_icon="🏫")

# --- DATA PERSISTENCE ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "attendance.db")

DEPARTMENTS = ["AGME", "AES", "BCE", "BSD", "ELEC", "HATS", "HAAPS", "LSD", "ICT"]

TIME_SLOTS = [
    "7.30-9.00", "09.00-10.30", "10.30-12.00",
    "12.00-1.30", "1.30-3.00", "3.00-4.30", "4.30-6.00"
]

# SESSION STATE
if "message" not in st.session_state:
    st.session_state.message = None

def show_message():
    if st.session_state.message:
        type_, text = st.session_state.message
        if type_ == "success": st.success(text)
        elif type_ == "error": st.error(text)
        elif type_ == "warning": st.warning(text)
        st.session_state.message = None

# DB HELPERS
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def fetch_df(query, params=()):
    conn = get_conn()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def execute(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        conn.commit()
        return True, "Success"
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "Duplicate Entry: Record already exists."
    except Exception as e:
        conn.rollback()
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

# INIT DATABASE
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('SUPER_ADMIN','HOD','CLASS_REP')),
        department_code TEXT
    );
    CREATE TABLE IF NOT EXISTS trainers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trainer_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        UNIQUE(trainer_name, department_code)
    );
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        UNIQUE(class_name, department_code)
    );
    CREATE TABLE IF NOT EXISTS units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        UNIQUE(unit_name, department_code)
    );
    CREATE TABLE IF NOT EXISTS lesson_attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lesson_date TEXT NOT NULL,
        class_name TEXT NOT NULL,
        unit_name TEXT NOT NULL,
        trainer_name TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Taught','Not Taught')),
        reason TEXT,
        remarks TEXT,
        reported_by TEXT NOT NULL,
        department_code TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(lesson_date, class_name, unit_name, trainer_name, time_slot)
    );
    CREATE TABLE IF NOT EXISTS class_rep_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        class_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        assigned_at TEXT DEFAULT (datetime('now')),
        UNIQUE(username, class_name, department_code)
    );
    """)
    # Default Super Admin
    cur.execute("SELECT COUNT(*) FROM users WHERE role='SUPER_ADMIN'")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username,password,role,department_code) VALUES (?,?,?,?)", 
                    ("admin","admin123","SUPER_ADMIN", "ALL"))
    conn.commit()
    conn.close()

init_db()

# --- HELPER: DATE FILTERING LOGIC ---
def filter_by_period(df, period, date_col="lesson_date"):
    if df.empty: return df
    
    df[date_col] = pd.to_datetime(df[date_col])
    today = pd.to_datetime(date.today())
    
    if period == "Today":
        return df[df[date_col].dt.date == today.date()]
    elif period == "This Week":
        start_week = today - timedelta(days=today.weekday())
        return df[df[date_col] >= start_week]
    elif period == "This Month":
        return df[(df[date_col].dt.month == today.month) & (df[date_col].dt.year == today.year)]
    elif period == "Term 1 (Jan-Mar)":
        return df[df[date_col].dt.month.isin([1, 2, 3])]
    elif period == "Term 2 (May-Jul)":
        return df[df[date_col].dt.month.isin([5, 6, 7])]
    elif period == "Term 3 (Sep-Nov)":
        return df[df[date_col].dt.month.isin([9, 10, 11])]
    return df

# --- LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 RVNP Login")
    u = st.text_input("Username", key="login_username")
    p = st.text_input("Password", type="password", key="login_password")
    if st.button("Login", type="primary"):
        df = fetch_df("SELECT * FROM users WHERE username=? AND password=?", (u,p))
        if df.empty:
            st.error("Invalid credentials")
        else:
            st.session_state.logged_in = True
            st.session_state.user = df.iloc[0].to_dict()
            st.rerun()
    st.stop()

user = st.session_state.user
role = user["role"]
user_dept = user["department_code"]

st.title("🏫 RVNP Trainer Attendance System")

# DISPLAY ROLE
if role == "SUPER_ADMIN":
    role_desc = "SUPER ADMIN (Principal)"
elif role == "HOD":
    role_desc = f"HOD - Department of {user_dept}"
else:
    role_desc = "Class Representative"

st.caption(f"**Logged in as:** {role_desc}")

# LOGOUT & MESSAGES
col_lo, col_msg = st.columns([1, 6])
with col_lo:
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()
with col_msg:
    show_message()

st.divider()

# ================= SUPER ADMIN PANEL =================
if role == "SUPER_ADMIN":
    tabs = st.tabs(["👥 Manage HODs", "📈 Global Analytics"])
    
    # 1. MANAGE HODS
    with tabs[0]:
        st.subheader("Create Head of Department (HOD)")
        with st.form("create_hod"):
            col1, col2, col3 = st.columns(3)
            new_u = col1.text_input("Username")
            new_p = col2.text_input("Password", type="password")
            new_dept = col3.selectbox("Assign Department", DEPARTMENTS)
            
            if st.form_submit_button("Create HOD"):
                if not new_u or not new_p:
                    st.session_state.message = ("error", "All fields required")
                else:
                    success, msg = execute(
                        "INSERT OR IGNORE INTO users (username, password, role, department_code) VALUES (?,?,?,?)",
                        (new_u, new_p, "HOD", new_dept)
                    )
                    if success: st.session_state.message = ("success", f"HOD for {new_dept} created.")
                    else: st.session_state.message = ("error", msg)
                st.rerun()
        
        # LIST HODs
        hods = fetch_df("SELECT id, username, department_code FROM users WHERE role='HOD' ORDER BY department_code")
        if not hods.empty:
            hods.insert(0, "S/No", range(1, len(hods)+1))
            st.dataframe(hods.rename(columns={"id": "System Ref"}), hide_index=True, use_container_width=True)
            
            del_id = st.number_input("Enter 'System Ref' to delete HOD", min_value=1, step=1)
            if st.button("Delete HOD"):
                execute("DELETE FROM users WHERE id=?", (del_id,))
                st.session_state.message = ("success", "HOD deleted.")
                st.rerun()

    # 2. GLOBAL ANALYTICS
    with tabs[1]:
        st.subheader("📊 Institution Analysis")
        
        c1, c2 = st.columns(2)
        filter_dept = c1.selectbox("Filter by Department", ["All Departments"] + DEPARTMENTS)
        filter_period = c2.selectbox("Filter by Period", 
            ["All Time", "Today", "This Week", "This Month", "Term 1 (Jan-Mar)", "Term 2 (May-Jul)", "Term 3 (Sep-Nov)"])
        
        # Fetch Data
        if filter_dept == "All Departments":
            df = fetch_df("SELECT * FROM lesson_attendance")
        else:
            df = fetch_df("SELECT * FROM lesson_attendance WHERE department_code=?", (filter_dept,))
            
        # Apply Time Filter
        df = filter_by_period(df, filter_period)
        
        if df.empty:
            st.info("No data found for this selection.")
        else:
            # Metrics
            total = len(df)
            taught = len(df[df['status']=='Taught'])
            rate = round((taught/total)*100, 1) if total > 0 else 0
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Lessons", total)
            m2.metric("Lessons Taught", taught)
            m3.metric("Attendance Rate", f"{rate}%")
            
            # Charts
            st.markdown("##### Attendance Trends")
            df['day'] = pd.to_datetime(df['lesson_date']).dt.date
            daily = df.groupby("day").agg(
                taught=("status", lambda x: (x == "Taught").sum()),
                missed=("status", lambda x: (x == "Not Taught").sum())
            ).reset_index()
            
            fig = px.bar(daily, x="day", y=["taught", "missed"], barmode="stack", 
                         color_discrete_sequence=["#4CAF50", "#F44336"])
            st.plotly_chart(fig, use_container_width=True)

# ================= HOD PANEL =================
elif role == "HOD":
    
    # Helper to manage basic tables
    def manage_table(table_name, col_name, label):
        with st.form(f"add_{table_name}"):
            name = st.text_input(f"New {label} Name").strip().upper()
            if st.form_submit_button(f"Add {label}"):
                if name:
                    success, msg = execute(f"INSERT OR IGNORE INTO {table_name} ({col_name}, department_code) VALUES (?,?)", (name, user_dept))
                    if success: st.session_state.message = ("success", "Added successfully.")
                    else: st.session_state.message = ("error", msg)
                    st.rerun()
        
        data = fetch_df(f"SELECT rowid as id, {col_name} FROM {table_name} WHERE department_code=? ORDER BY {col_name}", (user_dept,))
        if not data.empty:
            data.insert(0, "S/No", range(1, len(data)+1))
            st.dataframe(data.rename(columns={"id": "System Ref"}), hide_index=True, use_container_width=True)
            
            did = st.number_input(f"Enter 'System Ref' to delete {label}", min_value=1, step=1, key=f"del_{table_name}")
            if st.button(f"Delete {label}", key=f"btn_del_{table_name}"):
                # Security check
                check = fetch_df(f"SELECT department_code FROM {table_name} WHERE rowid=?", (did,))
                if not check.empty and check.iloc[0]['department_code'] == user_dept:
                    execute(f"DELETE FROM {table_name} WHERE rowid=?", (did,))
                    st.session_state.message = ("success", "Deleted.")
                    st.rerun()
                else:
                    st.error("Invalid ID or Permission Denied.")

    tabs = st.tabs(["📝 Class Reps", "👨‍🏫 Trainers", "🏫 Classes", "📚 Units", "🔗 Assign Reps", "📥 Import", "📈 Analytics"])
    
    # 1. MANAGE CLASS REPS (Create User)
    with tabs[0]:
        st.subheader("Create Class Rep Accounts")
        with st.form("create_rep"):
            u = st.text_input("Student Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Create Class Rep"):
                if u and p:
                    # CRITICAL: Insert with HOD's department code
                    success, msg = execute("INSERT OR IGNORE INTO users (username, password, role, department_code) VALUES (?,?,?,?)",
                                           (u, p, "CLASS_REP", user_dept))
                    if success: st.session_state.message = ("success", f"User {u} created.")
                    else: st.session_state.message = ("error", msg)
                    st.rerun()
        
        reps = fetch_df("SELECT id, username FROM users WHERE role='CLASS_REP' AND department_code=?", (user_dept,))
        if not reps.empty:
            reps.insert(0, "S/No", range(1, len(reps)+1))
            st.dataframe(reps.rename(columns={"id": "System Ref"}), hide_index=True, use_container_width=True)

    # 2, 3, 4. MANAGE DATA
    with tabs[1]: 
        st.subheader("Manage Trainers")
        manage_table("trainers", "trainer_name", "Trainer")
    with tabs[2]: 
        st.subheader("Manage Classes")
        manage_table("classes", "class_name", "Class")
    with tabs[3]: 
        st.subheader("Manage Units")
        manage_table("units", "unit_name", "Unit")

    # 5. ASSIGN REPS
    with tabs[4]:
        st.subheader("Link Class Reps to Classes")
        # DROPDOWN QUERY FIX: Only show Reps from THIS department
        rep_list = fetch_df("SELECT username FROM users WHERE role='CLASS_REP' AND department_code=?", (user_dept,))["username"].tolist()
        class_list = fetch_df("SELECT class_name FROM classes WHERE department_code=?", (user_dept,))["class_name"].tolist()
        
        if rep_list and class_list:
            with st.form("assign_rep_form"):
                r_sel = st.selectbox("Select Class Rep", rep_list)
                c_sel = st.selectbox("Select Class", class_list)
                if st.form_submit_button("Assign"):
                    success, msg = execute("INSERT OR IGNORE INTO class_rep_assignments (username, class_name, department_code) VALUES (?,?,?)",
                                           (r_sel, c_sel, user_dept))
                    if success: st.session_state.message = ("success", "Assigned successfully.")
                    else: st.session_state.message = ("error", msg)
                    st.rerun()
        
        assignments = fetch_df("SELECT rowid as id, username, class_name FROM class_rep_assignments WHERE department_code=?", (user_dept,))
        if not assignments.empty:
            assignments.insert(0, "S/No", range(1, len(assignments)+1))
            st.dataframe(assignments.rename(columns={"id": "System Ref"}), hide_index=True, use_container_width=True)
            
            del_assign = st.number_input("Enter 'System Ref' to delete assignment", min_value=1, step=1)
            if st.button("Delete Assignment"):
                check = fetch_df("SELECT department_code FROM class_rep_assignments WHERE rowid=?", (del_assign,))
                if not check.empty and check.iloc[0]['department_code'] == user_dept:
                    execute("DELETE FROM class_rep_assignments WHERE rowid=?", (del_assign,))
                    st.session_state.message = ("success", "Deleted.")
                    st.rerun()

    # 6. BULK IMPORT
    with tabs[5]:
        st.subheader("Bulk Import from Excel/CSV")
        st.info("Ensure your file has columns named exactly: **Name**, **Department**")
        st.caption("Once imported, the data will instantly appear in the dropdowns on other tabs.")
        
        target = st.selectbox("Select Target", ["Trainers", "Classes", "Units"])
        upl = st.file_uploader("Upload File", type=["csv", "xlsx"])
        
        if upl:
            try:
                df = pd.read_csv(upl) if upl.name.endswith('.csv') else pd.read_excel(upl)
                if 'Name' in df.columns and 'Department' in df.columns:
                    table_map = {"Trainers": ("trainers", "trainer_name"), "Classes": ("classes", "class_name"), "Units": ("units", "unit_name")}
                    tbl, col = table_map[target]
                    
                    count = 0
                    for _, row in df.iterrows():
                        n = str(row['Name']).strip().upper()
                        d = str(row['Department']).strip()
                        # Strictly import only for this HOD's dept
                        if d == user_dept and n:
                            execute(f"INSERT OR IGNORE INTO {tbl} ({col}, department_code) VALUES (?,?)", (n, d))
                            count += 1
                    
                    st.success(f"Successfully imported {count} records into {user_dept}.")
                else:
                    st.error("Columns 'Name' and 'Department' not found in file.")
            except Exception as e:
                st.error(f"File error: {e}")

    # 7. HOD ANALYTICS
    with tabs[6]:
        st.subheader(f"📊 {user_dept} Analysis")
        f_period = st.selectbox("Filter Period", 
            ["All Time", "Today", "This Week", "This Month", "Term 1 (Jan-Mar)", "Term 2 (May-Jul)", "Term 3 (Sep-Nov)"])
        
        df = fetch_df("SELECT * FROM lesson_attendance WHERE department_code=?", (user_dept,))
        df = filter_by_period(df, f_period)
        
        if df.empty:
            st.info("No records for this period.")
        else:
            total = len(df)
            taught = len(df[df['status']=='Taught'])
            missed = total - taught
            rate = round((taught/total)*100, 1) if total > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total", total)
            c2.metric("Taught", taught)
            c3.metric("Rate", f"{rate}%")
            
            st.markdown("##### Attendance by Day")
            df['day'] = pd.to_datetime(df['lesson_date']).dt.date
            daily = df.groupby("day").agg(
                taught=("status", lambda x: (x == "Taught").sum()),
                missed=("status", lambda x: (x == "Not Taught").sum())
            ).reset_index()
            
            fig = px.bar(daily, x="day", y=["taught", "missed"], barmode="stack", color_discrete_sequence=["#4CAF50", "#F44336"])
            st.plotly_chart(fig, use_container_width=True)

# ================= CLASS REP PANEL =================
elif role == "CLASS_REP":
    
    # 1. GET ASSIGNMENTS
    assignments = fetch_df("SELECT class_name, department_code FROM class_rep_assignments WHERE username=?", (user['username'],))
    
    if assignments.empty:
        st.error("You are not assigned to any class. Please contact your HOD.")
    else:
        dept = assignments.iloc[0]['department_code']
        classes = assignments['class_name'].unique().tolist()
        
        st.subheader(f"📝 Report for {dept}")
        st.info(f"Your Classes: {', '.join(classes)}")
        
        # 2. DROPDOWNS (Filtered by Dept)
        units = fetch_df("SELECT unit_name FROM units WHERE department_code=? ORDER BY unit_name", (dept,))['unit_name'].tolist()
        trainers = fetch_df("SELECT trainer_name FROM trainers WHERE department_code=? ORDER BY trainer_name", (dept,))['trainer_name'].tolist()
        
        if not units or not trainers:
            st.warning("HOD has not added Units or Trainers yet.")
        
        with st.form("report_form", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            ldate = c1.date_input("Date", date.today())
            slot = c2.selectbox("Time Slot", TIME_SLOTS)
            
            cls = st.selectbox("Class", classes)
            
            c3, c4 = st.columns(2)
            unit = c3.selectbox("Unit", units)
            trn = c4.selectbox("Trainer", trainers)
            
            status = st.radio("Status", ["Taught", "Not Taught"], horizontal=True)
            reason = st.selectbox("Reason (if Not Taught)", ["Trainer Absent", "Trainer Late", "Notes Given", "Other"]) if status == "Not Taught" else None
            rem = st.text_area("Remarks")
            
            if st.form_submit_button("Submit Report"):
                if unit and trn:
                    success, msg = execute("""
                        INSERT INTO lesson_attendance 
                        (lesson_date, class_name, unit_name, trainer_name, time_slot, status, reason, remarks, reported_by, department_code)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (str(ldate), cls, unit, trn, slot, status, reason, rem, user['username'], dept))
                    
                    if success: st.session_state.message = ("success", "Report Submitted!")
                    else: st.session_state.message = ("error", msg)
                else:
                    st.session_state.message = ("error", "Unit and Trainer required.")
                st.rerun()

st.caption("Rift Valley National Polytechnic Attendance System")