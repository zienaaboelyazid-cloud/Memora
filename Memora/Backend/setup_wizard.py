import os

import cv2


def capture_photo(camera, window_title="MEMORA Setup"):
    """
    Shows a live camera preview. Press SPACE to capture the photo,
    or ESC to skip/cancel. Returns the captured frame, or None if skipped.
    """
    print("(Look at the camera - press SPACE to capture, ESC to skip)")

    while True:
        ret, frame = camera.read()
        if not ret:
            continue

        cv2.imshow(window_title, frame)
        key = cv2.waitKey(1) & 0xFF

        if key == 32:  # SPACE
            cv2.destroyWindow(window_title)
            return frame
        elif key == 27:  # ESC
            cv2.destroyWindow(window_title)
            return None


def get_face_photo(camera, recognizer, person_label="this person", max_attempts=3):
    """
    Lets the family either TAKE a live photo with the camera or UPLOAD an
    existing photo file, then runs real face detection on it (same
    detector used everywhere else in the app) instead of just saving
    whatever was captured.

    Retries up to `max_attempts` times if no face is found in the photo,
    or if the chosen file can't be read.

    Returns (frame, bbox, embedding) on success - bbox is (x1, y1, x2, y2)
    of the detected face - or (None, None, None) if skipped/given up.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"\nHow do you want to provide {person_label}'s photo? "
              f"(attempt {attempt}/{max_attempts})")
        print("1) Take a photo with the camera")
        print("2) Upload an existing photo file")
        print("3) Skip / cancel")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            frame = capture_photo(camera)
            if frame is None:
                print("No photo captured.")
                continue

        elif choice == "2":
            path = input("Enter the full path to the photo file: ").strip().strip('"')
            if not path or not os.path.exists(path):
                print("File not found, please check the path and try again.")
                continue
            frame = cv2.imread(path)
            if frame is None:
                print("Could not read that file as an image (unsupported format?).")
                continue

        elif choice == "3":
            return None, None, None

        else:
            print("Please choose 1, 2 or 3.")
            continue

        faces = recognizer.get_all_faces(frame)

        if len(faces) == 0:
            print("No face was detected in that photo. Let's try again.")
            continue

        bbox, embedding = faces[0]
        return frame, bbox, embedding

    print(f"Giving up after {max_attempts} attempts - "
          f"{person_label} won't be registered with a photo right now.")
    return None, None, None


def run_family_setup(camera, capture, recognizer, database, speaker, patient_id):
    """
    Runs right after Sign Up (patient account creation) completes.
    Lets the family add themselves one by one (name, relationship,
    photo) so they're recognized from day one, instead of waiting for
    the camera to bump into them by chance.

    Every added person is scoped to this patient_id's account - a
    different account will not see them.

    Every photo - camera or uploaded - goes through real face detection
    before it's accepted, exactly like patient sign-up.
    """

    print("\n=== Let's add the family members MEMORA should recognize. ===")
    speaker.speak("Now let's add the family members.")

    while True:
        add_more = input("\nAdd a family member now? (y/n): ").strip().lower()
        if add_more != "y":
            break

        name = input("Enter their name: ").strip()
        if not name:
            print("Name can't be empty, skipping.")
            continue

        relationship = input("Enter their relationship to the patient (e.g. daughter, son): ").strip()

        frame, bbox, embedding = get_face_photo(camera, recognizer, person_label=name)

        if embedding is None:
            print(f"'{name}' was not added (no valid photo).")
            continue

        database.save(patient_id, name, embedding, relationship)

        x1, y1, x2, y2 = bbox
        x, y, w, h = x1, y1, x2 - x1, y2 - y1
        capture.capture_face(frame, (x, y, w, h), name)

        print(f"'{name}' ({relationship}) added successfully.")

    print("\n=== Family setup complete! MEMORA is ready to use. ===")
    speaker.speak("Setup complete. Memora is ready.")
