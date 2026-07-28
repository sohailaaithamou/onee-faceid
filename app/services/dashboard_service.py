from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.dashboard_settings import dashboard_settings
from app.core.exceptions import DatabaseOperationError
from app.schemas.dashboard import (
    DashboardCounts,
    DashboardCurrentPresenceItem,
    DashboardOverview,
    DashboardPresenceEventItem,
    DashboardRecognitionBreakdownItem,
    DashboardTrendItem,
    DashboardVisitItem,
)


ACTIVE_PRESENCE_STATUSES = ("VALID", "CORRECTED")


def _selected_day(value: date | None) -> date:
    tz = ZoneInfo(dashboard_settings.timezone)
    return value or datetime.now(tz).date()


def _day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(dashboard_settings.timezone)
    local_start = datetime.combine(day, time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )


def _trend_bounds_utc(day: date) -> tuple[date, datetime, datetime]:
    first_day = day - timedelta(days=dashboard_settings.trend_days - 1)
    start_utc, _ = _day_bounds_utc(first_day)
    _, end_utc = _day_bounds_utc(day)
    return first_day, start_utc, end_utc


def _overview_counts(
    db: Session,
    *,
    start_utc: datetime,
    end_utc: datetime,
) -> DashboardCounts:
    query = text(
        """
        WITH latest_presence AS (
            SELECT
                pe.person_id,
                pe.event_type,
                ROW_NUMBER() OVER (
                    PARTITION BY pe.person_id
                    ORDER BY pe.event_time DESC, pe.id DESC
                ) AS row_number
            FROM faceid.presence_event pe
            WHERE pe.status IN ('VALID', 'CORRECTED')
        )
        SELECT
            (
                SELECT COUNT(*)
                FROM faceid.person p
                JOIN faceid.employee_profile ep ON ep.person_id = p.id
                WHERE p.active = TRUE
                  AND ep.employment_status = 'ACTIVE'
            ) AS active_employees,
            (
                SELECT COUNT(*)
                FROM faceid.person p
                JOIN faceid.visitor_profile vp ON vp.person_id = p.id
                WHERE p.active = TRUE
                  AND vp.active = TRUE
            ) AS active_visitors,
            (
                SELECT COUNT(DISTINCT fe.person_id)
                FROM faceid.face_embedding fe
                JOIN faceid.person p ON p.id = fe.person_id
                WHERE fe.is_active = TRUE
                  AND p.active = TRUE
            ) AS enrolled_people,
            (
                SELECT COUNT(*)
                FROM latest_presence lp
                WHERE lp.row_number = 1
                  AND lp.event_type = 'ENTRY'
            ) AS currently_inside,
            (
                SELECT COUNT(*)
                FROM faceid.presence_event pe
                WHERE pe.event_time >= :start_utc
                  AND pe.event_time < :end_utc
                  AND pe.status IN ('VALID', 'CORRECTED')
                  AND pe.event_type = 'ENTRY'
            ) AS entries_today,
            (
                SELECT COUNT(*)
                FROM faceid.presence_event pe
                WHERE pe.event_time >= :start_utc
                  AND pe.event_time < :end_utc
                  AND pe.status IN ('VALID', 'CORRECTED')
                  AND pe.event_type = 'EXIT'
            ) AS exits_today,
            (
                SELECT COUNT(*)
                FROM faceid.visit v
                WHERE v.planned_start >= :start_utc
                  AND v.planned_start < :end_utc
            ) AS visits_today,
            (
                SELECT COUNT(*)
                FROM faceid.visit v
                WHERE v.status = 'IN_PROGRESS'
            ) AS visits_in_progress,
            (
                SELECT COUNT(*)
                FROM faceid.recognition_event re
                WHERE re.captured_at >= :start_utc
                  AND re.captured_at < :end_utc
            ) AS recognitions_today,
            (
                SELECT COUNT(*)
                FROM faceid.recognition_event re
                WHERE re.captured_at >= :start_utc
                  AND re.captured_at < :end_utc
                  AND re.decision = 'MATCHED'
            ) AS matched_today,
            (
                SELECT COUNT(*)
                FROM faceid.recognition_event re
                WHERE re.captured_at >= :start_utc
                  AND re.captured_at < :end_utc
                  AND re.decision = 'UNKNOWN'
            ) AS unknown_today
        """
    )

    row = db.execute(
        query,
        {"start_utc": start_utc, "end_utc": end_utc},
    ).mappings().one()

    recognitions = int(row["recognitions_today"] or 0)
    matched = int(row["matched_today"] or 0)
    success_rate = round((matched / recognitions) * 100, 2) if recognitions else 0.0

    return DashboardCounts(
        active_employees=int(row["active_employees"] or 0),
        active_visitors=int(row["active_visitors"] or 0),
        enrolled_people=int(row["enrolled_people"] or 0),
        currently_inside=int(row["currently_inside"] or 0),
        entries_today=int(row["entries_today"] or 0),
        exits_today=int(row["exits_today"] or 0),
        visits_today=int(row["visits_today"] or 0),
        visits_in_progress=int(row["visits_in_progress"] or 0),
        recognitions_today=recognitions,
        matched_today=matched,
        unknown_today=int(row["unknown_today"] or 0),
        recognition_success_rate=success_rate,
    )


