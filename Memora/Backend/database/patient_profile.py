import mysql.connector

from database.db_connection import get_connection


class PatientProfile:
    """
    Stores every patient/account registered on this device.

    MEMORA is now multi-user: each family member who has their own
    MEMORA account (their own national ID, their own recognized faces,
    their own schedule/facts, their own safe zone) gets their own row
    here. Everywhere else in the app, data is scoped by patient_id so
    logging in as a different account shows completely different data.
    """

    def __init__(self):
        self._init_table()

    def _connect(self):
        return get_connection()

    def _init_table(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INT AUTO_INCREMENT PRIMARY KEY,
                first_name VARCHAR(255) NOT NULL,
                last_name VARCHAR(255) NOT NULL,
                date_of_birth VARCHAR(50),
                age INT,
                national_id VARCHAR(50) UNIQUE NOT NULL,
                photo_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cur.close()
        conn.close()

    def create(self, first_name, last_name, date_of_birth, age, national_id, photo_path=""):
        """
        Registers a brand new account. Raises ValueError if that
        national ID is already registered on this device.
        Returns the new patient_id.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO patients (first_name, last_name, date_of_birth, age, national_id, photo_path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (first_name, last_name, date_of_birth, age, national_id, photo_path))
            conn.commit()
            new_id = cur.lastrowid
            cur.close()
            return new_id
        except mysql.connector.errors.IntegrityError:
            raise ValueError("That national ID is already registered on this device.")
        finally:
            conn.close()

    def find_by_national_id(self, national_id):
        """Used at Login. Returns the matching patient's dict, or None."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, first_name, last_name, date_of_birth, age, national_id, photo_path
            FROM patients WHERE national_id = %s
        """, (national_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return self._row_to_dict(row)

    def get(self, patient_id):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, first_name, last_name, date_of_birth, age, national_id, photo_path
            FROM patients WHERE id = %s
        """, (patient_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return self._row_to_dict(row)

    def update_photo(self, patient_id, photo_path):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("UPDATE patients SET photo_path = %s WHERE id = %s", (photo_path, patient_id))
        conn.commit()
        cur.close()
        conn.close()

    def delete(self, patient_id):
        """Permanently removes this patient's account row. Callers are
        responsible for also clearing their face/memory/safe-zone data
        (see FaceDatabase.delete_all_for_patient, etc.) - used by the
        Caregiver/Admin panel's 'Remove a patient account'."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM patients WHERE id = %s", (patient_id,))
        conn.commit()
        cur.close()
        conn.close()

    def list_all(self):
        """
        Every account registered on this device (id, name, national_id
        only) - used by the 'My data' debug screen so the family can
        see for themselves that accounts really are separate.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, first_name, last_name, national_id FROM patients ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {"id": r[0], "first_name": r[1], "last_name": r[2], "national_id": r[3]}
            for r in rows
        ]

    @staticmethod
    def _row_to_dict(row):
        if row is None:
            return None

        patient_id, first_name, last_name, dob, age, national_id, photo_path = row

        return {
            "id": patient_id,
            "first_name": first_name or "",
            "last_name": last_name or "",
            "name": f"{first_name or ''} {last_name or ''}".strip(),
            "date_of_birth": dob or "",
            "age": age,
            "national_id": national_id or "",
            "photo_path": photo_path or "",
        }
