from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from app.vision.settings import FaceSettings, get_face_settings


class FaceProcessingError(Exception):
    """Erreur contrôlée pendant le traitement d'une image faciale."""


@dataclass(frozen=True, slots=True)
class ExtractedFace:
    embedding: list[float]
    detection_score: float
    sharpness_score: float
    face_width: int
    face_height: int
    quality_score: float


class FaceEngine:
    """Détection YuNet, alignement et extraction SFace."""

    def __init__(self, settings: FaceSettings) -> None:
        self.settings = settings
        self._check_model_file(settings.yunet_path, "YuNet")
        self._check_model_file(settings.sface_path, "SFace")
        self.detector = self._create_detector(settings.yunet_path)
        self.recognizer = self._create_recognizer(settings.sface_path)

    @staticmethod
    def _check_model_file(path: Path, label: str) -> None:
        if not path.is_file():
            raise RuntimeError(
                f"Modèle {label} introuvable : {path}. "
                "Exécutez d'abord : python download_face_models.py"
            )

        if path.stat().st_size < 100_000:
            raise RuntimeError(
                f"Le fichier du modèle {label} semble incomplet : {path}. "
                "Relancez : python download_face_models.py --force"
            )

    def _create_detector(self, model_path: Path):
        args = (
            str(model_path),
            "",
            (320, 320),
            self.settings.detection_threshold,
            self.settings.nms_threshold,
            self.settings.top_k,
        )

        factory = getattr(cv2, "FaceDetectorYN_create", None)
        if factory is not None:
            return factory(*args)

        detector_class = getattr(cv2, "FaceDetectorYN", None)
        if detector_class is None or not hasattr(detector_class, "create"):
            raise RuntimeError(
                "Cette installation OpenCV ne contient pas FaceDetectorYN. "
                "Installez opencv-contrib-python puis redémarrez le terminal."
            )
        return detector_class.create(*args)

    @staticmethod
    def _create_recognizer(model_path: Path):
        factory = getattr(cv2, "FaceRecognizerSF_create", None)
        if factory is not None:
            return factory(str(model_path), "")

        recognizer_class = getattr(cv2, "FaceRecognizerSF", None)
        if recognizer_class is None or not hasattr(recognizer_class, "create"):
            raise RuntimeError(
                "Cette installation OpenCV ne contient pas FaceRecognizerSF. "
                "Installez opencv-contrib-python puis redémarrez le terminal."
            )
        return recognizer_class.create(str(model_path), "")

    @staticmethod
    def decode_image(image_bytes: bytes) -> np.ndarray:
        if not image_bytes:
            raise FaceProcessingError("Le fichier image est vide.")

        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise FaceProcessingError(
                "Le fichier ne peut pas être décodé comme une image JPEG, PNG ou WebP."
            )

        if image.ndim != 3 or image.shape[2] != 3:
            raise FaceProcessingError("L'image doit contenir trois canaux de couleur.")

        return image

    def extract(self, image_bytes: bytes) -> ExtractedFace:
        image = self.decode_image(image_bytes)
        height, width = image.shape[:2]
        # Réduire les très grandes images pour améliorer la détection YuNet.
        max_dimension = 1280

        if max(height, width) > max_dimension:
            scale = max_dimension / max(height, width)

            new_width = max(1, int(round(width * scale)))
            new_height = max(1, int(round(height * scale)))

            image = cv2.resize(
                image,
                (new_width, new_height),
                interpolation=cv2.INTER_AREA,
    )

        height, width = image.shape[:2]
        if width < self.settings.min_face_size or height < self.settings.min_face_size:
            raise FaceProcessingError("L'image est trop petite pour l'enrôlement facial.")

        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(image)

        face_count = 0 if faces is None else len(faces)
        if face_count == 0:
            raise FaceProcessingError(
                "Aucun visage n'a été détecté. Placez le visage face à la caméra."
            )
        if face_count > 1:
            raise FaceProcessingError(
                "Plusieurs visages ont été détectés. Une image doit contenir une seule personne."
            )

        face = faces[0]
        face_width = max(0, int(round(float(face[2]))))
        face_height = max(0, int(round(float(face[3]))))
        detection_score = float(face[14])

        if min(face_width, face_height) < self.settings.min_face_size:
            raise FaceProcessingError(
                "Le visage est trop éloigné. Approchez-vous de la caméra."
            )

        aligned_face = self.recognizer.alignCrop(image, face)
        if aligned_face is None or aligned_face.size == 0:
            raise FaceProcessingError("L'alignement du visage a échoué.")

        gray = cv2.cvtColor(aligned_face, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if sharpness < self.settings.min_sharpness:
            raise FaceProcessingError(
                "L'image du visage est trop floue. Stabilisez la caméra et recommencez."
            )

        feature = self.recognizer.feature(aligned_face)
        if feature is None:
            raise FaceProcessingError("L'extraction des caractéristiques faciales a échoué.")

        vector = np.asarray(feature, dtype=np.float32).reshape(-1)
        if vector.size != 128:
            raise FaceProcessingError(
                f"Le modèle a produit {vector.size} valeurs au lieu de 128."
            )
        if not np.all(np.isfinite(vector)):
            raise FaceProcessingError("L'embedding contient une valeur non valide.")

        norm = float(np.linalg.norm(vector))
        if norm <= 1e-12:
            raise FaceProcessingError("L'embedding facial produit est nul.")

        vector = vector / norm

        sharpness_component = min(sharpness / 300.0, 1.0)
        size_component = min(min(face_width, face_height) / 180.0, 1.0)
        quality = (
            0.50 * max(0.0, min(detection_score, 1.0))
            + 0.25 * sharpness_component
            + 0.25 * size_component
        )

        return ExtractedFace(
            embedding=[float(value) for value in vector],
            detection_score=round(detection_score, 6),
            sharpness_score=round(sharpness, 2),
            face_width=face_width,
            face_height=face_height,
            quality_score=round(max(0.0, min(quality, 1.0)), 4),
        )

    @staticmethod
    def cosine_similarity(first: list[float], second: list[float]) -> float:
        first_vector = np.asarray(first, dtype=np.float32)
        second_vector = np.asarray(second, dtype=np.float32)
        denominator = float(
            np.linalg.norm(first_vector) * np.linalg.norm(second_vector)
        )
        if denominator <= 1e-12:
            raise FaceProcessingError("Impossible de comparer deux embeddings nuls.")
        return float(np.dot(first_vector, second_vector) / denominator)


@lru_cache
def get_face_engine() -> FaceEngine:
    return FaceEngine(get_face_settings())
