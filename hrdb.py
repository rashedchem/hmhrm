"""Database layer (SQLite) for Steel Plant HR Management System."""
import os
import secrets
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('HR_DATA_DIR') or os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'hr.db')

HASH_METHOD = 'pbkdf2:sha256:600000'

# Department list taken from the "Department List" sheet of the workbook
DEPARTMENTS = [
    ('DEP-01', 'HR & Admin'), ('DEP-02', 'Store'), ('DEP-03', 'Accounts'),
    ('DEP-04', 'Delivery'), ('DEP-05', 'Logistics'), ('DEP-06', 'SMS Production'),
    ('DEP-07', 'SMS CCM'), ('DEP-08', 'SMS Electrical'), ('DEP-09', 'SMS Mechanical'),
    ('DEP-10', 'SMS Quality Control'), ('DEP-11', 'RM Production'),
    ('DEP-12', 'RM Electrical'), ('DEP-13', 'RM Mechanical'),
    ('DEP-14', 'RM Quality Control'),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('director','hr_manager','employee')),
    designation TEXT,
    employee_id TEXT,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    must_change INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    session_ver INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS departments (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    dob TEXT, gender TEXT, department TEXT, designation TEXT,
    worker_category TEXT, employment_type TEXT, join_date TEXT, shift TEXT,
    basic_wage REAL, gross_wage REAL, mobile TEXT, emergency_contact TEXT,
    nid_ref TEXT, notes TEXT,
    status TEXT NOT NULL DEFAULT 'Active',
    last_working_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    payload TEXT NOT NULL,
    employee_id TEXT,
    create_login INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','cancelled')),
    requested_by INTEGER NOT NULL REFERENCES users(id),
    requested_at TEXT NOT NULL,
    decided_by INTEGER REFERENCES users(id),
    decided_at TEXT,
    decision_note TEXT
);
CREATE INDEX IF NOT EXISTS ix_req_status ON requests(status);
CREATE INDEX IF NOT EXISTS ix_req_emp ON requests(employee_id);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    register TEXT NOT NULL,
    employee_id TEXT,
    data TEXT NOT NULL,
    request_id INTEGER REFERENCES requests(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rec_reg ON records(register, employee_id);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    username TEXT,
    ip TEXT,
    action TEXT NOT NULL,
    detail TEXT
);
"""


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.execute('PRAGMA journal_mode=WAL')
    if not conn.execute('SELECT 1 FROM departments LIMIT 1').fetchone():
        conn.executemany('INSERT INTO departments(code,name) VALUES(?,?)', DEPARTMENTS)
    conn.commit()
    conn.close()


def get_secret_key():
    """Random secret key, created once and kept in the data folder."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, 'secret.key')
    if not os.path.exists(path):
        with open(path, 'w') as fh:
            fh.write(secrets.token_hex(32))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    with open(path) as fh:
        return fh.read().strip()


def new_password():
    alphabet = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(12))


def create_user(conn, username, full_name, role, designation='', employee_id=None,
                password=None, must_change=1):
    password = password or new_password()
    conn.execute(
        'INSERT INTO users(username,full_name,role,designation,employee_id,'
        'password_hash,must_change,created_at) VALUES(?,?,?,?,?,?,?,?)',
        (username, full_name, role, designation, employee_id,
         generate_password_hash(password, method=HASH_METHOD), must_change, now()))
    return password


def bootstrap_users():
    """On first run create one Director and one HR Manager with random passwords."""
    conn = connect()
    if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
        conn.close()
        return None
    creds = {}
    creds['director'] = create_user(conn, 'director', 'Director', 'director', 'Director')
    creds['hrmanager'] = create_user(conn, 'hrmanager', 'HR Manager', 'hr_manager', 'HR Manager')
    conn.commit()
    conn.close()
    path = os.path.join(DATA_DIR, 'FIRST_RUN_PASSWORDS.txt')
    with open(path, 'w') as fh:
        fh.write('Temporary first-login passwords (you must change them at first login).\n')
        fh.write('DELETE THIS FILE after both accounts have logged in.\n\n')
        for u, p in creds.items():
            fh.write('username: %s    password: %s\n' % (u, p))
    return creds, path
