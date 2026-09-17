"""Browser webcam frame analysis via the unified recognition pipeline."""

import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile

from core.recognition_service import recognition_service

router = APIRouter(prefix="/api/v1/local_camera", tags=["local_camera"])


@router.post("/analyze_frame")
async def analyze_frame(file: UploadFile = File(...)):
    """Process a single frame captured by the browser webcam."""
    contents = await file.read()
    frame = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR)

    if frame is None or frame.size == 0:
        return {"faces": []}

    outcomes = await recognition_service.process_image(frame, source="browser_cam",
                                                       return_images=True)
    return {
        "faces": [
            {
                "type": "face",
                "person_id": o.person_id,
                "name": o.display_name,
                "status": o.status,
                "confidence": round(o.confidence, 3),
                "is_new": o.status == "registered",
                "bbox": o.bbox,
                "face_image": o.face_b64,
            }
            for o in outcomes
        ]
    }
