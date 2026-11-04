"""Form definitions that mirror the sheets of Steel_Plant_HR_Compliance_Registers.xlsx.

Every form is submitted as a *request* and only takes effect after the
Director / Executive Director approves it.

Python 3.8 compatible (Windows 7).
"""
import math
import re
from collections import OrderedDict
from datetime import datetime, date

CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
TEL_RE = re.compile(r'^[0-9+\-\s()]{5,20}$')


def F(name, label, type='text', required=False, options=None, maxlen=200,
      allow_neg=False, help='', pattern=None, pattern_msg='', readonly=False):
    return dict(name=name, label=label, type=type, required=required, options=options,
                maxlen=maxlen, allow_neg=allow_neg, help=help, pattern=pattern,
                pattern_msg=pattern_msg, readonly=readonly)


# ---------------------------------------------------------------- option lists
GENDERS = ['Male', 'Female', 'Other']
EMPLOYMENT_TYPES = ['Permanent', 'Temporary', 'Probation', 'Apprentice', 'Contractor', 'Other']
SHIFTS = ['General', 'A', 'B', 'C', 'Rotational']
LEAVE_TYPES = ['Annual/Earned', 'Casual', 'Sick', 'Festival', 'Compensatory', 'Maternity', 'Other']
INCIDENT_TYPES = ['Injury', 'Near Miss', 'Property Damage', 'Fire', 'Environmental',
                  'Process Safety', 'Other']
INCIDENT_STATUS = ['Open', 'In Progress', 'Closed', 'Overdue']
COMPETENCY = ['Competent', 'Needs Refresher', 'Not Competent', 'Pending']
PERMIT_TYPES = ['Hot Work', 'Electrical', 'Confined Space', 'Work at Height', 'Lifting',
                'General', 'Other']
PERMIT_STATUS = ['Open', 'Active', 'Suspended', 'Closed']
AUDIT_STATUS = ['Not Checked', 'Compliant', 'Non-Compliant', 'Not Applicable', 'In Progress']
EXIT_ROUTES = ['Resignation', 'Termination', 'Dismissal', 'Discharge', 'Retirement',
               'Contract End', 'Death', 'Other']
ABSENCE_CODES = ['', 'Present', 'Absent', 'Leave', 'Weekly Holiday', 'Festival Holiday', 'Other']

AUDIT_ITEMS = [
    ('AUD-001', 'Legal register and licences current'),
    ('AUD-002', 'Employee classification and appointment documents complete'),
    ('AUD-003', 'Worker register/service book/ID maintained'),
    ('AUD-004', 'Minimum wage and wage grade compliance'),
    ('AUD-005', 'Attendance, shift roster and rest breaks compliant'),
    ('AUD-006', 'OT pre-approval, statutory calculation and payment'),
    ('AUD-007', 'Weekly holiday, festival and leave records'),
    ('AUD-008', 'Payroll paid on time; deductions lawful'),
    ('AUD-009', 'Disciplinary process and separation settlements documented'),
    ('AUD-010', 'Maternity/PF/gratuity eligibility and payment reviewed'),
    ('AUD-011', 'Safety risk assessment/JSA updated'),
    ('AUD-012', 'LOTO/PTW and machine guarding checks effective'),
    ('AUD-013', 'Molten-metal, water-ingress and breakout emergency controls'),
    ('AUD-014', 'PPE suitable, issued and used'),
    ('AUD-015', 'First aid, trained coverage and safety record book'),
    ('AUD-016', 'Canteen/rest/water/toilet facilities meet threshold'),
    ('AUD-017', 'Participation/safety committee meetings and action closure'),
    ('AUD-018', 'Contractor documents, induction and wage evidence'),
    ('AUD-019', 'Incident reporting, investigation and corrective action'),
    ('AUD-020', 'Training and competency records current'),
    ('AUD-021', 'Delivery/logistics driver, vehicle and load controls'),
    ('AUD-022', 'QC lab chemical/SDS and waste controls'),
]
AUDIT_OPTIONS = [(a, '%s - %s' % (a, t)) for a, t in AUDIT_ITEMS]

