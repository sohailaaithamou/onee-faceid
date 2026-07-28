from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FaceSettings(BaseSettings):
    """Configuration commune à l'enrôlement et à la reconnaissance faciale."""

    model_dir: Path = Path("models/face")
    yunet_model: str = "face_detection_yunet_2023mar.onnx"
    sface_model: str = "face_recognition_sface_2021dec.onnx"
    model_version: str = "sface_2021dec_yunet_2023mar"

    max_upload_bytes: int = Field(default=8 * 1024 * 1024, ge=100_000)
    detection_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    nms_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    top_k: int = Field(default=5000, ge=1)
    min_face_size: int = Field(default=80, ge=20)
    min_sharpness: float = Field(default=40.0, ge=0.0)

    enrollment_min_similarity: float = Field(
        default=0.363,
        ge=-1.0,
        le=1.0,
    )
    recognition_threshold: float = Field(
        default=0.363,
        ge=-1.0,
        le=1.0,
    )
    recognition_cache_seconds: int = Field(default=30, ge=1, le=3600)
    recognition_top_candidates: int = Field(default=3, ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FACE_",
        extra="ignore",
    )

    @property
    def yunet_path(self) -> Path:
        return self.model_dir / self.yunet_model

    @property
    def sface_path(self) -> Path:
        return self.model_dir / self.sface_model


@lru_cache
def get_face_settings() -> FaceSettings:
    return FaceSettings()


face_settings = get_face_settings()
