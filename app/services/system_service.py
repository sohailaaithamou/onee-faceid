from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.schemas.system import (
    SystemCheck,
    SystemCheckState,
    SystemReadiness,
    SystemReadinessSummary,
)
from app.vision.settings import face_settings


REQUIRED_TABLES = {
    "external_organization",
    "organizational_unit",
    "person",
    "employee_profile",
    "visitor_profile",
    "internal_assignment",
    "face_embedding",
    "user_account",
    "visit",
    "recognition_event",
    "presence_event",
}

REQUIRED_VIEWS = {
    "v_person_details",
    "v_current_presence",
}

REQUIRED_TRIGGERS = {
    "trg_external_organization_updated_at",
    "trg_organizational_unit_updated_at",
    "trg_person_updated_at",
    "trg_person_type_change",
    "trg_user_account_updated_at",
    "trg_visit_updated_at",
    "trg_employee_profile_type",
    "trg_visitor_profile_type",
    "trg_organizational_hierarchy",
    "trg_internal_assignment_person",
    "trg_primary_assignment_overlap",
    "trg_face_embedding_values",
    "trg_prepare_visit",
    "trg_validate_presence_links",
}


def _check(
    key: str,
    label: str,
    state: SystemCheckState,
    detail: str,
    value: object | None = None,
) -> SystemCheck:
    return SystemCheck(
        key=key,
        label=label,
        state=state,
        detail=detail,
        value=value,
    )


def _relation_names(db: Session, relkind: str) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT c.relname
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n
              ON n.oid = c.relnamespace
            WHERE n.nspname = 'faceid'
              AND c.relkind = :relkind
            """
        ),
        {"relkind": relkind},
    ).scalars()
    return set(rows)


def _trigger_names(db: Session) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT t.tgname
            FROM pg_catalog.pg_trigger t
            JOIN pg_catalog.pg_class c
              ON c.oid = t.tgrelid
            JOIN pg_catalog.pg_namespace n
              ON n.oid = c.relnamespace
            WHERE n.nspname = 'faceid'
              AND NOT t.tgisinternal
            """
        )
    ).scalars()
    return set(rows)


def _model_file_check(key: str, label: str, path: Path) -> SystemCheck:
    resolved = path.resolve()
    if not resolved.is_file():
        return _check(
            key,
            label,
            SystemCheckState.FAIL,
            f"Fichier introuvable : {resolved}",
            str(resolved),
        )

    size = resolved.stat().st_size
    if size <= 0:
        return _check(
            key,
            label,
            SystemCheckState.FAIL,
            f"Le fichier existe mais il est vide : {resolved}",
            size,
        )

    return _check(
        key,
        label,
        SystemCheckState.PASS,
        f"Modèle disponible : {resolved.name}",
        {"path": str(resolved), "bytes": size},
    )


