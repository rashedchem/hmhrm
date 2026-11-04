"""Steel Plant HR Management System - Flask web application.

Roles
  director     Higher Management (Director / Executive Director): approves or rejects
               every submission, manages user accounts, sees the audit log.
  hr_manager   Submits every form (new employee, terminate, leave for a worker,
               attendance, OT, payroll, ...). Nothing takes effect until approved.
  employee     Management employee: read-only own profile + apply for own leave.

Python 3.8+ (works on Windows 7).
"""
import csv
import hmac
import io
import json
import os
import re
import secrets
import time
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import formdefs as fd
import hrdb

DIRECTOR, HR, EMP = 'director', 'hr_manager', 'employee'
ROLE_LABEL = {DIRECTOR: 'Higher Management', HR: 'HR Manager', EMP: 'Management Employee'}

app = Flask(__name__)
hrdb.init_db()
app.config.update(
    SECRET_KEY=hrdb.get_secret_key(),
    SESSION_COOKIE_NAME='hr_session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('HR_HTTPS') == '1',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),   # idle time-out
    MAX_CONTENT_LENGTH=512 * 1024,
)
DUMMY_HASH = generate_password_hash('dummy-password-for-timing', method=hrdb.HASH_METHOD)
MAX_FAILS, LOCK_MINUTES = 5, 15
_ip_fails = {}                                           # simple per-IP throttle


# ------------------------------------------------------------------ plumbing
def get_db():
    if 'db' not in g:
        g.db = hrdb.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def log(action, detail='', username=None):
    db = get_db()
    if username is None:
        username = g.user['username'] if g.get('user') else '-'
    db.execute('INSERT INTO audit_log(ts,username,ip,action,detail) VALUES(?,?,?,?,?)',
               (hrdb.now(), username, request.remote_addr, action, (detail or '')[:500]))
    db.commit()


def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(16)
    return session['_csrf']


app.jinja_env.globals['csrf_token'] = csrf_token
app.jinja_env.globals['ROLE_LABEL'] = ROLE_LABEL
app.jinja_env.globals['KIND_LABEL'] = fd.KIND_LABEL
app.jinja_env.globals['REGISTERS'] = fd.REGISTERS


@app.template_filter('val')
def val_filter(v):
    if v is None or v == '':
        return '-'
    if isinstance(v, float):
        return '{:,.2f}'.format(v)
    if isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 10000:
        return '{:,}'.format(v)
    return v


@app.before_request
def before():
    g.user = None
    uid = session.get('uid')
    if uid:
        u = get_db().execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if u and u['active'] and u['session_ver'] == session.get('sv'):
            g.user = u
            session.permanent = True
        else:
            session.clear()
    if request.method == 'POST':
        sent = request.form.get('_csrf', '')
        if not sent or not hmac.compare_digest(sent, session.get('_csrf', '')):
            abort(400)
    if (g.user and g.user['must_change'] and request.endpoint
            not in ('change_password', 'logout', 'static')):
        return redirect(url_for('change_password'))


