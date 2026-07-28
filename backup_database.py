from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from app.core.config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Créer une sauvegarde PostgreSQL du projet ONEE Face ID."
    )
    parser.add_argument(
        "--output-dir",
        default="backups",
        help="Dossier de destination. Valeur par défaut : backups",
    )
    parser.add_argument(
        "--pg-dump",
        default=None,
        help="Chemin explicite vers pg_dump.exe si nécessaire.",
    )
    return parser.parse_args()


def find_pg_dump(explicit_path: str | None) -> Path:
    candidates: list[Path] = []

    if explicit_path:
        candidates.append(Path(explicit_path))

    env_path = os.getenv("PG_DUMP_PATH")
    if env_path:
        candidates.append(Path(env_path))

    found = shutil.which("pg_dump")
    if found:
        candidates.append(Path(found))

    for version in (18, 17, 16, 15):
        candidates.append(
            Path(f"C:/Program Files/PostgreSQL/{version}/bin/pg_dump.exe")
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise SystemExit(
        "pg_dump est introuvable. Utilisez --pg-dump avec le chemin de pg_dump.exe."
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    pg_dump = find_pg_dump(args.pg_dump)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = output_dir / f"faceid_onee_{timestamp}.backup"

    command = [
        str(pg_dump),
        "--host",
        settings.db_host,
        "--port",
        str(settings.db_port),
        "--username",
        settings.db_user,
        "--format",
        "custom",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(backup_path),
        settings.db_name,
    ]

    environment = os.environ.copy()
    environment["PGPASSWORD"] = settings.db_password

    print(f"Sauvegarde de la base {settings.db_name}...")
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        if backup_path.exists():
            backup_path.unlink()
        detail = result.stderr.strip() or "Erreur pg_dump inconnue."
        raise SystemExit(f"Échec de la sauvegarde : {detail}")

    checksum = sha256_file(backup_path)
    checksum_path = backup_path.with_suffix(backup_path.suffix + ".sha256")
    checksum_path.write_text(
        f"{checksum}  {backup_path.name}\n",
        encoding="utf-8",
    )

    print(f"Sauvegarde créée : {backup_path.resolve()}")
    print(f"Taille : {backup_path.stat().st_size} octets")
    print(f"SHA-256 : {checksum}")
    print(f"Fichier de contrôle : {checksum_path.resolve()}")


if __name__ == "__main__":
    main()
