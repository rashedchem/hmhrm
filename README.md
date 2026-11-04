# Steel Plant HR Management System

Web-based HR system built on your *Steel_Plant_HR_Compliance_Registers.xlsx* (Python + HTML + CSS only,
one small dependency: Flask). Runs on **Windows 7 or newer**; used from **Chrome or Firefox**.

## Install (once)
1. Install **Python 3.8.10** from python.org (the last version that supports Windows 7;
   on Windows 8/10/11 any Python 3.8+ is fine). Tick **"Add Python to PATH"**.
2. Double-click **setup.bat** (needs internet once, to download Flask and Waitress).
   It prints the first passwords and saves them in `data\FIRST_RUN_PASSWORDS.txt`.
3. Double-click **run.bat**. Open **http://localhost:8000** in Chrome or Firefox.
   Other PCs on the office network use `http://<server-PC-IP>:8000`
   (allow Python through Windows Firewall when asked).

Windows 7 browsers: last versions are Chrome 109 and Firefox ESR 115 - both work; no CDN or internet is needed after setup.

## Roles
| Role | What they can do |
|---|---|
| **Higher Management** (Director / Executive Director) | Approve or reject every submission; create users, reset passwords, disable accounts; view all registers; audit log |
| **HR Manager** | Submit every form: add employee, edit employee, **terminate** employee (final settlement), **leave for a worker**, leave ledger, attendance, OT, payroll, incident, PPE, training, PTW/LOTO, audit. Nothing takes effect until approved. Can withdraw own pending requests |
| **Management Employee** | See **own profile only** (read-only, no edit) and **apply for own leave**; sees status of own applications |

Approval flow: *Submit -> Pending -> Director approves (data is written) or rejects (reason required)*.
Records only enter the registers/employee master on approval. Edit requests show old vs. new values to the approver.

## Security built in
- Password hashing (PBKDF2-SHA256, 600k rounds), min. 10 chars + letters/digits, forced change at first login and after reset
- Account lock for 15 min after 5 wrong passwords; per-IP throttle; same error for unknown user / wrong password
- 30-minute idle session timeout; sessions end immediately when a user is disabled, reset or terminated
- CSRF token on every POST; HttpOnly + SameSite cookies; strict Content-Security-Policy, no external scripts/fonts
- Role checks on every page; employees are locked to their own record (server-side, form values are not trusted)
- All SQL parameterised; all input validated server-side; CSV exports protected against formula injection
- Audit log of logins, submissions, approvals, rejections, exports, user changes
- Random secret key and first passwords generated per installation

**Recommended:** keep the server on the internal network only; if you need HTTPS, put it behind IIS/nginx/Caddy
with a certificate and set `HR_HTTPS=1` in run.bat. Double-click **backup.bat** daily (copies to `data\backup`),
and copy the `data` folder to another disk. Delete `FIRST_RUN_PASSWORDS.txt` after first logins.
If the Director is locked out: `venv\Scripts\python manage.py reset-password director`.

## First use
1. Log in as **director** -> change password. Log in as **hrmanager** -> change password.
2. HR: **Employees -> Add employee** (tick "create login" for management employees) -> Director approves ->
   the temporary login is shown once to the Director.
3. HR: **Leave Ledger Entry** to record each employee's leave entitlement (approved by Director).
4. Director can add more HR/Director users in **Users**.

## Notes
- Departments, shifts, leave types, incident/permit/audit lists and the 22 audit check points come from your workbook.
- Like your workbook, **no legal rate is hard-coded** (OT divisor, leave entitlement, notice, gratuity are entered by HR).
  OT pay uses the workbook formula: wage base / divisor x 2 x OT hours. Confirm all rules with your legal advisor.
- Data is stored in `data\hr.db` (SQLite). Export any register to CSV (opens in Excel, Bangla text supported).
- Test suite: `venv\Scripts\python tests\test_flow.py`
