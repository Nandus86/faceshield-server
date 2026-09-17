import csv
import datetime
import io
import logging

from fastapi import APIRouter, Query, Response
from sqlalchemy import desc, func, select

from core.camera_manager import camera_manager
from core.database import as_utc, is_using_sqlite, session_scope
from core.face_engine import face_engine
from core.models import Person, PresenceSession, VerificationLog
from core.presence_service import get_active_sessions
from core.schemas import VerificationLogOut, image_url_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"])


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _local_midnight_utc() -> datetime.datetime:
    local_now = datetime.datetime.now().astimezone()
    midnight_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_local.astimezone(datetime.timezone.utc)


@router.get("/stats")
async def get_stats():
    """Live system statistics derived from the database."""
    active_people = await get_active_sessions()
    midnight = _local_midnight_utc()

    async with session_scope() as session:
        total_registered = (
            await session.execute(select(func.count(Person.id)))
        ).scalar() or 0

        result = await session.execute(
            select(
                VerificationLog.detected_at,
                VerificationLog.is_new_registration,
            ).where(VerificationLog.detected_at >= _now() - datetime.timedelta(days=2))
        )
        recent = result.all()

        session_result = await session.execute(
            select(PresenceSession.started_at, PresenceSession.ended_at)
            .where(PresenceSession.started_at >= _now() - datetime.timedelta(days=2))
        )
        session_rows = session_result.all()

    detections_today = 0
    new_registrations_today = 0
    for detected_at, is_new in recent:
        dt = as_utc(detected_at)
        if dt and dt >= midnight:
            detections_today += 1
            if is_new:
                new_registrations_today += 1

    durations_minutes = []
    now = _now()
    for started_at, ended_at in session_rows:
        start = as_utc(started_at)
        if not start or start < midnight:
            continue
        end = as_utc(ended_at) or now
        durations_minutes.append((end - start).total_seconds() / 60)

    avg_stay_minutes = (
        round(sum(durations_minutes) / len(durations_minutes), 1)
        if durations_minutes else 0.0
    )

    camera_status = camera_manager.get_status()
    return {
        "active_people": active_people,
        "active_count": len(active_people),
        "total_registered": total_registered,
        "detections_today": detections_today,
        "new_registrations_today": new_registrations_today,
        "avg_stay_minutes": avg_stay_minutes,
        "fps": camera_status["fps"],
        "camera_status": camera_status["status"],
        "camera_active": camera_status["active"],
        "database_status": "SQLite (fallback)" if is_using_sqlite() else "PostgreSQL + pgvector",
        "engine_loaded": face_engine.is_available(),
    }


@router.get("/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=500),
    event_type: str = Query("ALL", pattern="^(ALL|known|registered)$"),
    source: str = Query("ALL"),
    person_id: int = Query(0, ge=0),
):
    """Unified detection history straight from the database.

    event_type: `known` = recognition of an existing person,
    `registered` = first-time automatic registration.
    """
    stmt = (
        select(VerificationLog, Person.name)
        .join(Person, Person.id == VerificationLog.person_id)
        .order_by(desc(VerificationLog.detected_at))
        .limit(limit * 3)
    )

    async with session_scope() as session:
        result = await session.execute(stmt)
        rows = result.all()

    out = []
    for log, person_name in rows:
        if event_type == "registered" and not log.is_new_registration:
            continue
        if event_type == "known" and log.is_new_registration:
            continue
        if source != "ALL" and (log.source or "") != source:
            continue
        if person_id and log.person_id != person_id:
            continue

        display = person_name if person_name else f"Pessoa #{log.person_id}"
        out.append(VerificationLogOut(
            id=log.id,
            person_id=log.person_id,
            confidence=log.confidence,
            detected_at=log.detected_at,
            source=log.source,
            is_new_registration=log.is_new_registration,
            person_name=display,
            image_url=image_url_for(log.frame_image_path),
        ))
        if len(out) >= limit:
            break

    return out


@router.get("/logs/export.csv")
async def export_logs_csv(
    limit: int = Query(1000, ge=1, le=10000),
    source: str = Query("ALL"),
):
    """Export verification logs to a CSV file."""
    stmt = (
        select(VerificationLog, Person.name)
        .join(Person, Person.id == VerificationLog.person_id)
        .order_by(desc(VerificationLog.detected_at))
        .limit(limit)
    )

    async with session_scope() as session:
        result = await session.execute(stmt)
        rows = result.all()

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID Log", "ID Pessoa", "Nome / Identificacao", "Confianca (%)", "Data e Hora", "Fonte", "Tipo de Evento"])

    for log, person_name in rows:
        if source != "ALL" and (log.source or "") != source:
            continue
        display = person_name if person_name else f"Pessoa #{log.person_id}"
        dt = as_utc(log.detected_at)
        dt_str = dt.strftime("%d/%m/%Y %H:%M:%S") if dt else ""
        event_type = "Novo Cadastro" if log.is_new_registration else "Reconhecimento"
        writer.writerow([
            log.id,
            log.person_id,
            display,
            f"{log.confidence * 100:.1f}%",
            dt_str,
            log.source or "",
            event_type,
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=logs_reconhecimento.csv"},
    )


@router.get("/presence")
async def get_presence():
    """People currently present in the environment."""
    return {"active": await get_active_sessions()}


@router.get("/presence/export.csv")
async def export_presence_csv():
    """Export currently present people to a CSV file."""
    active = await get_active_sessions()

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID Pessoa", "Nome / Identificacao", "Fonte", "Inicio da Presenca", "Ultimo Avistamento", "Tempo Total (s)"])

    for p in active:
        writer.writerow([
            p["person_id"],
            p["display_name"],
            p.get("source") or "",
            p["started_at"],
            p["last_seen_at"],
            p["duration_seconds"],
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=presenca_atual.csv"},
    )


@router.get("/analytics/timeline")
async def get_analytics_timeline():
    """Hourly detection counts for the past 24 hours to feed interactive charts."""
    now = _now()
    since = now - datetime.timedelta(hours=24)

    async with session_scope() as session:
        result = await session.execute(
            select(VerificationLog.detected_at, VerificationLog.is_new_registration)
            .where(VerificationLog.detected_at >= since)
        )
        rows = result.all()

    # Bucket into 24 hours
    buckets = {}
    for i in range(24):
        slot = since + datetime.timedelta(hours=i)
        hour_key = slot.strftime("%H:00")
        buckets[hour_key] = {"hour": hour_key, "detections": 0, "new_registrations": 0}

    for detected_at, is_new in rows:
        dt = as_utc(detected_at)
        if dt:
            hour_key = dt.strftime("%H:00")
            if hour_key in buckets:
                buckets[hour_key]["detections"] += 1
                if is_new:
                    buckets[hour_key]["new_registrations"] += 1

    return {"timeline": list(buckets.values())}
