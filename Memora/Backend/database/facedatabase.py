import os
import json

import mysql.connector

from database.db_connection import get_connection


class FaceDatabase:
    """
    Stores each registered person's name, relationship, and face embeddings
    in the shared MySQL database, SCOPED PER PATIENT (patient_id) so every
    MEMORA account only ever sees its own family members - logging in as a
    different account shows a different set of recognized faces.

    Tables:
        people     -> id, patient_id, name, relationship, age, notes, photo_path, created_at
        embeddings -> id, person_id (FK -> people.id), embedding (JSON text), created_at
    """

    def __init__(self):
        self._init_tables()

    def _connect(self):
        return get_connection()

    def _init_tables(self):
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id INT AUTO_INCREMENT PRIMARY KEY,
                patient_id INT NOT NULL DEFAULT 1,
                name VARCHAR(255) NOT NULL,
                relationship VARCHAR(255) DEFAULT '',
                age INT,
                notes VARCHAR(2000) DEFAULT '',
                photo_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                person_id INT NOT NULL,
                embedding LONGTEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES people (id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        conn.commit()

        # Upgrade an older install that's missing newer columns, instead of
        # breaking on it.
        cur.execute("""
            SELECT COLUMN_NAME FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = 'people'
        """)
        existing_columns = {row[0] for row in cur.fetchall()}
        if "patient_id" not in existing_columns:
            cur.execute("ALTER TABLE people ADD COLUMN patient_id INT NOT NULL DEFAULT 1")
            conn.commit()
        if "age" not in existing_columns:
            cur.execute("ALTER TABLE people ADD COLUMN age INT")
            conn.commit()
        if "notes" not in existing_columns:
            cur.execute("ALTER TABLE people ADD COLUMN notes VARCHAR(2000) DEFAULT ''")
            conn.commit()
        if "photo_path" not in existing_columns:
            cur.execute("ALTER TABLE people ADD COLUMN photo_path VARCHAR(500)")
            conn.commit()

        cur.close()
        conn.close()

    def save(self, patient_id, name, embedding, relationship="", age=None, photo_path=None, notes=None):
        """
        Saves a face embedding under a person's name, along with their
        relationship to the patient and (optionally) their age, a short
        free-text description/notes about them, and a path to their
        saved photo - scoped to this patient_id's account. If the
        person already exists under this account, the new embedding is
        added to their list, and the relationship/age/notes/photo are
        updated if new values are given.

        Returns the person's id (people.id) so callers can build a
        photo URL, link records, etc.
        """
        embedding_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        embedding_json = json.dumps(embedding_list)

        conn = self._connect()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM people WHERE patient_id = %s AND name = %s",
            (patient_id, name)
        )
        row = cur.fetchone()

        if row is None:
            cur.execute(
                "INSERT INTO people (patient_id, name, relationship, age, notes, photo_path) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (patient_id, name, relationship, age, notes or "", photo_path)
            )
            person_id = cur.lastrowid
        else:
            person_id = row[0]
            if relationship:
                cur.execute(
                    "UPDATE people SET relationship = %s WHERE id = %s",
                    (relationship, person_id)
                )
            if age is not None:
                cur.execute(
                    "UPDATE people SET age = %s WHERE id = %s",
                    (age, person_id)
                )
            if notes is not None:
                cur.execute(
                    "UPDATE people SET notes = %s WHERE id = %s",
                    (notes, person_id)
                )
            if photo_path:
                cur.execute(
                    "UPDATE people SET photo_path = %s WHERE id = %s",
                    (photo_path, person_id)
                )

        cur.execute(
            "INSERT INTO embeddings (person_id, embedding) VALUES (%s, %s)",
            (person_id, embedding_json)
        )

        conn.commit()
        cur.close()
        conn.close()
        return person_id

    def get_relationship(self, patient_id, name):
        """
        Returns the stored relationship for a person under this
        patient_id's account, or "" if unknown.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT relationship FROM people WHERE patient_id = %s AND name = %s",
            (patient_id, name)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else ""

    def load(self, patient_id):
        """
        Returns everyone registered under this patient_id's account:
        {
            "Sara": {"relationship": "daughter", "embeddings": [[...], [...]]},
            "Ahmed": {"relationship": "son", "embeddings": [[...]]}
        }
        """
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("SELECT id, name, relationship FROM people WHERE patient_id = %s", (patient_id,))
        people = cur.fetchall()

        data = {}
        for person_id, name, relationship in people:
            cur.execute(
                "SELECT embedding FROM embeddings WHERE person_id = %s",
                (person_id,)
            )
            embeddings = [json.loads(row[0]) for row in cur.fetchall()]
            data[name] = {"relationship": relationship, "embeddings": embeddings}

        cur.close()
        conn.close()
        return data

    def count_people(self, patient_id):
        """How many people are registered under this account - used by the 'My data' debug view."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM people WHERE patient_id = %s", (patient_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count

    def list_people(self, patient_id):
        """Lightweight list (no embeddings) - used by the family lists
        on the setup/dashboard/"my data" screens, the AI assistant's
        context, and the Caregiver/Admin panel's patient-details view."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, relationship, age, notes, photo_path FROM people WHERE patient_id = %s",
            (patient_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id": person_id,
                "name": name,
                "relationship": relationship,
                "age": age,
                "notes": notes or "",
                "hasPhoto": bool(photo_path) and os.path.exists(photo_path),
            }
            for person_id, name, relationship, age, notes, photo_path in rows
        ]

    def get_photo_path(self, patient_id, person_id):
        """Returns the saved photo path for this person, scoped to the
        patient's account, or "" if there isn't one - used to serve the
        family member's photo over the API."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT photo_path FROM people WHERE patient_id = %s AND id = %s",
            (patient_id, person_id)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return (row[0] if row else "") or ""

    def delete_all_for_patient(self, patient_id):
        """Removes every person (and their embeddings) registered under
        this account - used when a Caregiver deletes a patient account."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM people WHERE patient_id = %s", (patient_id,))
        person_ids = [row[0] for row in cur.fetchall()]
        for person_id in person_ids:
            cur.execute("DELETE FROM embeddings WHERE person_id = %s", (person_id,))
        cur.execute("DELETE FROM people WHERE patient_id = %s", (patient_id,))
        conn.commit()
        cur.close()
        conn.close()
