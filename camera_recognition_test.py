from __future__ import annotations

import argparse
import sys

import cv2
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture une image avec la webcam et l'envoie à l'API ONEE Face ID."
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/recognitions",
        help="URL de la route de reconnaissance.",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Numéro de la caméra OpenCV.",
    )
    parser.add_argument(
        "--device-code",
        default="RECEPTION-01",
        help="Code enregistré dans recognition_event.device_code.",
    )
    parser.add_argument(
        "--refresh-index",
        action="store_true",
        help="Force le rechargement des embeddings avant la comparaison.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        print("Impossible d'ouvrir la caméra.", file=sys.stderr)
        return 1

    print("ESPACE : reconnaître le visage | Q : quitter")

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Impossible de lire une image de la caméra.", file=sys.stderr)
                return 1

            cv2.putText(
                frame,
                "ESPACE: reconnaitre | Q: quitter",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow("ONEE Face ID - Phase 6", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
            if key != 32:
                continue

            encoded_ok, encoded = cv2.imencode(".jpg", frame)
            if not encoded_ok:
                print("Encodage JPEG impossible.")
                continue

            try:
                response = requests.post(
                    args.url,
                    files={
                        "image": (
                            "camera.jpg",
                            encoded.tobytes(),
                            "image/jpeg",
                        )
                    },
                    data={
                        "device_code": args.device_code,
                        "refresh_index": str(args.refresh_index).lower(),
                    },
                    timeout=30,
                )
                payload = response.json()
            except requests.RequestException as exc:
                print(f"Erreur de communication avec l'API : {exc}")
                continue
            except ValueError:
                print(f"Réponse non JSON : {response.text}")
                continue

            if response.status_code >= 400:
                print(f"Erreur HTTP {response.status_code} : {payload}")
                continue

            event = payload.get("event", {})
            person = event.get("matched_person")
            print("\nDécision :", event.get("decision"))
            print("Similarité :", event.get("similarity_score"))
            print("Seuil :", event.get("threshold_used"))
            if person:
                print(
                    "Personne :",
                    person.get("first_name"),
                    person.get("last_name"),
                )
            else:
                print("Personne : inconnue")

    finally:
        camera.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
