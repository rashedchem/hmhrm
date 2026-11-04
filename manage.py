"""Command-line admin tool.   python manage.py <command>

  init                    create the database and first accounts (done automatically)
  list-users              show all accounts
  reset-password USER     set a new temporary password (use if the Director is locked out)
  unlock USER             clear a lock after too many wrong passwords
  backup                  copy the database to data/backup/hr-YYYYMMDD-HHMMSS.db
"""
import os
import sqlite3
import sys
from datetime import datetime

from werkzeug.security import generate_password_hash

import hrdb


def main(argv):
    hrdb.init_db()
    cmd = argv[1] if len(argv) > 1 else ''
    if cmd == 'init':
        boot = hrdb.bootstrap_users()
        if boot:
            creds, path = boot
            print('Accounts created. Temporary passwords are saved in:\n  ' + path)
            for u, p in creds.items():
                print('  username: %-10s password: %s' % (u, p))
        else:
            print('Database ready. Accounts already exist.')
    elif cmd == 'list-users':
        c = hrdb.connect()
        for r in c.execute('SELECT username, role, active, last_login FROM users ORDER BY role, username'):
            print('%-15s %-12s %-8s %s' % (r['username'], r['role'], 'active' if r['active'] else 'DISABLED',
                                          r['last_login'] or '-'))
    elif cmd in ('reset-password', 'unlock') and len(argv) > 2:
        c = hrdb.connect()
        u = c.execute('SELECT id FROM users WHERE username=?', (argv[2],)).fetchone()
        if not u:
            print('No such user.')
            return 1
        if cmd == 'unlock':
            c.execute('UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=?', (u['id'],))
            print('Unlocked.')
        else:
            pw = hrdb.new_password()
            c.execute('UPDATE users SET password_hash=?, must_change=1, session_ver=session_ver+1, '
                      'failed_attempts=0, locked_until=NULL, active=1 WHERE id=?',
                      (generate_password_hash(pw, method=hrdb.HASH_METHOD), u['id']))
            print('New temporary password for %s: %s  (must be changed at next login)' % (argv[2], pw))
        c.commit()
    elif cmd == 'backup':
        folder = os.path.join(hrdb.DATA_DIR, 'backup')
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, 'hr-%s.db' % datetime.now().strftime('%Y%m%d-%H%M%S'))
        src = hrdb.connect()
        dst = sqlite3.connect(dest)
        src.backup(dst)
        dst.close()
        src.close()
        print('Backup written to ' + dest)
    else:
        print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