def _current_presence(db: Session) -> list[DashboardCurrentPresenceItem]:
    tz = ZoneInfo(dashboard_settings.timezone)
    local_today = datetime.now(tz).date()

    query = text(
        """
        WITH ranked_presence AS (
            SELECT
                pe.*,
                ROW_NUMBER() OVER (
                    PARTITION BY pe.person_id
                    ORDER BY pe.event_time DESC, pe.id DESC
                ) AS row_number
            FROM faceid.presence_event pe
            WHERE pe.status IN ('VALID', 'CORRECTED')
        )
        SELECT
            rp.id AS presence_id,
            rp.person_id,
            p.first_name,
            p.last_name,
            p.person_type,
            rp.event_time,
            assignment.unit_name,
            eo.legal_name AS organization_name,
            rp.visit_id
        FROM ranked_presence rp
        JOIN faceid.person p ON p.id = rp.person_id
        LEFT JOIN faceid.visitor_profile vp ON vp.person_id = p.id
        LEFT JOIN faceid.external_organization eo ON eo.id = vp.organization_id
        LEFT JOIN LATERAL (
            SELECT ou.name AS unit_name
            FROM faceid.internal_assignment ia
            JOIN faceid.organizational_unit ou
              ON ou.id = ia.organizational_unit_id
            WHERE ia.person_id = p.id
              AND ia.start_date <= :local_today
              AND (ia.end_date IS NULL OR ia.end_date >= :local_today)
            ORDER BY ia.is_primary DESC, ia.start_date DESC, ia.id DESC
            LIMIT 1
        ) assignment ON TRUE
        WHERE rp.row_number = 1
          AND rp.event_type = 'ENTRY'
        ORDER BY rp.event_time DESC, rp.id DESC
        LIMIT :limit
        """
    )

    rows = db.execute(
        query,
        {
            "local_today": local_today,
            "limit": dashboard_settings.current_presence_limit,
        },
    ).mappings().all()

    return [DashboardCurrentPresenceItem(**dict(row)) for row in rows]


def _recent_presence_events(db: Session) -> list[DashboardPresenceEventItem]:
    query = text(
        """
        SELECT
            pe.id,
            pe.person_id,
            p.first_name,
            p.last_name,
            p.person_type,
            pe.event_type,
            pe.event_time,
            pe.source,
            pe.status
        FROM faceid.presence_event pe
        JOIN faceid.person p ON p.id = pe.person_id
        ORDER BY pe.event_time DESC, pe.id DESC
        LIMIT :limit
        """
    )

    rows = db.execute(
        query,
        {"limit": dashboard_settings.recent_events_limit},
    ).mappings().all()

    return [DashboardPresenceEventItem(**dict(row)) for row in rows]


def _visits_for_day(
    db: Session,
    *,
    start_utc: datetime,
    end_utc: datetime,
) -> list[DashboardVisitItem]:
    query = text(
        """
        SELECT
            v.id,
            v.visitor_person_id,
            CONCAT(visitor.first_name, ' ', visitor.last_name) AS visitor_name,
            organization.legal_name AS organization_name,
            v.purpose,
            v.planned_start,
            v.planned_end,
            v.status,
            CASE
                WHEN host_person.id IS NULL THEN NULL
                ELSE CONCAT(host_person.first_name, ' ', host_person.last_name)
            END AS host_employee_name,
            host_unit.name AS host_unit_name
        FROM faceid.visit v
        JOIN faceid.person visitor ON visitor.id = v.visitor_person_id
        JOIN faceid.external_organization organization
          ON organization.id = v.organization_id
        LEFT JOIN faceid.person host_person ON host_person.id = v.host_employee_id
        LEFT JOIN faceid.organizational_unit host_unit ON host_unit.id = v.host_unit_id
        WHERE v.planned_start >= :start_utc
          AND v.planned_start < :end_utc
        ORDER BY v.planned_start ASC, v.id ASC
        LIMIT :limit
        """
    )

    rows = db.execute(
        query,
        {
            "start_utc": start_utc,
            "end_utc": end_utc,
            "limit": dashboard_settings.visits_limit,
        },
    ).mappings().all()

    return [DashboardVisitItem(**dict(row)) for row in rows]


