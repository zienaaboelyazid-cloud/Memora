"""
Diagnostic script - run this directly to see EXACTLY what's stored in
MySQL right now, without any of the try/except swallowing that
ai/assistant.py normally does. Helps answer "why doesn't the AI know
about this member/schedule?" by showing the raw data and any real
connection errors.

Usage:
    python db_check.py                  -> shows everything for patient_id 1
    python db_check.py 3                -> shows everything for patient_id 3
"""

import sys

from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_DATABASE
from database.db_connection import get_connection


def main():
    patient_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    print("=" * 60)
    print(f"Connecting to: host={MYSQL_HOST} port={MYSQL_PORT} user={MYSQL_USER} database={MYSQL_DATABASE}")
    print("=" * 60)

    try:
        conn = get_connection()
        print("✅ Connected to MySQL successfully.\n")
    except Exception as e:
        print("❌ COULD NOT CONNECT TO MYSQL. This is the real error:")
        print(f"   {type(e).__name__}: {e}")
        print("\nFix this first - nothing else below will work until the connection succeeds.")
        return

    cur = conn.cursor()

    # ---- every patient account that exists ----
    print("---- patients table (every account on this device) ----")
    cur.execute("SELECT id, first_name, last_name, national_id FROM patients ORDER BY id")
    rows = cur.fetchall()
    if not rows:
        print("  (EMPTY - no patient accounts exist yet in this MySQL database)")
    for r in rows:
        marker = "  <-- you're checking this one" if r[0] == patient_id else ""
        print(f"  id={r[0]}  name={r[1]} {r[2]}  national_id={r[3]}{marker}")

    # ---- family members for the requested patient_id ----
    print(f"\n---- people table WHERE patient_id = {patient_id} ----")
    cur.execute(
        "SELECT id, name, relationship, age, notes FROM people WHERE patient_id = %s",
        (patient_id,)
    )
    rows = cur.fetchall()
    if not rows:
        print(f"  (EMPTY - no family members saved under patient_id={patient_id})")
    for r in rows:
        print(f"  id={r[0]}  name={r[1]}  relationship={r[2]}  age={r[3]}  notes={r[4]}")

    # also show ALL people regardless of patient_id, to catch mismatches
    cur.execute("SELECT id, patient_id, name FROM people ORDER BY patient_id, id")
    all_rows = cur.fetchall()
    other_patient_ids = sorted({r[1] for r in all_rows if r[1] != patient_id})
    if other_patient_ids:
        print(f"\n  ⚠️  NOTE: there ARE people saved, but under different patient_id(s): {other_patient_ids}")
        print("      If that's where your member actually is, that's the bug - the app is")
        print("      adding/asking under two different patient_id values.")
        for r in all_rows:
            if r[1] != patient_id:
                print(f"      id={r[0]}  patient_id={r[1]}  name={r[2]}")

    # ---- schedule / memory facts for the requested patient_id ----
    print(f"\n---- patient_memory table WHERE patient_id = {patient_id} ----")
    cur.execute(
        "SELECT `key`, value, updated_at FROM patient_memory WHERE patient_id = %s",
        (patient_id,)
    )
    rows = cur.fetchall()
    if not rows:
        print(f"  (EMPTY - no facts/schedule saved under patient_id={patient_id})")
    for r in rows:
        print(f"  key={r[0]}  value={r[1]!r}  updated_at={r[2]}")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
