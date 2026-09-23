from datetime import datetime, timezone

from database.db_connection import get_connection


class PatientMemory:
    """
    Stores flexible key/value facts about the patient (today's schedule,
    home address, notes, etc.), SCOPED PER PATIENT (patient_id) so every
    MEMORA account keeps its own facts - the AI assistant only ever
    sees the facts that belong to whoever is currently logged in.
    """

    def __init__(self):
        self._init_table()

    def _connect(self):
        return get_connection()

    def _init_table(self):
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS patient_memory (
                patient_id INT NOT NULL,
                `key` VARCHAR(255) NOT NULL,
                value LONGTEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (patient_id, `key`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cur.close()
        conn.close()

    def set(self, patient_id, key, value):
        """
        Adds a new fact, or updates it if the key already exists, for
        this specific patient's account.
        e.g. memory.set(patient_id, "today_schedule", "9:00 - Doctor's appointment")
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO patient_memory (patient_id, `key`, value)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                value = VALUES(value),
                updated_at = CURRENT_TIMESTAMP
        """, (patient_id, key, value))
        conn.commit()
        cur.close()
        conn.close()

    def get(self, patient_id, key):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT value FROM patient_memory WHERE patient_id = %s AND `key` = %s",
            (patient_id, key)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None

    def get_age_hours(self, patient_id, key):
        """
        How many hours ago this fact was last saved, or None if the fact
        doesn't exist / has no usable timestamp. Used to tell when
        "today's schedule" has gone stale.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT updated_at FROM patient_memory WHERE patient_id = %s AND `key` = %s",
            (patient_id, key)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row or not row[0]:
            return None

        saved = row[0]
        if isinstance(saved, str):
            try:
                saved = datetime.strptime(saved, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

        saved = saved.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - saved).total_seconds() / 3600

    def get_all(self, patient_id):
        """
        Returns everything stored for this patient_id as a plain dict -
        used directly by ai/assistant.py to build the system prompt.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT `key`, value FROM patient_memory WHERE patient_id = %s", (patient_id,))
        data = dict(cur.fetchall())
        cur.close()
        conn.close()
        return data

    def delete_all_for_patient(self, patient_id):
        """Used when a Caregiver deletes a patient account."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM patient_memory WHERE patient_id = %s", (patient_id,))
        conn.commit()
        cur.close()
        conn.close()
