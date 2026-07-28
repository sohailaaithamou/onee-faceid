from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.db.session import SessionLocal
from app.main import app
from app.services.system_service import get_system_readiness


REQUIRED_PATHS = {
    "/organizations",
    "/organizational-units",
    "/employees",
    "/visitors",
    "/visits",
    "/face-enrollments/{person_id}",
    "/recognitions",
    "/recognition-index/status",
    "/presence-events/from-recognition/{recognition_id}",
    "/presence/current",
    "/dashboard/overview",
    "/auth/login",
    "/auth/me",
    "/user-accounts",
    "/system/readiness",
}

REQUIRED_STATIC_FILES = {
    Path("app/static/dashboard/index.html"),
    Path("app/static/dashboard/login.html"),
    Path("app/static/dashboard/app.js"),
    Path("app/static/dashboard/login.js"),
    Path("app/static/dashboard/styles.css"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validation finale du prototype ONEE Face ID."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Afficher le rapport au format JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Retourner un code d'erreur même en présence d'un simple WARNING.",
    )
    return parser.parse_args()


def application_checks() -> list[dict[str, Any]]:
    paths = set(app.openapi().get("paths", {}).keys())
    missing_paths = sorted(REQUIRED_PATHS - paths)
    missing_static = sorted(
        str(path) for path in REQUIRED_STATIC_FILES if not path.is_file()
    )

    return [
        {
            "key": "api_routes",
            "label": "Routes API des dix phases",
            "state": "PASS" if not missing_paths else "FAIL",
            "detail": (
                "Toutes les routes principales sont exposées."
                if not missing_paths
                else f"Routes manquantes : {', '.join(missing_paths)}"
            ),
            "value": {
                "expected": len(REQUIRED_PATHS),
                "found": len(REQUIRED_PATHS & paths),
                "missing": missing_paths,
            },
        },
        {
            "key": "dashboard_static_files",
            "label": "Fichiers du dashboard",
            "state": "PASS" if not missing_static else "FAIL",
            "detail": (
                "Les fichiers HTML, CSS et JavaScript sont présents."
                if not missing_static
                else f"Fichiers manquants : {', '.join(missing_static)}"
            ),
            "value": {"missing": missing_static},
        },
    ]


def print_text(report: dict[str, Any]) -> None:
    print("=" * 72)
    print("VALIDATION FINALE — ONEE FACE ID")
    print("=" * 72)
    print(f"Statut global : {report['status']}")
    print(
        "Résumé : "
        f"{report['summary']['passed']} PASS | "
        f"{report['summary']['warnings']} WARNING | "
        f"{report['summary']['failed']} FAIL"
    )
    print()

    for item in report["checks"]:
        symbol = {
            "PASS": "[PASS]",
            "WARNING": "[WARN]",
            "FAIL": "[FAIL]",
        }[item["state"]]
        print(f"{symbol} {item['label']}")
        print(f"       {item['detail']}")

    print("=" * 72)


def main() -> None:
    args = parse_args()

    with SessionLocal() as db:
        readiness = get_system_readiness(db).model_dump(mode="json")

    checks = application_checks() + readiness["checks"]
    passed = sum(item["state"] == "PASS" for item in checks)
    warnings = sum(item["state"] == "WARNING" for item in checks)
    failed = sum(item["state"] == "FAIL" for item in checks)

    if failed:
        status = "NOT_READY"
    elif warnings:
        status = "WARNING"
    else:
        status = "READY"

    report = {
        **readiness,
        "status": status,
        "summary": {
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
        },
        "checks": checks,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)

    if failed or (args.strict and warnings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
