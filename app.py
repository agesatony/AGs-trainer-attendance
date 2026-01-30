import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta
import io
import plotly.express as px

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Trainer Lesson Attendance System", layout="wide", page_icon="📊")

DB = "attendance.db"

DEPARTMENTS = ["AGME", "AES", "BCE", "BSD", "ELEC", "HATS", "HAAPS", "LSD", "ICT"]

TIME_SLOTS = [
    "7.30-9.00", "09.00-10.30", "10.30-12.00",
    "12.00-1.30", "1.30-3.00", "3.00-4.30", "4.30-6.00"
]

# ────────────────────────────────────────────────
# DB HELPERS
# ────────────────────────────────────────────────
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def fetch_df(query, params=()):
    conn = get_conn()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def execute(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()

# ────────────────────────────────────────────────
# INIT DATABASE
# ────────────────────────────────────────────────
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
        role TEXT NOT NULL CHECK(role IN ('ADMIN','HOD','CLASS_REP')),
        department_code TEXT,
        FOREIGN KEY(department_code) REFERENCES departments(department_code)
    );

    CREATE TABLE IF NOT EXISTS trainers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trainer_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        UNIQUE(trainer_name, department_code),
        FOREIGN KEY(department_code) REFERENCES departments(department_code)
    );

    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        UNIQUE(class_name, department_code),
        FOREIGN KEY(department_code) REFERENCES departments(department_code)
    );

    CREATE TABLE IF NOT EXISTS units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        UNIQUE(unit_name, department_code),
        FOREIGN KEY(department_code) REFERENCES departments(department_code)
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
        UNIQUE(lesson_date, class_name, unit_name, trainer_name, time_slot),
        FOREIGN KEY(department_code) REFERENCES departments(department_code)
    );

    CREATE TABLE IF NOT EXISTS class_rep_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        class_name TEXT NOT NULL,
        department_code TEXT NOT NULL,
        assigned_at TEXT DEFAULT (datetime('now')),
        UNIQUE(username, class_name, department_code),
        FOREIGN KEY(username) REFERENCES users(username),
        FOREIGN KEY(class_name, department_code) REFERENCES classes(class_name, department_code)
    );
    """)

    # Seed departments
    for code in DEPARTMENTS:
        cur.execute("INSERT OR IGNORE INTO departments VALUES (?,?)", (code, f"Department of {code}"))

    # Default admin
    cur.execute("INSERT OR IGNORE INTO users (username,password,role) VALUES (?,?,?)", ("admin","admin123","ADMIN"))

    conn.commit()
    conn.close()

init_db()

# ────────────────────────────────────────────────
# SESSION STATE & LOGIN
# ────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 Login")
    col1, col2 = st.columns([1, 3])
    with col1:
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", type="primary", key="login_submit"):
            df = fetch_df("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            if df.empty:
                st.error("Invalid credentials")
            else:
                st.session_state.logged_in = True
                st.session_state.user = df.iloc[0].to_dict()
                st.rerun()
    st.stop()

user = st.session_state.user
role = user["role"]
dept = user.get("department_code")

st.title("📊 Trainer Lesson Attendance System")
st.caption(f"**Role:** {role} • **Department:** {dept or 'Institution-wide'} • **User:** {user['username']}")

if st.button("🚪 Logout", key="global_logout"):
    st.session_state.clear()
    st.rerun()

# ────────────────────────────────────────────────
# ADMIN PANEL – Manage entities + assign reps
# ────────────────────────────────────────────────
def manage_entity(table, name_col, display_name):
    prefix = f"admin_{table}"

    st.subheader(f"Manage {display_name}s")

    # Add form
    with st.form(key=f"{prefix}_add_form", clear_on_submit=True):
        name = st.text_input(f"{display_name} Name", key=f"{prefix}_name_input").strip().upper()
        dept_sel = st.selectbox("Department", DEPARTMENTS, key=f"{prefix}_dept_select")
        if st.form_submit_button(f"Add {display_name}", type="primary"):
            if name:
                execute(
                    f"INSERT OR IGNORE INTO {table} ({name_col}, department_code) VALUES (?, ?)",
                    (name, dept_sel)
                )
                st.success(f"{display_name} added")
                st.rerun()
            else:
                st.error("Name is required")

    # List + Delete
    df_list = fetch_df(f"""
        SELECT rowid AS RowID,
               {name_col} AS Name,
               department_code AS Department
        FROM {table}
        ORDER BY Name
    """)

    if df_list.empty:
        st.info(f"No {display_name.lower()}s added yet.")
    else:
        st.dataframe(df_list, use_container_width=True, hide_index=True, key=f"{prefix}_data_table")

        del_rowid = st.number_input(
            "RowID to delete (see table above)",
            min_value=1,
            step=1,
            format="%d",
            key=f"{prefix}_delete_id"
        )
        if st.button("🗑 Delete record", type="primary", key=f"{prefix}_delete_btn"):
            execute(f"DELETE FROM {table} WHERE rowid = ?", (del_rowid,))
            st.success(f"RowID {del_rowid} deleted")
            st.rerun()

if role == "ADMIN":
    st.divider()
    st.subheader("🛠 Admin Panel")

    tab_users, tab_trainers, tab_classes, tab_units, tab_assign = st.tabs(
        ["Users", "Trainers", "Classes", "Units", "Assign Class Reps"]
    )

    with tab_users:
        with st.form("add_user_form", clear_on_submit=True):
            u = st.text_input("Username", key="admin_add_username")
            p = st.text_input("Password", type="password", key="admin_add_password")
            r = st.selectbox("Role", ["HOD", "CLASS_REP"], key="admin_add_role")
            d = st.selectbox("Department", [""] + DEPARTMENTS, key="admin_add_dept")
            dval = None if d == "" else d
            if st.form_submit_button("Add User"):
                execute("INSERT OR IGNORE INTO users(username,password,role,department_code) VALUES(?,?,?,?)",
                        (u, p, r, dval))
                st.success("User added")
                st.rerun()
        st.dataframe(fetch_df("SELECT username, role, department_code FROM users"), key="users_table")

    with tab_trainers: manage_entity("trainers", "trainer_name", "Trainer")
    with tab_classes:  manage_entity("classes",  "class_name",  "Class")
    with tab_units:    manage_entity("units",    "unit_name",   "Unit")

    with tab_assign:
        st.subheader("Assign Class Reps to Classes")
        reps = fetch_df("SELECT username FROM users WHERE role='CLASS_REP'")["username"].tolist()
        cls_df = fetch_df("SELECT class_name, department_code FROM classes")

        if not reps or cls_df.empty:
            st.warning("Create CLASS_REP users and classes first.")
        else:
            with st.form("assign_rep_form"):
                rep_user = st.selectbox("Class Representative", reps, key="assign_rep_user")
                class_option = st.selectbox(
                    "Class to assign",
                    [f"{row['class_name']} ({row['department_code']})" for _, row in cls_df.iterrows()],
                    key="assign_class_option"
                )
                if st.form_submit_button("Assign Class"):
                    class_name, dept_code = class_option.rsplit(" (", 1)
                    dept_code = dept_code[:-1]
                    execute(
                        "INSERT OR IGNORE INTO class_rep_assignments (username, class_name, department_code) VALUES (?,?,?)",
                        (rep_user, class_name.strip(), dept_code)
                    )
                    st.success(f"{rep_user} assigned to {class_name}")
                    st.rerun()

            st.markdown("**Current Assignments**")
            st.dataframe(
                fetch_df("SELECT username, class_name, department_code, assigned_at FROM class_rep_assignments"),
                use_container_width=True,
                key="assignments_table"
            )

# ────────────────────────────────────────────────
# CLASS REP SECTION
# ────────────────────────────────────────────────
if role == "CLASS_REP":
    st.divider()
    st.subheader("📝 Report Lesson Attendance")

    assigned = fetch_df("""
        SELECT class_name, department_code 
        FROM class_rep_assignments 
        WHERE username = ?
    """, (user["username"],))

    if assigned.empty:
        st.error("You are not assigned to any class yet. Contact the administrator.")
        st.stop()

    assigned_classes = assigned["class_name"].tolist()
    dept = assigned.iloc[0]["department_code"]

    st.info(f"Your assigned class(es): {', '.join(assigned_classes)}")

    units = fetch_df("SELECT unit_name FROM units WHERE department_code = ?", (dept,))["unit_name"].tolist()
    trainers = fetch_df("SELECT trainer_name FROM trainers WHERE department_code = ?", (dept,))["trainer_name"].tolist()

    if not (units and trainers):
        st.warning("No units or trainers configured for your department yet.")
        st.stop()

    with st.form("lesson_report_form", clear_on_submit=True):
        col_date, col_slot = st.columns([3, 2])
        lesson_date = col_date.date_input("Lesson Date", value=date.today(), key="rep_date")
        time_slot = col_slot.selectbox("Time Slot", TIME_SLOTS, key="rep_time_slot")

        class_choice = st.selectbox("Class", assigned_classes, key="rep_class_select")

        col_u, col_t = st.columns(2)
        unit_name = col_u.selectbox("Unit", units, key="rep_unit")
        trainer_name = col_t.selectbox("Trainer", trainers, key="rep_trainer")

        status = st.radio("Lesson Status", ["Taught", "Not Taught"], horizontal=True, key="rep_status")

        reason = None
        if status == "Not Taught":
            reason_options = ["Trainer Absent", "Trainer Late", "Notes given", "CAT given", "Other"]
            reason = st.selectbox("Reason", reason_options, key="rep_reason_select")

        remarks = st.text_area("Remarks / Additional Notes", height=100, key="rep_remarks")

        if st.form_submit_button("Submit Report", type="primary", use_container_width=True):
            execute("""
                INSERT OR IGNORE INTO lesson_attendance
                (lesson_date, class_name, unit_name, trainer_name, time_slot, status, reason, remarks, reported_by, department_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(lesson_date),
                class_choice,
                unit_name,
                trainer_name,
                time_slot,
                status,
                reason,
                remarks.strip() or None,
                user["username"],
                dept
            ))
            st.success("Lesson report submitted successfully")
            st.rerun()

