"""
Run this ONCE to migrate your existing data:
    data/face_database.json    -> MySQL (people, embeddings)
    data/patient_memory.json   -> MySQL (patient_memory)

After this runs successfully, the two old .json files are no longer
needed (you can keep them as a backup).
"""

import json
import os

from database.facedatabase import FaceDatabase
from database.patient_memory import PatientMemory


def migrate_faces(old_json_path="data/face_database.json", patient_id=1):
    if not os.path.exists(old_json_path):
        print(f"Skipping: '{old_json_path}' not found.")
        return

    with open(old_json_path, "r") as f:
        old_data = json.load(f)

    db = FaceDatabase()

    count = 0
    for name, info in old_data.items():
        relationship = info.get("relationship", "")
        embeddings = info.get("embeddings", [])
        for embedding in embeddings:
            db.save(patient_id, name, embedding, relationship)
        count += 1

    print(f"Migrated {count} people from '{old_json_path}' into account #{patient_id}.")


def migrate_patient_memory(old_json_path="data/patient_memory.json", patient_id=1):
    if not os.path.exists(old_json_path):
        print(f"Skipping: '{old_json_path}' not found.")
        return

    with open(old_json_path, "r") as f:
        old_data = json.load(f)

    memory = PatientMemory()

    for key, value in old_data.items():
        memory.set(patient_id, key, value)

    print(f"Migrated {len(old_data)} memory entries from '{old_json_path}' into account #{patient_id}.")


if __name__ == "__main__":
    migrate_faces()
    migrate_patient_memory()
    print("Done. Your data now lives in the MySQL 'memora' database.")