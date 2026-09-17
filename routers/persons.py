"""CRUD /api/v1/persons — registered people, manual registration and history."""

import asyncio
import base64
import logging
import os
import uuid
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

import config
from core.database import get_db, session_scope
from core.events import event_bus
from core.face_cache import face_cache
from core.models import EventPresence, Person, PresenceSession, VerificationLog
from core.recognition_service import recognition_service
from core.schemas import MergePersonsResponse, PersonOut, PersonUpdate, RegisterFaceRequest, VerificationLogOut, image_url_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/persons", tags=["persons"])


def _to_out(person: Person) -> PersonOut:
    return PersonOut(
        id=person.id,
        name=person.name,
        display_name=person.display_name,
        face_image_path=person.face_image_path,
        image_url=image_url_for(person.face_image_path),
        sighting_count=person.sighting_count or 0,
        first_seen_at=person.first_seen_at,
        last_seen_at=person.last_seen_at,
        created_at=person.created_at,
    )


async def _get_person_or_404(session: AsyncSession, person_id: int) -> Person:
    result = await session.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada.")
    return person


@router.get("", response_model=List[PersonOut])
async def list_persons(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
):
    """List registered people (newest first) with pagination."""
    result = await session.execute(
        select(Person).order_by(desc(Person.created_at)).offset(skip).limit(limit)
    )
    return [_to_out(p) for p in result.scalars().all()]


@router.get("/count")
async def count_persons(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(func.count(Person.id)))
    return {"count": result.scalar() or 0}