def get_system_readiness(db: Session) -> SystemReadiness:
    checks: list[SystemCheck] = []

    try:
        identity = db.execute(
            text(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS database_user,
                    current_schema() AS current_schema
                """
            )
        ).mappings().one()

        database_name = str(identity["database_name"])
        database_user = str(identity["database_user"])
        current_schema = str(identity["current_schema"])

        checks.append(
            _check(
                "database_connection",
                "Connexion PostgreSQL",
                SystemCheckState.PASS,
                "La connexion PostgreSQL fonctionne.",
                database_name,
            )
        )

        schema_state = (
            SystemCheckState.PASS
            if current_schema == "faceid"
            else SystemCheckState.WARNING
        )
        checks.append(
            _check(
                "search_path",
                "Schéma PostgreSQL courant",
                schema_state,
                (
                    "Le schéma courant est faceid."
                    if current_schema == "faceid"
                    else "Le schéma courant n'est pas faceid. Les requêtes qualifiées restent valides, mais vérifiez le search_path."
                ),
                current_schema,
            )
        )

        existing_tables = _relation_names(db, "r")
        missing_tables = sorted(REQUIRED_TABLES - existing_tables)
        checks.append(
            _check(
                "required_tables",
                "Tables obligatoires",
                (
                    SystemCheckState.PASS
                    if not missing_tables
                    else SystemCheckState.FAIL
                ),
                (
                    "Les 11 tables obligatoires existent."
                    if not missing_tables
                    else f"Tables manquantes : {', '.join(missing_tables)}"
                ),
                {
                    "expected": len(REQUIRED_TABLES),
                    "found": len(REQUIRED_TABLES & existing_tables),
                    "missing": missing_tables,
                },
            )
        )

        existing_views = _relation_names(db, "v")
        missing_views = sorted(REQUIRED_VIEWS - existing_views)
        checks.append(
            _check(
                "required_views",
                "Vues du dashboard",
                (
                    SystemCheckState.PASS
                    if not missing_views
                    else SystemCheckState.FAIL
                ),
                (
                    "Les vues v_person_details et v_current_presence existent."
                    if not missing_views
                    else f"Vues manquantes : {', '.join(missing_views)}"
                ),
                {"missing": missing_views},
            )
        )

        existing_triggers = _trigger_names(db)
        missing_triggers = sorted(REQUIRED_TRIGGERS - existing_triggers)
        checks.append(
            _check(
                "required_triggers",
                "Triggers d'intégrité",
                (
                    SystemCheckState.PASS
                    if not missing_triggers
                    else SystemCheckState.FAIL
                ),
                (
                    "Tous les triggers d'intégrité attendus existent."
                    if not missing_triggers
                    else f"Triggers manquants : {', '.join(missing_triggers)}"
                ),
                {
                    "expected": len(REQUIRED_TRIGGERS),
                    "found": len(REQUIRED_TRIGGERS & existing_triggers),
                    "missing": missing_triggers,
                },
            )
        )

        admin_count = int(
            db.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM faceid.user_account
                    WHERE role = 'ADMIN'
                      AND active = TRUE
                    """
                )
            )
            or 0
        )
        checks.append(
            _check(
                "active_admin",
                "Compte administrateur actif",
                (
                    SystemCheckState.PASS
                    if admin_count >= 1
                    else SystemCheckState.FAIL
                ),
                (
                    f"{admin_count} compte(s) ADMIN actif(s)."
                    if admin_count >= 1
                    else "Aucun compte ADMIN actif."
                ),
                admin_count,
            )
        )

        profile_stats = db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE p.person_type = 'EMPLOYEE'
                          AND ep.person_id IS NULL
                    ) AS employee_without_profile,
                    COUNT(*) FILTER (
                        WHERE p.person_type = 'VISITOR'
                          AND vp.person_id IS NULL
                    ) AS visitor_without_profile,
                    COUNT(*) FILTER (
                        WHERE ep.person_id IS NOT NULL
                          AND vp.person_id IS NOT NULL
                    ) AS person_with_both_profiles
                FROM faceid.person p
                LEFT JOIN faceid.employee_profile ep
                  ON ep.person_id = p.id
                LEFT JOIN faceid.visitor_profile vp
                  ON vp.person_id = p.id
                """
            )
        ).mappings().one()
        profile_invalid = sum(int(value or 0) for value in profile_stats.values())
        checks.append(
            _check(
                "person_profiles",
                "Cohérence des profils personnes",
                (
                    SystemCheckState.PASS
                    if profile_invalid == 0
                    else SystemCheckState.FAIL
                ),
                (
                    "Chaque personne possède le profil correspondant à son type."
                    if profile_invalid == 0
                    else "Des personnes ont un profil absent ou incompatible."
                ),
                dict(profile_stats),
            )
        )

        invalid_hierarchy = int(
            db.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM faceid.organizational_unit child
                    LEFT JOIN faceid.organizational_unit parent
                      ON parent.id = child.parent_id
                    WHERE
                        (child.unit_type = 'REGIONAL_DIRECTION' AND child.parent_id IS NOT NULL)
                        OR
                        (child.unit_type = 'DIVISION' AND (
                            child.parent_id IS NULL
                            OR parent.unit_type IS DISTINCT FROM 'REGIONAL_DIRECTION'
                        ))
                        OR
                        (child.unit_type = 'SERVICE' AND (
                            child.parent_id IS NULL
                            OR parent.unit_type IS DISTINCT FROM 'DIVISION'
                        ))
                    """
                )
            )
            or 0
        )
        checks.append(
            _check(
                "organizational_hierarchy",
                "Hiérarchie ONEE",
                (
                    SystemCheckState.PASS
                    if invalid_hierarchy == 0
                    else SystemCheckState.FAIL
                ),
                (
                    "La hiérarchie Direction régionale → Division → Service est cohérente."
                    if invalid_hierarchy == 0
                    else f"{invalid_hierarchy} unité(s) ont une hiérarchie invalide."
                ),
                invalid_hierarchy,
            )
        )

        embedding_stats = db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_active = TRUE) AS active_embeddings,
                    COUNT(DISTINCT person_id) FILTER (WHERE is_active = TRUE) AS enrolled_people,
                    COUNT(*) FILTER (
                        WHERE array_ndims(embedding) IS DISTINCT FROM 1
                           OR cardinality(embedding) IS DISTINCT FROM 128
                           OR array_position(embedding, NULL) IS NOT NULL
                    ) AS invalid_embeddings
                FROM faceid.face_embedding
                """
            )
        ).mappings().one()
        invalid_embeddings = int(embedding_stats["invalid_embeddings"] or 0)
        active_embeddings = int(embedding_stats["active_embeddings"] or 0)
        if invalid_embeddings > 0:
            embedding_state = SystemCheckState.FAIL
            embedding_detail = f"{invalid_embeddings} embedding(s) sont invalides."
        elif active_embeddings == 0:
            embedding_state = SystemCheckState.WARNING
            embedding_detail = "Aucun embedding actif : la reconnaissance ne peut reconnaître personne."
        else:
            embedding_state = SystemCheckState.PASS
            embedding_detail = f"{active_embeddings} embedding(s) actif(s) et valides."
        checks.append(
            _check(
                "face_embeddings",
                "Embeddings SFace",
                embedding_state,
                embedding_detail,
                dict(embedding_stats),
            )
        )

        invalid_recognitions = int(
            db.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM faceid.recognition_event
                    WHERE
                        (
                            decision = 'MATCHED'
                            AND (
                                matched_person_id IS NULL
                                OR similarity_score IS NULL
                                OR threshold_used IS NULL
                                OR similarity_score < threshold_used
                            )
                        )
                        OR
                        (
                            decision <> 'MATCHED'
                            AND matched_person_id IS NOT NULL
                        )
                    """
                )
            )
            or 0
        )
        checks.append(
            _check(
                "recognition_integrity",
                "Intégrité des reconnaissances",
                (
                    SystemCheckState.PASS
                    if invalid_recognitions == 0
                    else SystemCheckState.FAIL
                ),
                (
                    "Les événements de reconnaissance sont cohérents."
                    if invalid_recognitions == 0
                    else f"{invalid_recognitions} reconnaissance(s) sont incohérentes."
                ),
                invalid_recognitions,
            )
        )

        invalid_presences = int(
            db.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM faceid.presence_event pe
                    LEFT JOIN faceid.recognition_event re
                      ON re.id = pe.recognition_event_id
                    LEFT JOIN faceid.visit v
                      ON v.id = pe.visit_id
                    WHERE
                        (
                            pe.source = 'FACE'
                            AND (
                                re.id IS NULL
                                OR re.decision <> 'MATCHED'
                                OR re.matched_person_id IS DISTINCT FROM pe.person_id
                            )
                        )
                        OR
                        (
                            pe.source = 'MANUAL'
                            AND (
                                pe.recognition_event_id IS NOT NULL
                                OR pe.created_by IS NULL
                            )
                        )
                        OR
                        (
                            pe.visit_id IS NOT NULL
                            AND v.visitor_person_id IS DISTINCT FROM pe.person_id
                        )
                    """
                )
            )
            or 0
        )
        checks.append(
            _check(
                "presence_integrity",
                "Intégrité des entrées et sorties",
                (
                    SystemCheckState.PASS
                    if invalid_presences == 0
                    else SystemCheckState.FAIL
                ),
                (
                    "Les pointages sont correctement liés aux reconnaissances et aux visites."
                    if invalid_presences == 0
                    else f"{invalid_presences} pointage(s) ont des liens incohérents."
                ),
                invalid_presences,
            )
        )

        invalid_visits = int(
            db.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM faceid.visit
                    WHERE host_employee_id IS NULL
                      AND host_unit_id IS NULL
                    """
                )
            )
            or 0
        )
        checks.append(
            _check(
                "visit_hosts",
                "Hôtes des visites",
                (
                    SystemCheckState.PASS
                    if invalid_visits == 0
                    else SystemCheckState.FAIL
                ),
                (
                    "Toutes les visites possèdent un agent ou une unité hôte."
                    if invalid_visits == 0
                    else f"{invalid_visits} visite(s) ne possèdent aucun hôte."
                ),
                invalid_visits,
            )
        )

        checks.append(
            _model_file_check(
                "yunet_model",
                "Modèle YuNet",
                face_settings.yunet_path,
            )
        )
        checks.append(
            _model_file_check(
                "sface_model",
                "Modèle SFace",
                face_settings.sface_path,
            )
        )

    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseOperationError(
            "Impossible d'exécuter l'audit final de PostgreSQL."
        ) from exc

    passed = sum(check.state == SystemCheckState.PASS for check in checks)
    warnings = sum(check.state == SystemCheckState.WARNING for check in checks)
    failed = sum(check.state == SystemCheckState.FAIL for check in checks)

    if failed > 0:
        status = "NOT_READY"
    elif warnings > 0:
        status = "WARNING"
    else:
        status = "READY"

    return SystemReadiness(
        status=status,
        generated_at=datetime.now(timezone.utc),
        database=database_name,
        database_user=database_user,
        current_schema=current_schema,
        summary=SystemReadinessSummary(
            passed=passed,
            warnings=warnings,
            failed=failed,
        ),
        checks=checks,
    )
