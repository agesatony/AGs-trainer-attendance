import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
import plotly.express as px
import os

# CONFIG
st.set_page_config(page_title="Rift Valley National Polytechnic Attendance", layout="wide", page_icon="🏫")

# --- DATA PERSISTENCE FIX ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "attendance.db")
# -----------------------------

DEPARTMENTS = ["AGME", "AES", "BCE", "BSD", "ELEC", "HATS", "HAAPS", "LSD", "ICT"]

TIME_SLOTS = [
    "7.30-9.00", "09.00-10.30", "10.30-12.00",
    "12.00-1.30", "1.30-3.00", "3.00-4.30", "4.30-6.00"
]

# SESSION STATE MANAGEMENT
if "message" not in st.session_state:
    st.session_state.message = None

def show_message():
    """Display and clear the message from the previous run"""
    if st.session_state.message:
        type_, text = st.session_state.message
        if type_ == "success":
            st.success(text)
        elif type_ == "error":
            st.error(text)
        elif type_ == "warning":
            st.warning(text)
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
        return False, "Duplicate Entry: This record already exists."
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
    CREATE TABLE IF NOT EXISTS departments (
        department_code TEXT PRIMARY KEY,
        department_name TEXT
    );

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

    for code in DEPARTMENTS:
        cur.execute("INSERT OR IGNORE INTO departments VALUES (?,?)", (code, f"Department of {code}"))

    # Create Default Super Admin (Principal)
    cur.execute("SELECT COUNT(*) FROM users WHERE role='SUPER_ADMIN'")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username,password,role,department_code) VALUES (?,?,?,?)", 
                    ("admin","admin123","SUPER_ADMIN", "ALL"))

    conn.commit()
    conn.close()

init_db()

# LOGIN
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 RVNP Login")
    u = st.text_input("Username", key="login_username")
    p = st.text_input("Password", type="password", key="login_password")
    if st.button("Login", type="primary", key="login_button"):
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

# HEADER INFO
if role == "SUPER_ADMIN":
    role_display = "SUPER ADMIN (Principal)"
elif role == "HOD":
    role_display = f"HOD - Department of {user_dept}"
else:
    role_display = "Class Representative"

st.caption(f"**Role:** {role_display} • **User:** {user['username']}")

col_logout, col_msg = st.columns([1, 6])
with col_logout:
    if st.button("Logout", key="global_logout"):
        st.session_state.clear()
        st.rerun()
with col_msg:
    show_message()

# HELPER: Manage Entity (Trainer/Class/Unit) - Adapted for HOD vs Super Admin
def manage_entity(table, name_col, display_name):
    prefix = f"manage_{table}_"
    st.subheader(f"Manage {display_name}s")

    # ADD FORM
    with st.form(key=f"{prefix}add_form", clear_on_submit=True):
        name_input = st.text_input(f"{display_name} Name", key=f"{prefix}name_input")
        
        # Dept Selection Logic
        if role == "SUPER_ADMIN":
            dept = st.selectbox("Department", DEPARTMENTS, key=f"{prefix}dept_select")
        else:
            # HOD is locked to their department
            st.markdown(f"**Department:** {user_dept}")
            dept = user_dept
        
        if st.form_submit_button(f"Add {display_name}", type="primary"):
            name = name_input.strip().upper()
            if not name:
                st.session_state.message = ("error", "Name cannot be empty.")
                st.rerun()
            else:
                success, msg = execute(f"INSERT OR IGNORE INTO {table} ({name_col}, department_code) VALUES (?,?)", (name, dept))
                if success:
                    st.session_state.message = ("success", f"{display_name} '{name}' added.")
                else:
                    st.session_state.message = ("error", msg)
                st.rerun()

    # LIST DATA (Filtered for HOD)
    if role == "SUPER_ADMIN":
        query = f"SELECT rowid AS ID, {name_col} AS Name, department_code AS Dept FROM {table} ORDER BY department_code, {name_col}"
        df_list = fetch_df(query)
    else:
        query = f"SELECT rowid AS ID, {name_col} AS Name, department_code AS Dept FROM {table} WHERE department_code=? ORDER BY {name_col}"
        df_list = fetch_df(query, (user_dept,))
    
    if df_list.empty:
        st.info("No records yet")
    else:
        df_list.insert(0, "No.", range(1, len(df_list) + 1))
        st.dataframe(df_list, use_container_width=True, hide_index=True)
        
        col_del, _ = st.columns([1, 2])
        with col_del:
            st.caption("Enter ID to delete:")
            del_id = st.number_input("ID", min_value=1, step=1, key=f"{prefix}del_input")
            if st.button("Delete Record", type="primary", key=f"{prefix}del_btn"):
                # Safety check for HOD deleting other dept records
                if role == "HOD":
                    check = fetch_df(f"SELECT department_code FROM {table} WHERE rowid=?", (del_id,))
                    if not check.empty and check.iloc[0]['department_code'] != user_dept:
                        st.session_state.message = ("error", "You cannot delete records from other departments.")
                        st.rerun()

                execute(f"DELETE FROM {table} WHERE rowid = ?", (del_id,))
                st.session_state.message = ("success", "Record deleted.")
                st.rerun()