def _recognition_breakdown(
    db: Session,
    *,
    start_utc: datetime,
    end_utc: datetime,
) -> list[DashboardRecognitionBreakdownItem]:
    query = text(
        """
        SELECT re.decision, COUNT(*) AS count
        FROM faceid.recognition_event re
        WHERE re.captured_at >= :start_utc
          AND re.captured_at < :end_utc
        GROUP BY re.decision
        ORDER BY COUNT(*) DESC, re.decision ASC
        """
    )

    rows = db.execute(
        query,
        {"start_utc": start_utc, "end_utc": end_utc},
    ).mappings().all()

    return [
        DashboardRecognitionBreakdownItem(
            decision=str(row["decision"]),
            count=int(row["count"]),
        )
        for row in rows
    ]


def _trend(db: Session, *, selected_day: date) -> list[DashboardTrendItem]:
    first_day, start_utc, end_utc = _trend_bounds_utc(selected_day)
    timezone_name = dashboard_settings.timezone

    presence_query = text(
        """
        SELECT
            (timezone(:timezone_name, pe.event_time))::date AS local_day,
            COUNT(*) FILTER (WHERE pe.event_type = 'ENTRY') AS entries,
            COUNT(*) FILTER (WHERE pe.event_type = 'EXIT') AS exits
        FROM faceid.presence_event pe
        WHERE pe.event_time >= :start_utc
          AND pe.event_time < :end_utc
          AND pe.status IN ('VALID', 'CORRECTED')
        GROUP BY local_day
        ORDER BY local_day
        """
    )

    recognition_query = text(
        """
        SELECT
            (timezone(:timezone_name, re.captured_at))::date AS local_day,
            COUNT(*) FILTER (WHERE re.decision = 'MATCHED') AS matched,
            COUNT(*) FILTER (WHERE re.decision = 'UNKNOWN') AS unknown,
            COUNT(*) AS total_recognitions
        FROM faceid.recognition_event re
        WHERE re.captured_at >= :start_utc
          AND re.captured_at < :end_utc
        GROUP BY local_day
        ORDER BY local_day
        """
    )

    params = {
        "timezone_name": timezone_name,
        "start_utc": start_utc,
        "end_utc": end_utc,
    }
    presence_rows = db.execute(presence_query, params).mappings().all()
    recognition_rows = db.execute(recognition_query, params).mappings().all()

    by_day: dict[date, dict[str, int]] = {}
    for offset in range(dashboard_settings.trend_days):
        current_day = first_day + timedelta(days=offset)
        by_day[current_day] = {
            "entries": 0,
            "exits": 0,
            "matched": 0,
            "unknown": 0,
            "total_recognitions": 0,
        }

    for row in presence_rows:
        local_day = row["local_day"]
        if local_day in by_day:
            by_day[local_day]["entries"] = int(row["entries"] or 0)
            by_day[local_day]["exits"] = int(row["exits"] or 0)

    for row in recognition_rows:
        local_day = row["local_day"]
        if local_day in by_day:
            by_day[local_day]["matched"] = int(row["matched"] or 0)
            by_day[local_day]["unknown"] = int(row["unknown"] or 0)
            by_day[local_day]["total_recognitions"] = int(
                row["total_recognitions"] or 0
            )

    return [
        DashboardTrendItem(day=day, **values)
        for day, values in sorted(by_day.items())
    ]


def get_dashboard_overview(
    db: Session,
    *,
    day: date | None = None,
) -> DashboardOverview:
    selected_day = _selected_day(day)
    start_utc, end_utc = _day_bounds_utc(selected_day)
    tz = ZoneInfo(dashboard_settings.timezone)

    try:
        return DashboardOverview(
            generated_at=datetime.now(tz),
            selected_day=selected_day,
            timezone=dashboard_settings.timezone,
            counts=_overview_counts(
                db,
                start_utc=start_utc,
                end_utc=end_utc,
            ),
            current_presence=_current_presence(db),
            recent_presence_events=_recent_presence_events(db),
            visits=_visits_for_day(
                db,
                start_utc=start_utc,
                end_utc=end_utc,
            ),
            recognition_breakdown=_recognition_breakdown(
                db,
                start_utc=start_utc,
                end_utc=end_utc,
            ),
            trend=_trend(db, selected_day=selected_day),
        )
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de charger les indicateurs du tableau de bord."
        ) from exc