# --------------------------------------------------------------- Employee Master
EMPLOYEE_FIELDS = [
    F('employee_id', 'Employee ID', required=True, maxlen=20,
      pattern=r'^[A-Za-z0-9][A-Za-z0-9\-_/]{1,19}$',
      pattern_msg='Use 2-20 letters, digits, - _ or /'),
    F('full_name', 'Full Name', required=True),
    F('dob', 'Date of Birth', 'date', required=True),
    F('gender', 'Gender', 'select', True, GENDERS),
    F('department', 'Department', 'select', True, 'departments'),
    F('designation', 'Designation', required=True),
    F('worker_category', 'Worker Category', help='e.g. Skilled, Semi-skilled, Unskilled, Clerical'),
    F('employment_type', 'Employment Type', 'select', True, EMPLOYMENT_TYPES),
    F('join_date', 'Join Date', 'date', required=True),
    F('shift', 'Shift', 'select', True, SHIFTS),
    F('basic_wage', 'Basic Wage (BDT)', 'number'),
    F('gross_wage', 'Gross Wage (BDT)', 'number'),
    F('mobile', 'Mobile', 'tel'),
    F('emergency_contact', 'Emergency Contact'),
    F('nid_ref', 'NID / Passport Ref'),
    F('notes', 'Notes', 'textarea'),
]
EMP_COLS = [f['name'] for f in EMPLOYEE_FIELDS]
EMP_EDITABLE = [c for c in EMP_COLS if c != 'employee_id']

# ------------------------------------------------------------------- Registers
# emp_scope: 'active' -> only active employees may be chosen, 'all' -> everyone
REGISTERS = OrderedDict()

REGISTERS['leave'] = dict(
    title='Leave Application', bn='ছুটির আবেদন', emp=True, emp_scope='active',
    fields=[
        F('employee_id', 'Employee', 'employee', True),
        F('leave_type', 'Leave Type', 'select', True, LEAVE_TYPES),
        F('from_date', 'From Date', 'date', True),
        F('to_date', 'To Date', 'date', True),
        F('reason', 'Reason / Remarks', 'textarea'),
    ],
    cols=['employee_id', 'employee_name', 'leave_type', 'from_date', 'to_date', 'days'])

REGISTERS['leave_ledger'] = dict(
    title='Leave Ledger Entry', bn='ছুটির হিসাব', emp=True, emp_scope='active',
    fields=[
        F('employee_id', 'Employee', 'employee', True),
        F('year', 'Leave Year', 'int', True),
        F('leave_type', 'Leave Type', 'select', True, LEAVE_TYPES),
        F('opening', 'Opening Balance (days)', 'number', True),
        F('accrued', 'Accrued (days)', 'number'),
        F('adjusted', 'Adjusted (days, may be negative)', 'number', allow_neg=True),
        F('remarks', 'Remarks', 'textarea'),
    ],
    help='Entitlements are entered by HR and approved by management. No statutory '
         'entitlement is hard-coded; check the current law before entering balances.',
    cols=['employee_id', 'employee_name', 'year', 'leave_type', 'opening', 'accrued', 'adjusted'])

REGISTERS['attendance'] = dict(
    title='Daily Attendance', bn='দৈনিক হাজিরা', emp=True, emp_scope='active',
    fields=[
        F('date', 'Date', 'date', True),
        F('employee_id', 'Employee', 'employee', True),
        F('shift', 'Shift', 'select', False, SHIFTS),
        F('roster_start', 'Roster Start', 'time'),
        F('roster_end', 'Roster End', 'time'),
        F('actual_in', 'Actual In', 'time'),
        F('actual_out', 'Actual Out', 'time'),
        F('break_hrs', 'Break (hrs)', 'number'),
        F('absence_code', 'Absence / Leave Code', 'select', False, ABSENCE_CODES[1:]),
        F('supervisor_approval', 'Supervisor Approval'),
        F('correction_reason', 'Correction Reason', 'textarea'),
    ],
    cols=['date', 'employee_id', 'employee_name', 'shift', 'actual_in', 'actual_out',
          'net_hours', 'late_mins', 'absence_code'])