@router.post("/register", response_model=PersonOut, status_code=201)
async def register_named_face(request: RegisterFaceRequest):
    """Register a new person with a name from a base64 image.

    The face is detected via InsightFace and stored directly in the database,
    sharing the exact same identity space as automatic registrations.
    """
    from core.face_engine import face_engine

    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="O nome não pode ser vazio.")

    try:
        payload = request.image_base64.split(",")[-1]
        nparr = np.frombuffer(base64.b64decode(payload), dtype=np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"Erro ao decodificar imagem: {err}")

    if image is None or image.size == 0:
        raise HTTPException(status_code=400, detail="Imagem inválida.")

    cfg = config.get_settings()
    detected = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: face_engine.detect_faces(
            image, min_face_size=cfg.MIN_FACE_SIZE, min_det_score=cfg.MIN_DET_SCORE
        ),
    )
    if not detected:
        raise HTTPException(status_code=400, detail="Nenhum rosto foi detectado na imagem.")

    # Best-quality crop wins.
    face = max(detected, key=lambda f: f.det_score)

    directory = config.FACES_DIR
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"face_{uuid.uuid4().hex}.jpg")
    cv2.imwrite(path, face.face_image)

    vec = np.asarray(face.embedding, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    async with session_scope() as session:
        person = Person(name=name, embedding=vec.tolist(), face_image_path=path, sighting_count=1)
        session.add(person)
        await session.flush()
        session.add(VerificationLog(
            person_id=person.id, confidence=1.0, frame_image_path=path,
            source="cadastro_manual", is_new_registration=True,
        ))
        out = _to_out(person)
        person_id = person.id

    face_cache.add(person_id, vec, name=name)
    await event_bus.publish_async("person_registered",
                                  {"person_id": person_id, "name": name, "source": "manual"})
    logger.info("Cadastro manual: '%s' (id=%d)", name, person_id)
    return out


@router.get("/{person_id}", response_model=PersonOut)
async def get_person(person_id: int, session: AsyncSession = Depends(get_db)):
    person = await _get_person_or_404(session, person_id)
    return _to_out(person)


@router.put("/{person_id}", response_model=PersonOut)
async def update_person(
    person_id: int,
    data: PersonUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Rename a person (auto-registered people start unnamed)."""
    person = await _get_person_or_404(session, person_id)

    if data.name is not None:
        stripped = data.name.strip()
        if not stripped:
            raise HTTPException(status_code=400, detail="O nome não pode ser vazio.")
        person.name = stripped

    await session.commit()
    await session.refresh(person)
    face_cache.rename(person.id, person.name)
    return _to_out(person)


@router.delete("/{person_id}")
async def delete_person(person_id: int, session: AsyncSession = Depends(get_db)):
    """Delete a person, their photos and all their logs/sessions."""
    person = await _get_person_or_404(session, person_id)

    if person.face_image_path and os.path.exists(person.face_image_path):
        try:
            os.remove(person.face_image_path)
        except Exception as err:
            logger.warning("Falha ao remover foto %s: %s", person.face_image_path, err)

    await session.delete(person)
    await session.commit()
    face_cache.remove(person_id)
    return {"detail": "Pessoa excluída com sucesso."}


@router.get("/{person_id}/logs", response_model=List[VerificationLogOut])
async def get_person_logs(
    person_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
):
    """Verification history for one person."""
    person = await _get_person_or_404(session, person_id)

    result = await session.execute(
        select(VerificationLog)
        .where(VerificationLog.person_id == person_id)
        .order_by(desc(VerificationLog.detected_at))
        .offset(skip).limit(limit)
    )
    logs = result.scalars().all()
    return [
        VerificationLogOut(
            id=log.id,
            person_id=log.person_id,
            confidence=log.confidence,
            detected_at=log.detected_at,
            source=log.source,
            is_new_registration=log.is_new_registration,
            person_name=person.display_name,
            image_url=image_url_for(log.frame_image_path),
        )
        for log in logs
    ]


@router.get("/{person_id}/image")
async def get_person_image(person_id: int, session: AsyncSession = Depends(get_db)):
    """Serve the person's registered photo or a default avatar."""
    person = await _get_person_or_404(session, person_id)
    if person.face_image_path and os.path.exists(person.face_image_path):
        return FileResponse(person.face_image_path, media_type="image/jpeg")

    avatar_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "static", "avatar.svg")
    if os.path.exists(avatar_path):
        return FileResponse(avatar_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Imagem não encontrada.")


@router.post("/{person_id}/reprocess", response_model=PersonOut)
async def reprocess_embedding(person_id: int):
    """Re-extract the embedding from the stored photo (fixes stale profiles)."""
    from core.face_engine import face_engine

    async with session_scope() as session:
        result = await session.execute(select(Person).where(Person.id == person_id))
        person = result.scalar_one_or_none()
        if not person or not person.face_image_path \
                or not os.path.exists(person.face_image_path):
            raise HTTPException(status_code=404, detail="Pessoa ou foto não encontrada.")

        image = cv2.imread(person.face_image_path)
        if image is None:
            raise HTTPException(status_code=400, detail="Foto corrompida.")

        cfg = config.get_settings()
        detected = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: face_engine.detect_faces(image, min_face_size=20, min_det_score=0.30),
        )
        if not detected:
            raise HTTPException(status_code=400, detail="Nenhum rosto na foto armazenada.")

        vec = np.asarray(detected[0].embedding, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        person.embedding = vec.tolist()
        out = _to_out(person)

    face_cache.update(person_id, vec)
    return out


@router.post("/{source_id}/merge/{target_id}", response_model=MergePersonsResponse)
async def merge_persons(source_id: int, target_id: int):
    """Merge two profiles into one (source_id -> target_id).

    Reassigns all verification logs, presence sessions, and event presences
    from source to target, calculates a weighted average embedding,
    updates the face cache, and deletes the source profile.
    """
    if source_id == target_id:
        raise HTTPException(status_code=400, detail="Não é possível mesclar uma pessoa com ela mesma.")

    async with session_scope() as session:
        source = (await session.execute(select(Person).where(Person.id == source_id))).scalar_one_or_none()
        target = (await session.execute(select(Person).where(Person.id == target_id))).scalar_one_or_none()

        if not source:
            raise HTTPException(status_code=404, detail=f"Pessoa de origem #{source_id} não encontrada.")
        if not target:
            raise HTTPException(status_code=404, detail=f"Pessoa de destino #{target_id} não encontrada.")

        # 1. Compute weighted average embedding
        w_source = max(1, source.sighting_count or 1)
        w_target = max(1, target.sighting_count or 1)

        vec_src = np.asarray(source.embedding, dtype=np.float32).reshape(-1)
        vec_tgt = np.asarray(target.embedding, dtype=np.float32).reshape(-1)

        blended = (w_target * vec_tgt + w_source * vec_src) / (w_target + w_source)
        norm = np.linalg.norm(blended)
        if norm > 0:
            blended = blended / norm

        target.embedding = blended.tolist()
        target.sighting_count = w_target + w_source
        if source.first_seen_at and (not target.first_seen_at or source.first_seen_at < target.first_seen_at):
            target.first_seen_at = source.first_seen_at
        if source.last_seen_at and (not target.last_seen_at or source.last_seen_at > target.last_seen_at):
            target.last_seen_at = source.last_seen_at

        # 2. Reassign verification logs
        log_res = await session.execute(
            update(VerificationLog)
            .where(VerificationLog.person_id == source_id)
            .values(person_id=target_id)
        )
        logs_count = log_res.rowcount if hasattr(log_res, "rowcount") else 0

        # 3. Reassign presence sessions
        sess_res = await session.execute(
            update(PresenceSession)
            .where(PresenceSession.person_id == source_id)
            .values(person_id=target_id)
        )
        sessions_count = sess_res.rowcount if hasattr(sess_res, "rowcount") else 0

        # 4. Reassign event presences (delete duplicate event presences first)
        target_events_res = await session.execute(
            select(EventPresence.event_id).where(EventPresence.person_id == target_id)
        )
        target_event_ids = set(target_events_res.scalars().all())

        if target_event_ids:
            await session.execute(
                delete(EventPresence).where(
                    EventPresence.person_id == source_id,
                    EventPresence.event_id.in_(target_event_ids),
                )
            )

        await session.execute(
            update(EventPresence)
            .where(EventPresence.person_id == source_id)
            .values(person_id=target_id)
        )

        # 5. Delete source person and image file
        source_img = source.face_image_path
        await session.delete(source)

        target_display = target.display_name
        target_name = target.name

    if source_img and os.path.exists(source_img):
        try:
            os.remove(source_img)
        except Exception as err:
            logger.warning("Falha ao remover imagem da pessoa mesclada %s: %s", source_img, err)

    # 6. Synchronize in-memory face cache
    face_cache.update(target_id, blended, name=target_name, has_name=bool(target_name))
    face_cache.remove(source_id)

    logger.info("Mesclada Pessoa #%d em %s (id=%d). Logs transferidos: %d",
                source_id, target_display, target_id, logs_count)

    return MergePersonsResponse(
        success=True,
        target_id=target_id,
        target_name=target_display,
        reassigned_logs_count=logs_count,
        reassigned_presence_sessions_count=sessions_count,
        message=f"Pessoa #{source_id} foi mesclada com sucesso em {target_display} (ID #{target_id}).",
    )

