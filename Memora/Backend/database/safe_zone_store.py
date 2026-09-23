from database.db_connection import get_connection


class SafeZoneStore:
    """
    Stores each patient's home location / safe-zone radius in the SAME
    MySQL database as everything else, SCOPED PER PATIENT (patient_id) -
    previously this lived in one shared JSON file (data/safe_zone_config.json),
    which meant every account on the device shared the same safe zone. Now
    every MEMORA account has its own.
    """

    def __init__(self):
        self._init_table()

    def _connect(self):
        return get_connection()

    def _init_table(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS safe_zones (
                patient_id INT PRIMARY KEY,
                center_lat DOUBLE NOT NULL,
                center_lon DOUBLE NOT NULL,
                radius_meters DOUBLE NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cur.close()
        conn.close()

    def save(self, patient_id, center_lat, center_lon, radius_meters):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO safe_zones (patient_id, center_lat, center_lon, radius_meters)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                center_lat = VALUES(center_lat),
                center_lon = VALUES(center_lon),
                radius_meters = VALUES(radius_meters),
                updated_at = CURRENT_TIMESTAMP
        """, (patient_id, center_lat, center_lon, radius_meters))
        conn.commit()
        cur.close()
        conn.close()

    def get(self, patient_id):
        """Returns {"center_lat", "center_lon", "radius_meters"} or None."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT center_lat, center_lon, radius_meters FROM safe_zones WHERE patient_id = %s",
            (patient_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row is None:
            return None

        return {"center_lat": row[0], "center_lon": row[1], "radius_meters": row[2]}

    def delete(self, patient_id):
        """Used when a Caregiver deletes a patient account."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM safe_zones WHERE patient_id = %s", (patient_id,))
        conn.commit()
        cur.close()
        conn.close()
