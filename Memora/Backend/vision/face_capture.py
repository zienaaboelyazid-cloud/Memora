import cv2
import os


class FaceCapture:

    def __init__(self, save_directory="data/people"):
        self.save_directory = save_directory

        if not os.path.exists(self.save_directory):
            os.makedirs(self.save_directory)

    def capture_face(self, frame, face, person_name):

        x, y, w, h = face

        face_image = frame[y:y + h, x:x + w]

        image_number = 1

        while True:

            file_name = f"{person_name}_{image_number}.jpg"

            file_path = os.path.join(
                self.save_directory,
                file_name
            )

            if not os.path.exists(file_path):
                break

            image_number += 1

        cv2.imwrite(file_path, face_image)

        return file_path