@app.after_request
def secure_headers(resp):
    h = resp.headers
    h['Content-Security-Policy'] = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                    "script-src 'self'; frame-ancestors 'none'; "
                                    "form-action 'self'; base-uri 'self'")
    h['X-Content-Type-Options'] = 'nosniff'
    h['X-Frame-Options'] = 'DENY'
    h['Referrer-Policy'] = 'same-origin'
    h['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    if request.endpoint != 'static':
        h['Cache-Control'] = 'no-store, max-age=0'
        h['Pragma'] = 'no-cache'
    if os.environ.get('HR_HTTPS') == '1':
        h['Strict-Transport-Security'] = 'max-age=31536000'
    return resp


def roles(*allowed):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not g.user:
                return redirect(url_for('login', next=request.path))
            if g.user['role'] not in allowed:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def _err(code, title, msg):
    return render_template('error.html', code=code, title=title, msg=msg), code


@app.errorhandler(400)
def e400(_e):
    return _err(400, 'Bad request', 'The form expired or was invalid. Go back, refresh and try again.')


@app.errorhandler(403)
def e403(_e):
    return _err(403, 'Access denied', 'You do not have permission to open this page.')


@app.errorhandler(404)
def e404(_e):
    return _err(404, 'Not found', 'The page or record does not exist.')


@app.errorhandler(413)
def e413(_e):
    return _err(413, 'Too large', 'The submitted data is too large.')


@app.errorhandler(500)
def e500(_e):
    return _err(500, 'Server error', 'Something went wrong. The error has not changed any data.')


# --------------------------------------------------------------------- helpers
def depts():
    return [r['name'] for r in get_db().execute(
        'SELECT name FROM departments WHERE active=1 ORDER BY code')]


def employee_rows(scope='all'):
    sql = 'SELECT * FROM employees'
    if scope == 'active':
        sql += " WHERE status='Active'"
    return get_db().execute(sql + ' ORDER BY employee_id').fetchall()


def get_employee(eid):
    return get_db().execute('SELECT * FROM employees WHERE employee_id=?', (eid,)).fetchone()


def create_request(kind, data, employee_id=None, create_login=0):
    db = get_db()
    cur = db.execute(
        'INSERT INTO requests(kind,title,payload,employee_id,create_login,requested_by,requested_at)'
        ' VALUES(?,?,?,?,?,?,?)',
        (kind, fd.req_title(kind, data), json.dumps(data, ensure_ascii=False),
         employee_id, create_login, g.user['id'], hrdb.now()))
    db.commit()
    rid = cur.lastrowid
    log('SUBMIT', 'request #%d %s' % (rid, kind))
    return rid


def leave_conflict(eid, f, t, exclude_req=None):
    db = get_db()
    for r in db.execute("SELECT data FROM records WHERE register='leave' AND employee_id=?", (eid,)):
        d = json.loads(r['data'])
        if d['from_date'] <= t and d['to_date'] >= f:
            return True
    for r in db.execute("SELECT id,payload FROM requests WHERE kind='leave' AND "
                        "status='pending' AND employee_id=?", (eid,)):
        if exclude_req and r['id'] == exclude_req:
            continue
        d = json.loads(r['payload'])
        if d['from_date'] <= t and d['to_date'] >= f:
            return True
    return False


def leave_balances(eid, year):
    db = get_db()
    bal = {}
    for r in db.execute("SELECT data FROM records WHERE register='leave_ledger' AND employee_id=?", (eid,)):
        d = json.loads(r['data'])
        if int(d.get('year') or 0) != year:
            continue
        b = bal.setdefault(d['leave_type'], {'entitled': 0, 'taken': 0})
        b['entitled'] += (d.get('opening') or 0) + (d.get('accrued') or 0) + (d.get('adjusted') or 0)
    for r in db.execute("SELECT data FROM records WHERE register='leave' AND employee_id=?", (eid,)):
        d = json.loads(r['data'])
        if d['from_date'][:4] == str(year):
            b = bal.setdefault(d['leave_type'], {'entitled': 0, 'taken': 0})
            b['taken'] += d['days']
    for b in bal.values():
        b['closing'] = b['entitled'] - b['taken']
    return bal


def same(a, b):
    if a in (None, '') and b in (None, ''):
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def none_if_blank(v):
    return None if v == '' else v


# ------------------------------------------------------------- authentication
def throttled(ip):
    now = time.time()
    hits = [t for t in _ip_fails.get(ip, []) if now - t < 600]
    _ip_fails[ip] = hits
    return len(hits) >= 25


@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        ip = request.remote_addr
        username = (request.form.get('username') or '').strip()[:64]
        pw = request.form.get('password') or ''
        db = get_db()
        if throttled(ip):
            error = 'Too many attempts from this computer. Please wait 10 minutes.'
        else:
            u = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            now = hrdb.now()
            locked = bool(u and u['locked_until'] and u['locked_until'] > now)
            ok = check_password_hash(u['password_hash'] if u else DUMMY_HASH, pw)
            if u and ok and u['active'] and not locked:
                session.clear()
                session['uid'], session['sv'] = u['id'], u['session_ver']
                session.permanent = True
                db.execute('UPDATE users SET failed_attempts=0, locked_until=NULL, last_login=? '
                           'WHERE id=?', (now, u['id']))
                db.commit()
                log('LOGIN', '', username=u['username'])
                nxt = request.args.get('next', '')
                if re.match(r'^/[A-Za-z0-9_\-/]*$', nxt) and not nxt.startswith('//'):
                    return redirect(nxt)
                return redirect(url_for('dashboard'))
            _ip_fails.setdefault(ip, []).append(time.time())
            if u and not locked:
                fails = u['failed_attempts'] + 1
                until = None
                if fails >= MAX_FAILS:
                    until = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime('%Y-%m-%d %H:%M:%S')
                    fails = 0
                db.execute('UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?',
                           (fails, until, u['id']))
                db.commit()
            log('LOGIN_FAILED', 'user=%s' % username, username=username or '-')
            error = ('Invalid username or password, or the account is locked/disabled. '
                     'After %d wrong attempts an account is locked for %d minutes.'
                     % (MAX_FAILS, LOCK_MINUTES))
    return render_template('login.html', error=error)


@app.route('/logout', methods=['POST'])
def logout():
    if g.user:
        log('LOGOUT')
    session.clear()
    return redirect(url_for('login'))


def password_problem(pw, username):
    if len(pw) < 10:
        return 'Password must be at least 10 characters.'
    if not re.search(r'[A-Za-z]', pw) or not re.search(r'\d', pw):
        return 'Password must contain letters and digits.'
    if pw.lower() == username.lower():
        return 'Password must not be the same as the username.'
    return None


@app.route('/password', methods=['GET', 'POST'])
def change_password():
    if not g.user:
        return redirect(url_for('login'))
    error = None
    if request.method == 'POST':
        cur = request.form.get('current') or ''
        new = request.form.get('new') or ''
        new2 = request.form.get('new2') or ''
        if not check_password_hash(g.user['password_hash'], cur):
            error = 'Current password is incorrect.'
        elif new != new2:
            error = 'The two new passwords do not match.'
        elif new == cur:
            error = 'The new password must be different from the current one.'
        else:
            error = password_problem(new, g.user['username'])
        if not error:
            db = get_db()
            ver = g.user['session_ver'] + 1
            db.execute('UPDATE users SET password_hash=?, must_change=0, session_ver=? WHERE id=?',
                       (generate_password_hash(new, method=hrdb.HASH_METHOD), ver, g.user['id']))
            db.commit()
            session['sv'] = ver
            log('PASSWORD_CHANGED')
            flash('Password changed.', 'ok')
            return redirect(url_for('dashboard'))
    return render_template('password.html', error=error, forced=bool(g.user['must_change']))


# ------------------------------------------------------------------ dashboard
@app.route('/')
@roles(DIRECTOR, HR, EMP)
def dashboard():
    db = get_db()
    today = date.today().isoformat()
    ctx = {}
    if g.user['role'] in (DIRECTOR, HR):
        ctx['active_emps'] = db.execute("SELECT COUNT(*) c FROM employees WHERE status='Active'").fetchone()['c']
        ctx['pending'] = db.execute("SELECT COUNT(*) c FROM requests WHERE status='pending'").fetchone()['c']
        on_leave = 0
        for r in db.execute("SELECT data FROM records WHERE register='leave'"):
            d = json.loads(r['data'])
            if d['from_date'] <= today <= d['to_date']:
                on_leave += 1
        ctx['on_leave'] = on_leave
        ctx['pending_list'] = db.execute(
            "SELECT r.*, u.full_name requester FROM requests r JOIN users u ON u.id=r.requested_by "
            "WHERE r.status='pending' ORDER BY r.id DESC LIMIT 15").fetchall()
        ctx['recent'] = db.execute(
            "SELECT r.*, u.full_name requester FROM requests r JOIN users u ON u.id=r.requested_by "
            "WHERE r.status IN ('approved','rejected') ORDER BY r.decided_at DESC LIMIT 8").fetchall()
        if g.user['role'] == HR:
            ctx['mine_rejected'] = db.execute(
                "SELECT COUNT(*) c FROM requests WHERE requested_by=? AND status='rejected' "
                "AND decided_at > ?", (g.user['id'], (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
            ).fetchone()['c']
    else:
        eid = g.user['employee_id']
        ctx['emp'] = get_employee(eid) if eid else None
        ctx['year'] = date.today().year
        ctx['balances'] = leave_balances(eid, ctx['year']) if eid else {}
        ctx['my_requests'] = db.execute(
            "SELECT r.*, u.full_name requester FROM requests r JOIN users u ON u.id=r.requested_by "
            "WHERE r.requested_by=? OR (r.kind='leave' AND r.employee_id=?) ORDER BY r.id DESC LIMIT 8",
            (g.user['id'], eid)).fetchall()
    return render_template('dashboard.html', **ctx)


# ------------------------------------------------------------------ employees
@app.route('/employees')
@roles(DIRECTOR, HR)
def employees():
    q = (request.args.get('q') or '').strip()[:50]
    dept = request.args.get('dept', '')
    status = request.args.get('status', 'Active')
    sql, args = 'SELECT * FROM employees WHERE 1=1', []
    if q:
        sql += ' AND (employee_id LIKE ? OR full_name LIKE ?)'
        args += ['%' + q + '%'] * 2
    if dept:
        sql += ' AND department=?'
        args.append(dept)
    if status in ('Active', 'Separated'):
        sql += ' AND status=?'
        args.append(status)
    rows = get_db().execute(sql + ' ORDER BY employee_id LIMIT 1000', args).fetchall()
    return render_template('employees.html', rows=rows, q=q, dept=dept, status=status, depts=depts())


@app.route('/employees/export.csv')
@roles(DIRECTOR, HR)
def employees_export():
    rows = employee_rows('all')
    cols = fd.EMP_COLS + ['status', 'last_working_date']
    log('EXPORT', 'employees')
    return csv_response('employees.csv', [fd.label_for('add_employee', c) if c in fd.EMP_COLS
                                          else c.replace('_', ' ').title() for c in cols],
                        [[r[c] for c in cols] for r in rows])


def csv_safe(v):
    s = '' if v is None else str(v)
    if s[:1] in ('=', '+', '-', '@', '\t', '\r'):
        s = "'" + s            # block spreadsheet formula injection
    return s


def csv_response(name, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(c) for c in r])
    data = '\ufeff' + buf.getvalue()        # BOM so Excel reads Bangla text correctly
    return Response(data, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=' + name})


@app.route('/profile')
@roles(EMP, HR, DIRECTOR)
def my_profile():
    eid = g.user['employee_id']
    if not eid:
        flash('Your login is not linked to an employee record. Contact the Director.', 'warn')
        return redirect(url_for('dashboard'))
    return redirect(url_for('employee_view', eid=eid))


@app.route('/employees/<eid>')
@roles(DIRECTOR, HR, EMP)
def employee_view(eid):
    if g.user['role'] == EMP and g.user['employee_id'] != eid:
        abort(403)                                # employees can only see their own profile
    emp = get_employee(eid)
    if not emp:
        abort(404)
    db = get_db()
    year = date.today().year
    leaves = []
    for r in db.execute("SELECT data, created_at FROM records WHERE register='leave' AND "
                        "employee_id=? ORDER BY id DESC LIMIT 50", (eid,)):
        leaves.append(json.loads(r['data']))
    pend = db.execute("SELECT r.*, u.full_name requester FROM requests r JOIN users u ON u.id=r.requested_by "
                      "WHERE r.employee_id=? AND r.status='pending' ORDER BY r.id DESC", (eid,)).fetchall()
    if g.user['role'] == EMP:
        pend = [p for p in pend if p['kind'] == 'leave']
    return render_template('employee_view.html', emp=emp, balances=leave_balances(eid, year),
                           year=year, leaves=leaves, pending=pend)


def form_page(**kw):
    kw.setdefault('errors', {})
    return render_template('form.html', **kw)


@app.route('/employees/new', methods=['GET', 'POST'])
@roles(HR)
def employee_new():
    fields = fd.prepare(fd.EMPLOYEE_FIELDS, depts())
    values, errors = request.args.to_dict(), {}
    if request.method == 'POST':
        values = request.form.to_dict()
        clean, errors = fd.validate(fields, request.form)
        eid = clean.get('employee_id')
        db = get_db()
        if eid and 'employee_id' not in errors:
            if get_employee(eid):
                errors['employee_id'] = 'This Employee ID already exists'
            elif db.execute("SELECT 1 FROM requests WHERE kind='add_employee' AND status='pending' "
                            "AND employee_id=?", (eid,)).fetchone():
                errors['employee_id'] = 'A request to add this ID is already waiting for approval'
        if clean.get('dob') and clean.get('join_date') and 'dob' not in errors \
                and 'join_date' not in errors:
            if clean['dob'] >= clean['join_date']:
                errors['dob'] = 'Date of birth must be before the join date'
            elif clean['dob'] > date.today().isoformat():
                errors['dob'] = 'Date of birth cannot be in the future'
        if not errors:
            rid = create_request('add_employee', clean, eid,
                                 1 if request.form.get('create_login') == '1' else 0)
            flash('Request #%d submitted. The new employee will be added after Higher Management '
                  'approves it.' % rid, 'ok')
            return redirect(url_for('request_view', rid=rid))
    return form_page(title='Add New Employee', bn='নতুন কর্মী', fields=fields, values=values,
                     errors=errors, submit_label='Submit for approval', back_url=url_for('employees'),
                     note='This form is sent to Higher Management. The employee is created only after approval.',
                     show_login_option=True)


@app.route('/employees/<eid>/edit', methods=['GET', 'POST'])
@roles(HR)
def employee_edit(eid):
    emp = get_employee(eid)
    if not emp:
        abort(404)
    if emp['status'] != 'Active':
        flash('Separated employees cannot be edited.', 'warn')
        return redirect(url_for('employee_view', eid=eid))
    fields = fd.prepare([f for f in fd.EMPLOYEE_FIELDS if f['name'] != 'employee_id'], depts())
    values, errors = dict(emp), {}
    if request.method == 'POST':
        values = request.form.to_dict()
        clean, errors = fd.validate(fields, request.form)
        if not errors:
            changes = {k: clean[k] for k in clean if not same(emp[k], clean[k])}
            if not changes:
                errors['full_name'] = 'Nothing was changed'
            else:
                data = {'employee_id': eid, 'full_name': emp['full_name'], 'changes': changes,
                        'old': {k: emp[k] for k in changes}}
                rid = create_request('edit_employee', data, eid)
                flash('Change request #%d submitted for approval.' % rid, 'ok')
                return redirect(url_for('request_view', rid=rid))
    return form_page(title='Edit Employee %s' % eid, bn='কর্মী তথ্য সংশোধন', fields=fields,
                     values=values, errors=errors, submit_label='Submit change for approval',
                     back_url=url_for('employee_view', eid=eid),
                     note='The existing record stays unchanged until the change is approved.')


# ------------------------------------------------------------- generic forms
def register_submit(key, self_emp=None):
    reg = fd.REGISTERS[key]
    db = get_db()
    emps = employee_rows(reg['emp_scope']) if reg['emp'] else []
    if self_emp:
        emps = [e for e in emps if e['employee_id'] == self_emp]
    emp_map = {e['employee_id']: e for e in emps}
    fields = fd.prepare(reg['fields'], depts(), emps)
    values, errors = request.args.to_dict(), {}
    if self_emp:
        values['employee_id'] = self_emp
    if request.method == 'POST':
        form = request.form.to_dict()
        if self_emp:
            form['employee_id'] = self_emp          # server-side enforcement
        values = form
        clean, errors = fd.validate(fields, form, emp_map)
        if not errors:
            derived, derr = fd.compute(key, clean)
            errors.update(derr)
            clean.update(derived)
        if not errors:
            eid = clean.get('employee_id') if reg['emp'] else None
            if key == 'leave' and leave_conflict(eid, clean['from_date'], clean['to_date']):
                errors['from_date'] = 'This employee already has leave (approved or pending) in this period'
            if key == 'separation' and db.execute(
                    "SELECT 1 FROM requests WHERE kind='separation' AND status='pending' "
                    "AND employee_id=?", (eid,)).fetchone():
                errors['employee_id'] = 'A termination request for this employee is already pending'
            if key == 'leave_ledger' and 'year' in clean:
                pass
        if not errors:
            rid = create_request(key, clean, clean.get('employee_id') if reg['emp'] else None)
            flash('Request #%d submitted. It takes effect after Higher Management approval.' % rid, 'ok')
            return redirect(url_for('request_view', rid=rid))
    if self_emp:
        note = 'Your leave application goes to Higher Management for approval.'
    else:
        note = reg.get('help') or 'This form is sent to Higher Management. It takes effect only after approval.'
    return form_page(title=reg['title'], bn=reg['bn'], fields=fields, values=values, errors=errors,
                     submit_label='Submit for approval', note=note,
                     back_url=url_for('dashboard'), leave_calc=(key == 'leave'))


@app.route('/submit/<key>', methods=['GET', 'POST'])
@roles(HR)
def submit_form(key):
    if key not in fd.REGISTERS:
        abort(404)
    return register_submit(key)


@app.route('/leave/apply', methods=['GET', 'POST'])
@roles(HR, EMP)
def leave_apply():
    if g.user['role'] == EMP:
        eid = g.user['employee_id']
        emp = get_employee(eid) if eid else None
        if not emp or emp['status'] != 'Active':
            flash('Your login is not linked to an active employee record.', 'warn')
            return redirect(url_for('dashboard'))
        return register_submit('leave', self_emp=eid)
    return register_submit('leave')


# -------------------------------------------------------------------- requests
def can_see_request(r):
    if g.user['role'] in (DIRECTOR, HR):
        return True
    return r['requested_by'] == g.user['id'] or (
        r['kind'] == 'leave' and r['employee_id'] == g.user['employee_id'])


@app.route('/requests')
@roles(DIRECTOR, HR, EMP)
def requests_list():
    status = request.args.get('status', 'pending' if g.user['role'] == DIRECTOR else 'all')
    sql = ('SELECT r.*, u.full_name requester FROM requests r JOIN users u ON u.id=r.requested_by '
           'WHERE 1=1')
    args = []
    if status in ('pending', 'approved', 'rejected', 'cancelled'):
        sql += ' AND r.status=?'
        args.append(status)
    if g.user['role'] == EMP:
        sql += " AND (r.requested_by=? OR (r.kind='leave' AND r.employee_id=?))"
        args += [g.user['id'], g.user['employee_id']]
    rows = get_db().execute(sql + ' ORDER BY r.id DESC LIMIT 300', args).fetchall()
    return render_template('requests.html', rows=rows, status=status)


@app.route('/requests/<int:rid>')
@roles(DIRECTOR, HR, EMP)
def request_view(rid):
    db = get_db()
    r = db.execute('SELECT r.*, u.full_name requester, d.full_name decider FROM requests r '
                   'JOIN users u ON u.id=r.requested_by LEFT JOIN users d ON d.id=r.decided_by '
                   'WHERE r.id=?', (rid,)).fetchone()
    if not r or not can_see_request(r):
        abort(404)
    data = json.loads(r['payload'])
    if r['kind'] == 'edit_employee':
        rows = [(fd.label_for('edit_employee', k), data['old'].get(k), v)
                for k, v in data['changes'].items()]
        details = None
    else:
        rows, details = None, fd.describe(r['kind'], data)
    return render_template('request_view.html', r=r, details=details, diff=rows)


def create_login_for(db, eid, full_name):
    if db.execute('SELECT 1 FROM users WHERE username=?', (eid,)).fetchone():
        return None
    return hrdb.create_user(db, eid, full_name, EMP, '', eid)


def apply_request(db, r):
    """Apply an approved request to the real data. Runs inside the caller's transaction.
    Returns (ok, message, secret)."""
    d = json.loads(r['payload'])
    kind, now = r['kind'], hrdb.now()
    secret = None
    if kind == 'add_employee':
        if get_employee(d['employee_id']):
            return False, 'Employee ID %s already exists.' % d['employee_id'], None
        cols = fd.EMP_COLS
        db.execute('INSERT INTO employees(%s,status,created_at,updated_at) VALUES(%s,?,?,?)' % (
            ','.join(cols), ','.join('?' * len(cols))),
            [none_if_blank(d.get(c, '')) for c in cols] + ['Active', now, now])
        msg = 'Employee %s added.' % d['employee_id']
        if r['create_login']:
            pw = create_login_for(db, d['employee_id'], d['full_name'])
            if pw:
                secret = 'Login created. Username: %s   Temporary password: %s  (give it to the employee; '
                secret += 'it must be changed at first login and is shown only once)'
                secret = secret % (d['employee_id'], pw)
        return True, msg, secret
    if kind == 'edit_employee':
        emp = get_employee(d['employee_id'])
        if not emp or emp['status'] != 'Active':
            return False, 'Employee is no longer active.', None
        sets = [c for c in d['changes'] if c in fd.EMP_EDITABLE]      # whitelist of column names
        if sets:
            db.execute('UPDATE employees SET %s, updated_at=? WHERE employee_id=?' %
                       ', '.join(c + '=?' for c in sets),
                       [none_if_blank(d['changes'][c]) for c in sets] + [now, d['employee_id']])
        return True, 'Employee %s updated.' % d['employee_id'], None
    if kind == 'separation':
        emp = get_employee(d['employee_id'])
        if not emp or emp['status'] != 'Active':
            return False, 'Employee is not active.', None
        db.execute("UPDATE employees SET status='Separated', last_working_date=?, updated_at=? "
                   "WHERE employee_id=?", (d['last_working_date'], now, d['employee_id']))
        db.execute('UPDATE users SET active=0, session_ver=session_ver+1 WHERE employee_id=?',
                   (d['employee_id'],))
    if kind == 'leave':
        if leave_conflict(d['employee_id'], d['from_date'], d['to_date'], exclude_req=r['id']):
            return False, 'Leave dates now overlap with other leave.', None
        emp = get_employee(d['employee_id'])
        if not emp or emp['status'] != 'Active':
            return False, 'Employee is not active.', None
    db.execute('INSERT INTO records(register,employee_id,data,request_id,created_at) VALUES(?,?,?,?,?)',
               (kind, d.get('employee_id') if fd.REGISTERS[kind]['emp'] else None,
                json.dumps(d, ensure_ascii=False), r['id'], now))
    return True, '%s approved and recorded.' % fd.KIND_LABEL[kind], None


@app.route('/requests/<int:rid>/approve', methods=['POST'])
@roles(DIRECTOR)
def request_approve(rid):
    db = get_db()
    r = db.execute('SELECT * FROM requests WHERE id=?', (rid,)).fetchone()
    if not r:
        abort(404)
    note = (request.form.get('note') or '').strip()[:500]
    try:
        cur = db.execute("UPDATE requests SET status='approved', decided_by=?, decided_at=?, "
                         "decision_note=? WHERE id=? AND status='pending'",
                         (g.user['id'], hrdb.now(), note, rid))
        if cur.rowcount == 0:
            db.rollback()
            flash('This request has already been processed.', 'warn')
            return redirect(url_for('request_view', rid=rid))
        ok, msg, secret = apply_request(db, r)
        if not ok:
            db.rollback()
            flash(msg + ' Reject the request or ask HR to resubmit.', 'error')
            return redirect(url_for('request_view', rid=rid))
        db.commit()
    except Exception:
        db.rollback()
        raise
    log('APPROVE', 'request #%d %s' % (rid, r['kind']))
    flash('Request #%d approved. %s' % (rid, msg), 'ok')
    if secret:
        flash(secret, 'secret')
    return redirect(url_for('request_view', rid=rid))


@app.route('/requests/<int:rid>/reject', methods=['POST'])
@roles(DIRECTOR)
def request_reject(rid):
    db = get_db()
    note = (request.form.get('note') or '').strip()[:500]
    if not note:
        flash('Please write the reason for rejection.', 'error')
        return redirect(url_for('request_view', rid=rid))
    cur = db.execute("UPDATE requests SET status='rejected', decided_by=?, decided_at=?, "
                     "decision_note=? WHERE id=? AND status='pending'",
                     (g.user['id'], hrdb.now(), note, rid))
    db.commit()
    if cur.rowcount == 0:
        flash('This request has already been processed.', 'warn')
    else:
        log('REJECT', 'request #%d' % rid)
        flash('Request #%d rejected.' % rid, 'ok')
    return redirect(url_for('request_view', rid=rid))


@app.route('/requests/<int:rid>/cancel', methods=['POST'])
@roles(HR, EMP)
def request_cancel(rid):
    db = get_db()
    r = db.execute('SELECT * FROM requests WHERE id=?', (rid,)).fetchone()
    if not r or not (g.user['role'] == HR or r['requested_by'] == g.user['id']):
        abort(404)
    cur = db.execute("UPDATE requests SET status='cancelled', decided_by=?, decided_at=?, "
                     "decision_note='Withdrawn by requester' WHERE id=? AND status='pending'",
                     (g.user['id'], hrdb.now(), rid))
    db.commit()
    if cur.rowcount:
        log('CANCEL', 'request #%d' % rid)
        flash('Request #%d withdrawn.' % rid, 'ok')
    else:
        flash('Only pending requests can be withdrawn.', 'warn')
    return redirect(url_for('request_view', rid=rid))


# ------------------------------------------------------------------- registers
@app.route('/registers')
@roles(DIRECTOR, HR)
def registers():
    counts = {r['register']: r['c'] for r in get_db().execute(
        'SELECT register, COUNT(*) c FROM records GROUP BY register')}
    return render_template('registers.html', counts=counts)


def reg_rows(key):
    return [dict(json.loads(r['data']), _id=r['id'], _at=r['created_at'], _req=r['request_id'])
            for r in get_db().execute('SELECT * FROM records WHERE register=? ORDER BY id DESC LIMIT 3000',
                                      (key,))]


@app.route('/registers/<key>')
@roles(DIRECTOR, HR)
def register_list(key):
    if key not in fd.REGISTERS:
        abort(404)
    reg = fd.REGISTERS[key]
    q = (request.args.get('q') or '').strip().lower()[:50]
    rows = reg_rows(key)
    if q:
        rows = [r for r in rows if q in json.dumps(r, ensure_ascii=False).lower()]
    cols = [(c, fd.label_for(key, c)) for c in reg['cols']]
    return render_template('register_list.html', key=key, reg=reg, rows=rows[:500], cols=cols,
                           q=q, total=len(rows))


@app.route('/registers/<key>/export.csv')
@roles(DIRECTOR, HR)
def register_export(key):
    if key not in fd.REGISTERS:
        abort(404)
    reg = fd.REGISTERS[key]
    keys = []
    if reg['emp']:
        keys += ['employee_name', 'department']
    keys += [f['name'] for f in reg['fields'] if f['name'] not in keys]
    keys += [c for c in fd.COMPUTED if c not in keys and any(c in r for r in reg_rows(key)[:50])]
    rows = reg_rows(key)
    log('EXPORT', key)
    return csv_response(key + '.csv', [fd.label_for(key, k) for k in keys] + ['Request #', 'Recorded at'],
                        [[r.get(k, '') for k in keys] + [r['_req'], r['_at']] for r in rows])


# ----------------------------------------------------------------------- users
@app.route('/users')
@roles(DIRECTOR)
def users():
    rows = get_db().execute('SELECT * FROM users ORDER BY role, username').fetchall()
    return render_template('users.html', rows=rows, now=hrdb.now())


@app.route('/users/new', methods=['GET', 'POST'])
@roles(DIRECTOR)
def user_new():
    db = get_db()
    errors, values = {}, {}
    emps = employee_rows('active')
    if request.method == 'POST':
        values = request.form.to_dict()
        username = (values.get('username') or '').strip()
        full_name = (values.get('full_name') or '').strip()
        role = values.get('role')
        eid = (values.get('employee_id') or '').strip() or None
        designation = (values.get('designation') or '').strip()[:60]
        if not re.match(r'^[A-Za-z0-9._\-]{3,30}$', username):
            errors['username'] = 'Use 3-30 letters, digits, dot, dash or underscore'
        elif db.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            errors['username'] = 'This username already exists'
        if not full_name or len(full_name) > 80:
            errors['full_name'] = 'Required (max 80 characters)'
        if role not in (DIRECTOR, HR, EMP):
            errors['role'] = 'Choose a role'
        if eid and not get_employee(eid):
            errors['employee_id'] = 'Unknown employee'
        if role == EMP and not eid:
            errors['employee_id'] = 'A management employee login must be linked to an employee record'
        if not errors:
            pw = hrdb.create_user(db, username, full_name, role, designation,
                                  eid if role == EMP else None)
            db.commit()
            log('USER_CREATED', '%s (%s)' % (username, role))
            flash('User %s created.' % username, 'ok')
            flash('Username: %s   Temporary password: %s  (shown only once; must be changed at first login)'
                  % (username, pw), 'secret')
            return redirect(url_for('users'))
    return render_template('user_form.html', errors=errors, values=values, emps=emps)


@app.route('/users/<int:uid>/toggle', methods=['POST'])
@roles(DIRECTOR)
def user_toggle(uid):
    db = get_db()
    u = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not u:
        abort(404)
    if u['id'] == g.user['id']:
        flash('You cannot disable your own account.', 'warn')
    else:
        new = 0 if u['active'] else 1
        db.execute('UPDATE users SET active=?, session_ver=session_ver+1, failed_attempts=0, '
                   'locked_until=NULL WHERE id=?', (new, uid))
        db.commit()
        log('USER_ENABLED' if new else 'USER_DISABLED', u['username'])
        flash('User %s %s.' % (u['username'], 'enabled' if new else 'disabled'), 'ok')
    return redirect(url_for('users'))


@app.route('/users/<int:uid>/reset', methods=['POST'])
@roles(DIRECTOR)
def user_reset(uid):
    db = get_db()
    u = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not u:
        abort(404)
    pw = hrdb.new_password()
    db.execute('UPDATE users SET password_hash=?, must_change=1, session_ver=session_ver+1, '
               'failed_attempts=0, locked_until=NULL WHERE id=?',
               (generate_password_hash(pw, method=hrdb.HASH_METHOD), uid))
    db.commit()
    log('PASSWORD_RESET', u['username'])
    flash('Password reset for %s.' % u['username'], 'ok')
    flash('Username: %s   Temporary password: %s  (shown only once)' % (u['username'], pw), 'secret')
    return redirect(url_for('users'))


@app.route('/audit-log')
@roles(DIRECTOR)
def audit_log():
    rows = get_db().execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT 500').fetchall()
    return render_template('audit_log.html', rows=rows)


# ------------------------------------------------------------------------ main
def main():
    boot = hrdb.bootstrap_users()
    if boot:
        creds, path = boot
        print('\n' + '=' * 64)
        print(' FIRST RUN - accounts created (passwords saved in):')
        print('   ' + path)
        for u, p in creds.items():
            print('   username: %-10s password: %s' % (u, p))
        print(' You must change each password at first login.')
        print('=' * 64 + '\n')
    host = os.environ.get('HR_HOST', '0.0.0.0')
    port = int(os.environ.get('HR_PORT', '8000'))
    print('HR system running. Open  http://localhost:%d  in Chrome or Firefox.' % port)
    print('Other PCs on the network: http://<this-PC-IP>:%d   (press Ctrl+C to stop)' % port)
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, threaded=True)


if __name__ == '__main__':
    main()