# --- ADMIN / HOD PANELS ---
if role in ["SUPER_ADMIN", "HOD"]:
    st.divider()
    st.subheader(f"🛠 {role_display} Panel")

    tabs = st.tabs(["Users & HODs", "Trainers", "Classes", "Units", "Assign Reps", "Bulk Import", "Backup"])

    # 1. USERS TAB
    with tabs[0]:
        st.subheader("User Management")
        
        # Add User Form
        with st.form("add_user_form", clear_on_submit=True):
            col_u, col_p, col_r = st.columns(3)
            u_input = col_u.text_input("Username")
            p_input = col_p.text_input("Password", type="password")
            
            # Role Selection Logic
            if role == "SUPER_ADMIN":
                role_select = col_r.selectbox("Role", ["HOD", "CLASS_REP", "SUPER_ADMIN"])
                dept_select = st.selectbox("Department (For HOD/Rep)", DEPARTMENTS)
            else:
                # HOD can only add Class Reps for their dept
                st.write("**Role:** CLASS_REP")
                role_select = "CLASS_REP"
                st.write(f"**Department:** {user_dept}")
                dept_select = user_dept

            if st.form_submit_button("Create User"):
                u = u_input.strip()
                p = p_input.strip()
                
                if not u or not p:
                    st.session_state.message = ("error", "Username and Password required.")
                else:
                    # Logic: If Super Admin creating Super Admin, dept is ALL
                    final_dept = "ALL" if role_select == "SUPER_ADMIN" else dept_select
                    
                    success, msg = execute("INSERT OR IGNORE INTO users(username,password,role,department_code) VALUES(?,?,?,?)", 
                                           (u, p, role_select, final_dept))
                    if success: st.session_state.message = ("success", f"User '{u}' created as {role_select}.")
                    else: st.session_state.message = ("error", msg)
                st.rerun()

        # List Users
        if role == "SUPER_ADMIN":
            users_df = fetch_df("SELECT id, username, role, department_code FROM users ORDER BY role, department_code")
        else:
            users_df = fetch_df("SELECT id, username, role, department_code FROM users WHERE department_code=? AND role='CLASS_REP'", (user_dept,))

        if not users_df.empty:
            users_df.insert(0, "No.", range(1, len(users_df) + 1))
            st.dataframe(users_df, hide_index=True, use_container_width=True)
            
            st.divider()
            col_d1, _ = st.columns([1,3])
            with col_d1:
                del_user_id = st.number_input("User ID to Delete", min_value=1, step=1, key="del_user_input")
                if st.button("Delete User", type="primary"):
                    # Prevent self-delete
                    current_id = fetch_df("SELECT id FROM users WHERE username=?", (user['username'],)).iloc[0]['id']
                    if del_user_id == current_id:
                        st.session_state.message = ("error", "Cannot delete your own account.")
                    else:
                        execute("DELETE FROM users WHERE id = ?", (del_user_id,))
                        st.session_state.message = ("success", "User deleted.")
                    st.rerun()

    # 2-4. ENTITY MANAGEMENT
    with tabs[1]: manage_entity("trainers", "trainer_name", "Trainer")
    with tabs[2]: manage_entity("classes", "class_name", "Class")
    with tabs[3]: manage_entity("units", "unit_name", "Unit")

    # 5. ASSIGN REPS
    with tabs[4]:
        st.subheader("Assign Class Reps to Classes")
        
        # Filter Lists based on Role
        if role == "SUPER_ADMIN":
            reps = fetch_df("SELECT username FROM users WHERE role='CLASS_REP'")["username"].tolist()
            cls_df = fetch_df("SELECT class_name, department_code FROM classes")
        else:
            reps = fetch_df("SELECT username FROM users WHERE role='CLASS_REP' AND department_code=?", (user_dept,))["username"].tolist()
            cls_df = fetch_df("SELECT class_name, department_code FROM classes WHERE department_code=?", (user_dept,))

        if reps and not cls_df.empty:
            with st.form("assign_form"):
                rep = st.selectbox("Select Class Rep", reps, key="assign_rep")
                cl_options = [f"{r['class_name']} ({r['department_code']})" for _, r in cls_df.iterrows()]
                cl = st.selectbox("Select Class", cl_options, key="assign_class")
                
                if st.form_submit_button("Assign"):
                    cl_name, d_code = cl.rsplit(" (", 1)
                    d_code = d_code[:-1]
                    success, msg = execute("INSERT OR IGNORE INTO class_rep_assignments (username, class_name, department_code) VALUES (?,?,?)",
                            (rep, cl_name.strip(), d_code))
                    if success: st.session_state.message = ("success", "Rep assigned.")
                    else: st.session_state.message = ("error", msg)
                    st.rerun()
        
        # View Assignments
        if role == "SUPER_ADMIN":
            assign_df = fetch_df("SELECT rowid as ID, * FROM class_rep_assignments")
        else:
            assign_df = fetch_df("SELECT rowid as ID, * FROM class_rep_assignments WHERE department_code=?", (user_dept,))
            
        if not assign_df.empty:
            st.dataframe(assign_df, use_container_width=True, hide_index=True)
            del_assign_id = st.number_input("Assignment ID to Delete", min_value=1, step=1, key="del_assign")
            if st.button("Delete Assignment", type="primary"):
                execute("DELETE FROM class_rep_assignments WHERE rowid=?", (del_assign_id,))
                st.session_state.message = ("success", "Assignment deleted.")
                st.rerun()

    # 6. IMPORT
    with tabs[5]:
        st.subheader("Bulk Import Data")
        entity = st.selectbox("Import into", ["Trainers", "Classes", "Units"])
        file = st.file_uploader("CSV/Excel (Columns: Name, Department)", type=["csv","xlsx"])
        if file:
            try:
                df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                if 'Name' in df.columns and 'Department' in df.columns:
                    table_map = {"Trainers": "trainers", "Classes": "classes", "Units": "units"}
                    table = table_map[entity]
                    col_map = {"Trainers": "trainer_name", "Classes": "class_name", "Units": "unit_name"}
                    col = col_map[entity]
                    
                    count = 0
                    for _, row in df.iterrows():
                        n = str(row['Name']).strip().upper()
                        d = str(row['Department']).strip()
                        
                        # HOD Security Check
                        if role == "HOD" and d != user_dept:
                            continue # Skip rows not in HOD's dept

                        if n and d in DEPARTMENTS:
                            execute(f"INSERT OR IGNORE INTO {table} ({col}, department_code) VALUES (?,?)", (n, d))
                            count += 1
                    st.success(f"Imported {count} records")
                else:
                    st.error("File must have columns: Name, Department")
            except Exception as e:
                st.error(f"Error: {e}")

    # 7. BACKUP
    with tabs[6]:
        if os.path.exists(DB):
            with open(DB, "rb") as f:
                st.download_button("Download Database Backup", f, "attendance_backup.db", "application/octet-stream")

