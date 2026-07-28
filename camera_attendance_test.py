from __future__ import annotations

import argparse
import sys

import cv2
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test webcam : reconnaissance puis pointage ENTRY/EXIT."
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
        help="Adresse de l'API FastAPI.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Index OpenCV de la caméra.",
    )
    parser.add_argument(
        "--device-code",
        default="RECEPTION-01",
        help="Code de la caméra ou du poste.",
    )
    parser.add_argument(
        "--visit-id",
        type=int,
        default=None,
        help="Identifiant de visite requis pour un visiteur.",
    )
    parser.add_argument(
        "--refresh-index",
        action="store_true",
        help="Recharge l'index facial à chaque capture.",
    )
    return parser.parse_args()


def print_api_error(response: requests.Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        print(f"Erreur HTTP {response.status_code}: {response.text}")
        return
    print(f"Erreur HTTP {response.status_code}: {payload}")


def main() -> int:
    args = parse_args()
    camera = cv2.VideoCapture(args.camera_index)

    if not camera.isOpened():
        print("Impossible d'ouvrir la caméra.")
        return 1

    window_name = "ONEE Face ID - Phase 7 Attendance"
    print("Cliquez dans la fenêtre caméra.")
    print("ESPACE ou ENTREE : reconnaître et pointer")
    print("Q ou ECHAP : quitter")

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Impossible de lire une image depuis la caméra.")
                return 1

            cv2.putText(
                frame,
                "ESPACE/ENTREE: pointer | Q: quitter",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(window_name, frame)

            key = cv2.waitKeyEx(20)
            if key in (ord("q"), ord("Q"), 27):
                break
            if key not in (32, 13):
                continue

            print("\nCapture détectée : reconnaissance en cours...")
            encoded_ok, encoded = cv2.imencode(".jpg", frame)
            if not encoded_ok:
                print("Encodage JPEG impossible.")
                continue

            try:
                recognition_response = requests.post(
                    f"{args.api_url.rstrip('/')}/recognitions",
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
            except requests.RequestException as exc:
                print(f"API inaccessible : {exc}")
                continue

            if recognition_response.status_code >= 400:
                print_api_error(recognition_response)
                continue

            recognition = recognition_response.json()
            event = recognition.get("event", {})
            print(
                "Reconnaissance :",
                event.get("decision"),
                "| score =",
                event.get("similarity_score"),
            )

            if event.get("decision") != "MATCHED":
                print("Aucun pointage créé : la personne n'est pas reconnue.")
                continue

            recognition_id = event.get("id")
            payload = {
                "visit_id": args.visit_id,
                "note": "Pointage depuis la webcam Phase 7",
            }

            try:
                presence_response = requests.post(
                    (
                        f"{args.api_url.rstrip('/')}/presence-events/"
                        f"from-recognition/{recognition_id}"
                    ),
                    json=payload,
                    timeout=15,
                )
            except requests.RequestException as exc:
                print(f"Erreur pendant le pointage : {exc}")
                continue

            if presence_response.status_code >= 400:
                print_api_error(presence_response)
                continue

            result = presence_response.json()
            presence = result["presence"]
            person = presence["person"]
            print(result["message"])
            print(
                f"Type : {presence['event_type']} | "
                f"Personne : {person['first_name']} {person['last_name']} | "
                f"Heure : {presence['event_time']}"
            )
    finally:
        camera.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