REGISTERS['ot'] = dict(
    title='Overtime Register', bn='ওভারটাইম রেজিস্টার', emp=True, emp_scope='active',
    fields=[
        F('date', 'Date', 'date', True),
        F('employee_id', 'Employee', 'employee', True),
        F('shift', 'Shift', 'select', False, SHIFTS),
        F('regular_hours', 'Regular Hours', 'number'),
        F('ot_start', 'OT Start', 'time', True),
        F('ot_end', 'OT End', 'time', True),
        F('break_hrs', 'Break (hrs)', 'number'),
        F('reason', 'Reason', 'textarea'),
        F('preapproval_ref', 'Pre-approval Ref'),
        F('approved_by', 'Approved By'),
        F('ot_wage_base', 'OT Wage Base (BDT)', 'number'),
        F('divisor', 'Statutory divisor / method ref (number)', 'number',
          help='Enter the divisor confirmed by your legal review. Nothing is hard-coded.'),
        F('payroll_month', 'Payroll Month', help='e.g. 2026-10'),
    ],
    cols=['date', 'employee_id', 'employee_name', 'ot_start', 'ot_end', 'ot_hours',
          'ot_rate', 'ot_pay', 'payroll_month'])

REGISTERS['payroll'] = dict(
    title='Monthly Payroll', bn='মাসিক বেতন', emp=True, emp_scope='all',
    fields=[
        F('month', 'Month', required=True, help='e.g. 2026-10', maxlen=10,
          pattern=r'^\d{4}-(0[1-9]|1[0-2])$', pattern_msg='Use format YYYY-MM'),
        F('employee_id', 'Employee', 'employee', True),
        F('basic', 'Basic', 'number', True),
        F('house_rent', 'House Rent', 'number'),
        F('medical', 'Medical', 'number'),
        F('other_allowance', 'Other Allowance', 'number'),
        F('ot_pay', 'OT Pay', 'number'),
        F('other_earnings', 'Other Earnings', 'number'),
        F('absence_deduction', 'Absence Deduction', 'number'),
        F('other_deduction', 'Other Lawful Deduction', 'number'),
        F('payment_date', 'Payment Date', 'date'),
        F('bank_ref', 'Bank / EFT Ref'),
        F('payslip_ref', 'Payslip Ref'),
        F('checked_by', 'Checked By'),
    ],
    cols=['month', 'employee_id', 'employee_name', 'gross', 'ot_pay', 'net_pay', 'payment_date'])

REGISTERS['separation'] = dict(
    title='Terminate Employee / Final Settlement', bn='চাকরি অবসান', emp=True,
    emp_scope='active',
    fields=[
        F('employee_id', 'Employee', 'employee', True),
        F('last_working_date', 'Last Working Date', 'date', True),
        F('exit_route', 'Exit Route', 'select', True, EXIT_ROUTES),
        F('reason', 'Reason / Case reference', 'textarea', True),
        F('notice_days', 'Notice Days', 'number'),
        F('notice_pay', 'Notice Pay', 'number'),
        F('wages_due', 'Wages Due', 'number'),
        F('ot_due', 'OT Due', 'number'),
        F('leave_encashment', 'Leave Encashment', 'number'),
        F('compensation', 'Compensation', 'number'),
        F('gratuity', 'Gratuity', 'number'),
        F('pf_benefit', 'PF / Other Benefit', 'number'),
        F('other_dues', 'Other Dues', 'number'),
        F('deductions', 'Deductions (lawful)', 'number'),
        F('hr_checked', 'HR Checked By'),
        F('finance_checked', 'Finance Checked By'),
        F('payment_ref', 'Payment Ref'),
    ],
    help='On approval the employee is marked Separated and the login (if any) is disabled. '
         'Follow the legally required process and notice before submitting.',
    cols=['employee_id', 'employee_name', 'exit_route', 'last_working_date', 'net_settlement'])

REGISTERS['incident'] = dict(
    title='Incident & Near-Miss', bn='দুর্ঘটনা', emp=False,
    fields=[
        F('incident_id', 'Incident ID', required=True, maxlen=30),
        F('date', 'Date', 'date', True),
        F('time', 'Time', 'time'),
        F('department', 'Department', 'select', True, 'departments'),
        F('location', 'Location'),
        F('type', 'Type', 'select', True, INCIDENT_TYPES),
        F('persons', 'Person(s) involved'),
        F('description', 'Description', 'textarea', True),
        F('injury', 'Injury / Damage'),
        F('immediate_action', 'Immediate Action', 'textarea'),
        F('root_cause', 'Root Cause', 'textarea'),
        F('corrective_action', 'Corrective Action', 'textarea'),
        F('owner', 'Owner'),
        F('due_date', 'Due Date', 'date'),
        F('status', 'Status', 'select', True, INCIDENT_STATUS),
        F('close_date', 'Close Date', 'date'),
        F('authority_ref', 'Reported To Authority Ref'),
    ],
    cols=['incident_id', 'date', 'department', 'type', 'persons', 'status'])

