import hashlib
import secrets

from database.db_connection import get_connection


class CaregiverAuth:
    """
    One caregiver/admin PIN for this whole device (completely separate
    from any patient's national ID). Whoever knows it can open the
    Caregiver / Admin panel and see every patient registered on this
    device - so it's stored salted + hashed (SHA-256), never in plain
    text, exactly like a login password would be.
    """

    def __init__(self):
        self._init_table()

    def _connect(self):
        return get_connection()

    def _init_table(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS caregiver_auth (
                id INT PRIMARY KEY,
                salt VARCHAR(64) NOT NULL,
                pin_hash VARCHAR(64) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cur.close()
        conn.close()

    @staticmethod
    def _hash(pin, salt):
        return hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()

    def is_set_up(self):
        """True once a caregiver PIN has been created on this device."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM caregiver_auth WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row is not None

    def set_pin(self, pin):
        salt = secrets.token_hex(16)
        pin_hash = self._hash(pin, salt)

        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO caregiver_auth (id, salt, pin_hash) VALUES (1, %s, %s)
            ON DUPLICATE KEY UPDATE
                salt = VALUES(salt),
                pin_hash = VALUES(pin_hash)
        """, (salt, pin_hash))
        conn.commit()
        cur.close()
        conn.close()

    def verify(self, pin):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT salt, pin_hash FROM caregiver_auth WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row is None:
            return False

        salt, stored_hash = row
        return self._hash(pin, salt) == stored_hash