# --- CLASS REP INTERFACE ---
if role == "CLASS_REP":
    st.divider()
    st.subheader("📝 Report Lesson Attendance")

    assigned = fetch_df("SELECT class_name, department_code FROM class_rep_assignments WHERE username=?", (user["username"],))
    
    if assigned.empty:
        st.error("You have not been assigned a class yet. Please contact your HOD.")
    else:
        dept = assigned.iloc[0]["department_code"]
        classes = assigned["class_name"].unique().tolist()
        
        st.markdown(f"### 🏛 Department of {dept}")
        st.info(f"**Assigned Classes:** {', '.join(classes)}")
        
        # Filter Lists
        units_df = fetch_df("SELECT DISTINCT unit_name FROM units WHERE department_code = ? ORDER BY unit_name ASC", (dept,))
        units = units_df["unit_name"].tolist() if not units_df.empty else []
        
        trainers_df = fetch_df("SELECT DISTINCT trainer_name FROM trainers WHERE department_code = ? ORDER BY trainer_name ASC", (dept,))
        trainers = trainers_df["trainer_name"].tolist() if not trainers_df.empty else []

        with st.form("rep_form", clear_on_submit=True):
            col1, col2 = st.columns([3,2])
            ldate = col1.date_input("Date", date.today(), key="rep_date")
            slot = col2.selectbox("Slot", TIME_SLOTS, key="rep_slot")

            cls = st.selectbox("Class", classes, key="rep_class")

            col3, col4 = st.columns(2)
            unit = col3.selectbox("Unit", units, key="rep_unit")
            trainer = col4.selectbox("Trainer", trainers, key="rep_trainer")

            status = st.radio("Status", ["Taught", "Not Taught"], horizontal=True, key="rep_status")

            reason = None
            if status == "Not Taught":
                reason = st.selectbox("Reason", ["Trainer Absent", "Trainer Late", "Notes given", "CAT given", "Other"], key="rep_reason")

            remarks = st.text_area("Remarks (Optional)", height=80, key="rep_remarks")

            if st.form_submit_button("Submit Report", type="primary"):
                if not trainer or not unit:
                     st.session_state.message = ("error", "Trainer and Unit required.")
                else:
                    success, msg = execute("""
                        INSERT INTO lesson_attendance
                        (lesson_date, class_name, unit_name, trainer_name, time_slot, status, reason, remarks, reported_by, department_code)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (str(ldate), cls, unit, trainer, slot, status, reason, remarks, user["username"], dept))
                    
                    if success: st.session_state.message = ("success", "✅ Report submitted!")
                    else: st.session_state.message = ("error", f"❌ {msg}")
                st.rerun()

# --- DASHBOARD (ANALYTICS) ---
if role in ["SUPER_ADMIN", "HOD"]:
    st.divider()
    col_dash_title, col_refresh = st.columns([6, 1])
    with col_dash_title:
        st.subheader("📈 Analytics & Charts")
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun()

    # FILTER DATA BASED ON ROLE
    if role == "SUPER_ADMIN":
        df = fetch_df("SELECT * FROM lesson_attendance ORDER BY lesson_date DESC, id DESC")
    else:
        df = fetch_df("SELECT * FROM lesson_attendance WHERE department_code=? ORDER BY lesson_date DESC, id DESC", (user_dept,))

    if df.empty:
        st.info("No attendance records found.")
    else:
        total = len(df)
        taught = len(df[df["status"] == "Taught"])
        missed = total - taught
        rate = round(taught / total * 100, 1) if total > 0 else 0.0

        cols = st.columns(4)
        cols[0].metric("Total Lessons", total)
        cols[1].metric("Taught", taught)
        cols[2].metric("Missed", missed)
        cols[3].metric("Attendance Rate", f"{rate}%")

        st.markdown("### Recent Reports")
        st.dataframe(df[["lesson_date", "time_slot", "class_name", "trainer_name", "status", "reason", "department_code"]], 
                     use_container_width=True, hide_index=True)

        # AGGREGATED STATS
        rank = df.groupby('trainer_name').apply(
            lambda x: pd.Series({
                'Total': len(x),
                'Taught': (x['status'] == 'Taught').sum(),
                'Missed': (x['status'] == 'Not Taught').sum(),
                'Rate (%)': round((x['status'] == 'Taught').sum() / len(x) * 100, 1)
            })
        ).reset_index().sort_values('Rate (%)', ascending=False)

        st.markdown("### Trainer Statistics")
        st.dataframe(rank, use_container_width=True, hide_index=True)

        # CHARTS
        df["lesson_date"] = pd.to_datetime(df["lesson_date"])
        df["day"] = df["lesson_date"].dt.date

        daily = df.groupby("day").agg(
            taught=("status", lambda x: (x == "Taught").sum()),
            missed=("status", lambda x: (x == "Not Taught").sum())
        ).reset_index()

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            fig_bar = px.bar(daily, x="day", y=["taught", "missed"], barmode="stack",
                             title="Taught vs Missed per Day", color_discrete_sequence=["#4CAF50", "#F44336"])
            st.plotly_chart(fig_bar, use_container_width=True)
        
        with col_c2:
            if missed > 0:
                reasons = df[df["status"] == "Not Taught"]["reason"].value_counts().reset_index()
                reasons.columns = ["Reason", "Count"]
                fig_pie = px.pie(reasons, values="Count", names="Reason", title="Reasons for Not Taught")
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No missed lessons to analyze.")

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Full CSV", csv, "attendance.csv", "text/csv")

st.caption("Rift Valley National Polytechnic – Trainer Attendance System")