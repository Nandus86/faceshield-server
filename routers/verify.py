"""POST /api/v1/verify — single unified pipeline for uploaded images."""

import cv2
import numpy as np
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from core.recognition_service import recognition_service
from core.schemas import FaceResult, VerifyResponse

router = APIRouter(prefix="/api/v1", tags=["verify"])


@router.post("/verify", response_model=VerifyResponse)
async def verify_faces(
    file: UploadFile = File(..., description="JPEG or PNG image"),
    device_id: Optional[str] = Form(None, description="Optional edge device ID (e.g. pi-camera-01)"),
    source: Optional[str] = Form(None, description="Custom source name (defaults to 'pi:{device_id}' or 'api')"),
):
    """Detect faces in the uploaded image and run the recognition pipeline.

    Statuses per face:
    - **registered**: stranger confirmed for the first time -> new person.
    - **known**: recognized person logged (cooldown elapsed).
    - **known_cooldown**: recognized person within dedup window.
    - **pending**: unknown face awaiting confirmation sightings.
    - **unknown**: auto-registration disabled.
    """
    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Formato de imagem inválido.")

    source_tag = source or (f"pi:{device_id}" if device_id else "api")
    outcomes = await recognition_service.process_image(image, source=source_tag, return_images=True)

    return VerifyResponse(
        faces_detected=len(outcomes),
        results=[
            FaceResult(
                status=o.status,
                person_id=o.person_id,
                display_name=o.display_name,
                confidence=o.confidence,
                bbox=o.bbox,
                face_image=o.face_b64,
            )
            for o in outcomes
        ],
    )