REGISTERS['ppe'] = dict(
    title='PPE Issue', bn='সুরক্ষা সরঞ্জাম', emp=True, emp_scope='active',
    fields=[
        F('date', 'Date', 'date', True),
        F('employee_id', 'Employee', 'employee', True),
        F('ppe_item', 'PPE Item', required=True),
        F('size_spec', 'Size / Spec'),
        F('qty', 'Qty', 'number', True),
        F('condition', 'Condition'),
        F('training_demo', 'Training / Demo'),
        F('issued_by', 'Issued By'),
        F('employee_sign', 'Employee Sign / Ref'),
        F('replacement_due', 'Replacement Due', 'date'),
        F('remarks', 'Remarks', 'textarea'),
    ],
    cols=['date', 'employee_id', 'employee_name', 'ppe_item', 'qty', 'replacement_due'])

REGISTERS['training'] = dict(
    title='Training & Competency', bn='প্রশিক্ষণ', emp=True, emp_scope='active',
    fields=[
        F('date', 'Date', 'date', True),
        F('employee_id', 'Employee', 'employee', True),
        F('topic', 'Training Topic', required=True),
        F('trainer', 'Trainer'),
        F('duration', 'Duration (hrs)', 'number'),
        F('assessment', 'Assessment'),
        F('competency', 'Competency Status', 'select', True, COMPETENCY),
        F('refresher_due', 'Refresher Due', 'date'),
        F('evidence_ref', 'Evidence Ref'),
        F('remarks', 'Remarks', 'textarea'),
    ],
    cols=['date', 'employee_id', 'employee_name', 'topic', 'competency', 'refresher_due'])

REGISTERS['ptw'] = dict(
    title='Permit to Work & LOTO', bn='কাজের অনুমতি', emp=False,
    fields=[
        F('permit_no', 'Permit No', required=True, maxlen=30),
        F('date', 'Date', 'date', True),
        F('department', 'Department', 'select', True, 'departments'),
        F('task_location', 'Task / Location', required=True),
        F('permit_type', 'Permit Type', 'select', True, PERMIT_TYPES),
        F('hazard', 'Hazard / Risk', 'textarea'),
        F('isolation_points', 'Isolation Points', 'textarea'),
        F('loto_by', 'LOTO Applied By'),
        F('gas_test', 'Gas Test / Other Test'),
        F('ppe_controls', 'PPE / Controls', 'textarea'),
        F('issuer', 'Issuer'),
        F('receiver', 'Receiver'),
        F('start_time', 'Start Time', 'time'),
        F('end_time', 'End Time', 'time'),
        F('closed_by', 'Closed By'),
        F('status', 'Status', 'select', True, PERMIT_STATUS),
        F('remarks', 'Remarks', 'textarea'),
    ],
    cols=['permit_no', 'date', 'department', 'task_location', 'permit_type', 'status'])

REGISTERS['audit'] = dict(
    title='Monthly Compliance Audit', bn='মাসিক অডিট', emp=False,
    fields=[
        F('audit_id', 'Audit Check Point', 'select', True, AUDIT_OPTIONS),
        F('audit_date', 'Audit Date', 'date', True),
        F('status', 'Status', 'select', True, AUDIT_STATUS),
        F('evidence', 'Evidence / Record', 'textarea'),
        F('finding', 'Finding / Risk', 'textarea'),
        F('corrective', 'Corrective Action', 'textarea'),
        F('responsible', 'Responsible'),
        F('due_date', 'Due Date', 'date'),
        F('closure_date', 'Closure Date', 'date'),
        F('verified_by', 'Verified By'),
    ],
    cols=['audit_id', 'audit_date', 'status', 'responsible', 'due_date', 'verified_by'])

# Registers HR can open from the "New form" menu (employee add/edit are separate)
SUBMITTABLE = list(REGISTERS.keys())

