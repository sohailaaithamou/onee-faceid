from __future__ import annotations

import argparse
from getpass import getpass

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Person, UserAccount


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Créer le premier compte ADMIN du dashboard ONEE Face ID."
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--person-id", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    username = args.username.strip()
    if len(username) < 3 or any(character.isspace() for character in username):
        raise SystemExit("Nom d'utilisateur invalide.")

    password = getpass("Mot de passe ADMIN : ")
    confirmation = getpass("Confirmer le mot de passe : ")

    if password != confirmation:
        raise SystemExit("Les mots de passe ne correspondent pas.")
    if len(password) < 10:
        raise SystemExit("Le mot de passe doit contenir au moins 10 caractères.")

    with SessionLocal() as db:
        duplicate = db.scalar(
            select(UserAccount.id).where(
                func.lower(func.btrim(UserAccount.username)) == username.lower()
            )
        )
        if duplicate is not None:
            raise SystemExit("Ce nom d'utilisateur existe déjà.")

        if args.person_id is not None:
            person = db.get(Person, args.person_id)
            if person is None:
                raise SystemExit("Personne associée introuvable.")
            if person.person_type != "EMPLOYEE" or not person.active:
                raise SystemExit("La personne doit être un agent ONEE actif.")

        account = UserAccount(
            person_id=args.person_id,
            username=username,
            password_hash=hash_password(password),
            role="ADMIN",
            active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

    print(f"Compte ADMIN créé : {username} (id={account.id})")


if __name__ == "__main__":
    main()
