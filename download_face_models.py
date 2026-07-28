from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
        "models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}


def download(url: str, destination: Path, *, force: bool) -> None:
    if destination.exists() and not force and destination.stat().st_size >= 100_000:
        print(f"Déjà présent : {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")

    print(f"Téléchargement : {destination.name}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ONEE-FaceID-Prototype/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    if temporary.stat().st_size < 100_000:
        content = temporary.read_bytes()[:200]
        temporary.unlink(missing_ok=True)
        if b"git-lfs.github.com/spec" in content:
            raise RuntimeError(
                "Le serveur a retourné un pointeur Git LFS au lieu du modèle ONNX."
            )
        raise RuntimeError("Le fichier téléchargé est trop petit et semble incomplet.")

    temporary.replace(destination)
    print(f"OK : {destination} ({destination.stat().st_size / 1024 / 1024:.2f} Mo)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Télécharge les modèles officiels YuNet et SFace d'OpenCV Zoo."
    )
    parser.add_argument("--model-dir", default="models/face")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    try:
        for filename, url in MODELS.items():
            download(url, model_dir / filename, force=args.force)
    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    print("Les modèles faciaux sont prêts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
