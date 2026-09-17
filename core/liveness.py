"""Passive face liveness and image quality assessment.

Calculates sharpness (Laplacian variance), bounding box geometry sanity,
and color variance to prevent blurry images, extreme artifacts, and basic spoofing.
"""

from typing import List, Optional, Tuple
import cv2
import numpy as np


def check_liveness_and_quality(
    face_image: np.ndarray,
    bbox: List[float],
    min_sharpness: float = 35.0,
) -> Tuple[bool, float, str]:
    """Evaluate if a detected face crop meets quality and anti-spoofing criteria.

    Returns:
        (is_passed, quality_score, reason_message)
    """
    if face_image is None or face_image.size == 0:
        return False, 0.0, "Imagem de rosto vazia."

    h, w = face_image.shape[:2]
    if h < 20 or w < 20:
        return False, 0.0, "Rosto muito pequeno para validação confiável."

    # 1. Geometry sanity check
    aspect_ratio = float(w) / float(h)
    if aspect_ratio < 0.4 or aspect_ratio > 2.5:
        return False, 0.2, f"Proporção do rosto atípica ({aspect_ratio:.2f})."

    # 2. Sharpness check via Laplacian variance
    gray = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY) if len(face_image.shape) == 3 else face_image
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = float(laplacian.var())

    # 3. Dynamic contrast / standard deviation check
    std_dev = float(np.std(gray))
    if std_dev < 10.0:
        return False, 0.1, "Contraste insuficiente (imagem uniforme/apagada)."

    quality_score = min(1.0, variance / 200.0)

    if variance < min_sharpness:
        return False, quality_score, f"Rosto borrado ou sem foco (nitidez: {variance:.1f} < {min_sharpness})."

    return True, quality_score, "Aprovado"


def check_occlusion_and_integrity(
    face_image: np.ndarray,
    bbox: Optional[List[float]] = None,
    kps: Optional[List[List[float]]] = None,
) -> Tuple[bool, str]:
    """Check if the face is partially occluded (e.g. mouth/lower face covered).

    Returns:
        (is_occluded, reason)
    """
    if face_image is None or face_image.size == 0:
        return True, "Imagem vazia."

    h, w = face_image.shape[:2]
    if h < 24 or w < 24:
        return False, "Imagem muito pequena para análise de oclusão."

    # 1. Landmark geometrical consistency if kps are available
    if kps is not None and len(kps) == 5:
        try:
            kps_arr = np.array(kps, dtype=np.float32)
            left_eye, right_eye = kps_arr[0], kps_arr[1]
            nose = kps_arr[2]
            left_mouth, right_mouth = kps_arr[3], kps_arr[4]

            eye_dist = float(np.linalg.norm(right_eye - left_eye))
            mouth_dist = float(np.linalg.norm(right_mouth - left_mouth))

            if eye_dist > 5.0:
                # Mouth keypoints collapsed or severely abnormal
                if mouth_dist < 0.12 * eye_dist:
                    return True, "Pontos da boca colapsados (possível oclusão)."

                mouth_center_y = (left_mouth[1] + right_mouth[1]) / 2.0
                nose_y = nose[1]
                eyes_y = (left_eye[1] + right_eye[1]) / 2.0

                # Mouth detected above nose or eyes is physically invalid
                if mouth_center_y <= nose_y - 2.0 or mouth_center_y <= eyes_y:
                    return True, "Posicionamento anatômico inválido dos pontos bucais."
        except Exception:
            pass

    # 2. Lower face texture & variance analysis (mouth/chin area vs upper cheeks)
    try:
        gray = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY) if len(face_image.shape) == 3 else face_image
        # Upper middle face (eyes/nose region): 20% to 55% height
        upper_region = gray[int(h * 0.20):int(h * 0.55), int(w * 0.15):int(w * 0.85)]
        # Lower face (mouth/chin region): 65% to 95% height
        lower_region = gray[int(h * 0.65):int(h * 0.95), int(w * 0.15):int(w * 0.85)]

        if upper_region.size > 0 and lower_region.size > 0:
            upper_std = float(np.std(upper_region))
            lower_std = float(np.std(lower_region))

            # If upper face has good contrast but lower face is completely flat/uniform (< 5 std)
            # it indicates a mask, solid object, or flat hand covering the mouth
            if upper_std > 20.0 and lower_std < 5.5:
                return True, "Região inferior do rosto uniforme ou coberta."
    except Exception:
        pass

    return False, "Sem oclusão detectada."

