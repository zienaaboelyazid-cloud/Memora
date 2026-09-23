import cv2
import numpy as np
import insightface


class FaceRecognizer:

    def __init__(self):

        self.app = insightface.app.FaceAnalysis(
            providers=["CPUExecutionProvider"]
        )

        self.app.prepare(
            ctx_id=0,
            det_size=(640, 640)
        )

    def get_all_faces(self, image):
        """
        Detects ALL faces in the image directly using insightface's own
        detector, and returns a list of (bbox, embedding) for each one.
        bbox is (x1, y1, x2, y2).
        """

        if image is None:
            raise ValueError("Image is empty")

        faces = self.app.get(image)

        results = []

        for face in faces:
            bbox = face.bbox.astype(int)
            results.append((bbox, face.embedding))

        return results

    def get_embedding_from_image(self, image):
        """
        Convenience method for a SINGLE face - returns the embedding
        of the first face found, or None if there isn't one.
        """

        faces = self.get_all_faces(image)

        if len(faces) == 0:
            return None

        return faces[0][1]  # embedding of the first face

    def get_embedding(self, image_path):
        """
        Same idea, but takes a file path to an image instead of an image object.
        """

        image = cv2.imread(image_path)

        if image is None:
            raise ValueError("Could not read image")

        return self.get_embedding_from_image(image)

    def recognize(self, embedding, known_faces, threshold=0.5):
        """
        Compares a single face embedding against everyone already registered
        (known_faces, as loaded from FaceDatabase).
        Returns (name, similarity_score), or ("Unknown", best_score) if no
        good match is found.
        """

        best_name = "Unknown"
        best_score = -1.0

        for name, person_data in known_faces.items():
            saved_embeddings = person_data["embeddings"]
            for saved_embedding in saved_embeddings:

                saved_embedding = np.array(saved_embedding)

                similarity = np.dot(embedding, saved_embedding) / (
                    np.linalg.norm(embedding) * np.linalg.norm(saved_embedding)
                )

                if similarity > best_score:
                    best_score = similarity
                    best_name = name

        if best_score >= threshold:
            return best_name, best_score

        return "Unknown", best_score