COMPUTED = {
    'employee_name': 'Name', 'department': 'Department', 'days': 'Days',
    'net_hours': 'Net Hours', 'late_mins': 'Late (mins)', 'ot_hours': 'OT Hours',
    'ot_rate': 'OT Rate (BDT/hr)', 'ot_pay': 'OT Pay (BDT)', 'gross': 'Gross',
    'net_pay': 'Net Pay', 'net_settlement': 'Net Settlement (BDT)',
}
KIND_LABEL = {
    'add_employee': 'Add Employee', 'edit_employee': 'Edit Employee',
}
for _k, _r in REGISTERS.items():
    KIND_LABEL[_k] = _r['title']


# ------------------------------------------------------------------ helpers
def prepare(fields, depts, employees=None):
    """Return copies of fields with `choices` resolved for select/employee types."""
    out = []
    for f in fields:
        g = dict(f)
        if f['type'] == 'select':
            opts = depts if f['options'] == 'departments' else f['options']
            g['choices'] = [(o, o) if isinstance(o, str) else tuple(o) for o in opts]
        elif f['type'] == 'employee':
            g['choices'] = [
                (e['employee_id'], '%s - %s (%s)' % (e['employee_id'], e['full_name'],
                                                     e['department'] or ''))
                for e in (employees or [])]
        out.append(g)
    return out


def _fmt_num(x):
    if x == int(x):
        return int(x)
    return round(x, 2)


def validate(fields, form, emp_map=None):
    """Validate submitted values. Returns (clean, errors). Never trusts the browser."""
    clean, errors = {}, {}
    emp_map = emp_map or {}
    for f in fields:
        n, t = f['name'], f['type']
        if f.get('readonly'):
            continue
        raw = (form.get(n) or '').strip()
        if CTRL.search(raw):
            errors[n] = 'Contains invalid characters'
            continue
        if not raw:
            clean[n] = ''
            if f['required']:
                errors[n] = 'This field is required'
            continue
        limit = 2000 if t == 'textarea' else f['maxlen']
        if len(raw) > limit:
            errors[n] = 'Too long (maximum %d characters)' % limit
            continue
        if f.get('pattern') and not re.match(f['pattern'], raw):
            errors[n] = f.get('pattern_msg') or 'Invalid format'
            continue
        if t in ('text', 'textarea'):
            clean[n] = raw
        elif t == 'tel':
            if TEL_RE.match(raw):
                clean[n] = raw
            else:
                errors[n] = 'Enter a valid phone number'
        elif t == 'date':
            try:
                d = datetime.strptime(raw, '%Y-%m-%d').date()
                if not 1900 <= d.year <= 2100:
                    raise ValueError
                clean[n] = d.isoformat()
            except ValueError:
                errors[n] = 'Enter a valid date (YYYY-MM-DD)'
        elif t == 'time':
            if TIME_RE.match(raw):
                clean[n] = raw
            else:
                errors[n] = 'Enter a valid time (HH:MM)'
        elif t in ('number', 'int'):
            try:
                x = float(raw)
                if not math.isfinite(x) or abs(x) > 1e9:
                    raise ValueError
                if x < 0 and not f['allow_neg']:
                    errors[n] = 'Must not be negative'
                    continue
                if t == 'int':
                    if x != int(x) or not 1990 <= x <= 2100:
                        raise ValueError
                    clean[n] = int(x)
                else:
                    clean[n] = _fmt_num(round(x, 2))
            except ValueError:
                errors[n] = 'Enter a valid number'
        elif t == 'select':
            if raw in dict(f['choices']):
                clean[n] = raw
            else:
                errors[n] = 'Choose a value from the list'
        elif t == 'employee':
            emp = emp_map.get(raw)
            if emp is None or raw not in dict(f['choices']):
                errors[n] = 'Choose an employee from the list'
            else:
                clean[n] = raw
                clean['employee_name'] = emp['full_name']
                clean['department'] = emp['department'] or ''
    return clean, errors


def _num(d, k):
    v = d.get(k)
    return float(v) if v not in (None, '') else 0.0


def _mins(t):
    h, m = t.split(':')
    return int(h) * 60 + int(m)


def _c_none(d):
    return {}, {}


def _c_leave(d):
    der, err = {}, {}
    if d.get('from_date') and d.get('to_date'):
        f = date.fromisoformat(d['from_date'])
        t = date.fromisoformat(d['to_date'])
        days = (t - f).days + 1
        if days < 1:
            err['to_date'] = 'To Date cannot be before From Date'
        elif days > 366:
            err['to_date'] = 'Leave period is too long'
        else:
            der['days'] = days
    return der, err