# ────────────────────────────────────────────────
# DASHBOARD – HOD & ADMIN with charts
# ────────────────────────────────────────────────
if role in ["HOD", "ADMIN"]:
    st.divider()
    st.subheader("📈 Attendance Dashboard & Analytics")

    # Department
    if role == "ADMIN":
        selected_dept = st.selectbox("Department", ["All Departments"] + DEPARTMENTS, key="dash_dept")
        dept_where = "" if selected_dept == "All Departments" else "department_code = ?"
        dept_params = () if selected_dept == "All Departments" else (selected_dept,)
    else:
        selected_dept = dept
        dept_where = "department_code = ?"
        dept_params = (dept,)

    # Time filter
    period = st.radio(
        "Period",
        ["This month", "Today", "This week", "This year", "All time", "Custom range"],
        horizontal=True,
        index=0,
        key="period_radio"
    )

    today = date.today()
    date_from = date_to = None

    if period == "This month":
        date_from = today.replace(day=1)
        date_to = today
    elif period == "Today":
        date_from = date_to = today
    elif period == "This week":
        date_from = today - timedelta(days=today.weekday())
        date_to = today
    elif period == "This year":
        date_from = date(today.year, 1, 1)
        date_to = today
    elif period == "Custom range":
        c1, c2 = st.columns(2)
        date_from = c1.date_input("From", today - timedelta(days=30))
        date_to   = c2.date_input("To", today)

    # Additional filters
    with st.expander("Filter by Trainer / Unit / Class"):
        f1, f2, f3 = st.columns(3)

        trainers_avail = fetch_df(f"SELECT DISTINCT trainer_name FROM lesson_attendance {dept_where}", dept_params)["trainer_name"].tolist()
        sel_trainers = f1.multiselect("Trainers", trainers_avail, key="filter_trainer")

        units_avail = fetch_df(f"SELECT DISTINCT unit_name FROM lesson_attendance {dept_where}", dept_params)["unit_name"].tolist()
        sel_units = f2.multiselect("Units", units_avail, key="filter_unit")

        classes_avail = fetch_df(f"SELECT DISTINCT class_name FROM lesson_attendance {dept_where}", dept_params)["class_name"].tolist()
        sel_classes = f3.multiselect("Classes", classes_avail, key="filter_class")

    # Build WHERE clause
    where = []
    params = []

    if dept_where:
        where.append(dept_where)
        params += dept_params

    if date_from:
        where.append("lesson_date >= ?")
        params.append(str(date_from))
    if date_to:
        where.append("lesson_date <= ?")
        params.append(str(date_to))

    if sel_trainers:
        where.append(f"trainer_name IN ({','.join('?'*len(sel_trainers))})")
        params += sel_trainers
    if sel_units:
        where.append(f"unit_name IN ({','.join('?'*len(sel_units))})")
        params += sel_units
    if sel_classes:
        where.append(f"class_name IN ({','.join('?'*len(sel_classes))})")
        params += sel_classes

    where_str = "WHERE " + " AND ".join(where) if where else ""

    df = fetch_df(f"SELECT * FROM lesson_attendance {where_str} ORDER BY lesson_date DESC", tuple(params))

    if df.empty:
        st.info("No records match the selected filters.")
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

        # Prepare data for charts
        df["lesson_date"] = pd.to_datetime(df["lesson_date"])
        df["day"]   = df["lesson_date"].dt.date
        df["week"]  = df["lesson_date"].dt.isocalendar().week.astype(str)
        df["month"] = df["lesson_date"].dt.to_period("M").astype(str)

        group_level = st.radio("Group trend by", ["Daily", "Weekly", "Monthly"], horizontal=True, key="group_level")

        group_col = {"Daily": "day", "Weekly": "week", "Monthly": "month"}[group_level]

        grouped = df.groupby(group_col).agg(
            total=("id", "count"),
            taught=("status", lambda x: (x == "Taught").sum()),
            missed=("status", lambda x: (x == "Not Taught").sum())
        ).reset_index()

        grouped["rate"] = grouped["taught"] / grouped["total"] * 100

        # Line chart - attendance rate trend
        fig_line = px.line(
            grouped,
            x=group_col,
            y="rate",
            title=f"Attendance Rate Trend ({group_level})",
            labels={group_col: group_level, "rate": "Attendance %"},
            markers=True
        )
        fig_line.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig_line, use_container_width=True)

        # Stacked bar - taught vs missed
        fig_bar = px.bar(
            grouped,
            x=group_col,
            y=["taught", "missed"],
            title=f"Taught vs Missed Lessons per {group_level}",
            barmode="stack",
            color_discrete_sequence=["#4CAF50", "#F44336"]
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Heatmap - taught lessons intensity
        fig_heat = px.density_heatmap(
            df,
            x="lesson_date",
            y="time_slot",
            title="Heatmap of Lessons Taught by Time Slot & Date",
            color_continuous_scale="YlGnBu"
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        # Pie - reasons for missed
        if missed > 0:
            reasons = df[df["status"] == "Not Taught"]["reason"].value_counts().reset_index()
            reasons.columns = ["Reason", "Count"]
            fig_pie = px.pie(
                reasons,
                values="Count",
                names="Reason",
                title="Reasons for Lessons Not Taught",
                hole=0.4
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # Raw data + export
        st.dataframe(df, use_container_width=True, key="raw_data_table")

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, "attendance_export.csv", "text/csv")

st.caption("Trainer Lesson Attendance System • Rift Valley National Polytechnic • 2026")