def _c_attendance(d):
    der, err = {}, {}
    if d.get('actual_in') and d.get('actual_out'):
        mins = (_mins(d['actual_out']) - _mins(d['actual_in'])) % 1440
        net = mins / 60.0 - _num(d, 'break_hrs')
        if net < 0:
            err['break_hrs'] = 'Break is longer than the time worked'
        else:
            der['net_hours'] = round(net, 2)
    if d.get('roster_start') and d.get('actual_in'):
        diff = _mins(d['actual_in']) - _mins(d['roster_start'])
        if diff < -720:
            diff += 1440
        elif diff > 720:
            diff -= 1440
        der['late_mins'] = max(0, diff)
    return der, err


def _c_ot(d):
    der, err = {}, {}
    hrs = ((_mins(d['ot_end']) - _mins(d['ot_start'])) % 1440) / 60.0 - _num(d, 'break_hrs')
    if hrs <= 0:
        err['ot_end'] = 'OT hours must be greater than zero'
        return der, err
    der['ot_hours'] = round(hrs, 2)
    base, div = _num(d, 'ot_wage_base'), _num(d, 'divisor')
    if base and div:
        rate = base / div * 2          # same formula as the workbook: base / divisor x 2
        der['ot_rate'] = round(rate, 2)
        der['ot_pay'] = round(hrs * rate, 2)
    return der, err


def _c_payroll(d):
    gross = sum(_num(d, k) for k in ('basic', 'house_rent', 'medical', 'other_allowance'))
    net = (gross + _num(d, 'ot_pay') + _num(d, 'other_earnings')
           - _num(d, 'absence_deduction') - _num(d, 'other_deduction'))
    err = {}
    if net < 0:
        err['other_deduction'] = 'Deductions exceed earnings'
    return {'gross': round(gross, 2), 'net_pay': round(net, 2)}, err


def _c_sep(d):
    plus = sum(_num(d, k) for k in ('notice_pay', 'wages_due', 'ot_due', 'leave_encashment',
                                    'compensation', 'gratuity', 'pf_benefit', 'other_dues'))
    net = plus - _num(d, 'deductions')
    return {'net_settlement': round(net, 2)}, {}


COMPUTE = {'leave': _c_leave, 'attendance': _c_attendance, 'ot': _c_ot,
           'payroll': _c_payroll, 'separation': _c_sep}


def compute(kind, clean):
    return COMPUTE.get(kind, _c_none)(clean)


def fields_for(kind):
    if kind in ('add_employee', 'edit_employee'):
        return EMPLOYEE_FIELDS
    return REGISTERS[kind]['fields']


def label_for(kind, key):
    for f in fields_for(kind):
        if f['name'] == key:
            return f['label']
    return COMPUTED.get(key, key.replace('_', ' ').title())


def req_title(kind, d):
    who = '%s - %s' % (d.get('employee_id', ''), d.get('employee_name', ''))
    if kind in ('add_employee', 'edit_employee'):
        return '%s: %s - %s' % (KIND_LABEL[kind], d.get('employee_id', ''), d.get('full_name', ''))
    if kind == 'leave':
        return 'Leave: %s, %s to %s (%s day%s)' % (
            who, d['from_date'], d['to_date'], d['days'], '' if d['days'] == 1 else 's')
    if kind == 'separation':
        return 'Terminate: %s (%s)' % (who, d.get('exit_route', ''))
    if REGISTERS[kind]['emp']:
        return '%s: %s' % (REGISTERS[kind]['title'], who)
    ref = d.get('incident_id') or d.get('permit_no') or d.get('audit_id') or ''
    return '%s: %s' % (REGISTERS[kind]['title'], ref)


def describe(kind, data):
    """Ordered (label, value) pairs for showing a payload to the approver."""
    rows, seen = [], set()
    for key in ('employee_name', 'department'):
        if key in data and kind not in ('add_employee', 'edit_employee') \
                and REGISTERS[kind]['emp']:
            rows.append((COMPUTED[key], data[key]))
            seen.add(key)
    for f in fields_for(kind):
        v = data.get(f['name'])
        if v not in (None, '') and f['name'] not in seen:
            rows.append((f['label'], v))
            seen.add(f['name'])
    for key in COMPUTED:
        if key in data and key not in seen:
            rows.append((COMPUTED[key], data[key]))
    return rows
