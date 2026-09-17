"""In-memory face embedding cache for fast cosine matching.

All registered people are kept as rows of a NumPy matrix, enabling vectorized
cosine-distance matching regardless of the database backend (pgvector or
SQLite fallback). The cache is refreshed from the database at startup and
kept in sync by the recognition service on register/update/delete.
"""

import logging
import threading
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class FaceCache:
    """Thread-safe in-memory store of normalized face embeddings."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._matrix = np.zeros((0, 512), dtype=np.float32)
        self._ids: List[int] = []
        self._names: Dict[int, Optional[str]] = {}
        self._index: Dict[int, int] = {}  # person_id -> row position

    # ── Loading ───────────────────────────────────────────────

    def load_from_rows(self, rows) -> int:
        """Rebuild the cache from Person ORM rows (id, name, embedding)."""
        ids: List[int] = []
        vectors: List[np.ndarray] = []
        names: Dict[int, Optional[str]] = {}

        for person in rows:
            try:
                vec = np.array(person.embedding, dtype=np.float32)
                if vec.size != 512:
                    continue
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                ids.append(person.id)
                vectors.append(vec)
                names[person.id] = person.name
            except Exception:
                logger.warning("Embedding inválido para person_id=%s, ignorado.", person.id)

        with self._lock:
            self._matrix = np.vstack(vectors) if vectors else np.zeros((0, 512), dtype=np.float32)
            self._ids = ids
            self._names = names
            self._index = {pid: i for i, pid in enumerate(ids)}

        logger.info("Cache facial carregado: %d pessoa(s) em memória.", len(ids))
        return len(ids)

    # ── Matching ──────────────────────────────────────────────

    def match(self, embedding: np.ndarray, threshold: float, min_margin: float = 0.04):
        """Find the closest person below `threshold` with ambiguity rejection.

        Args:
            embedding: 512-d query vector.
            threshold: Cosine distance cutoff (e.g. 0.45).
            min_margin: Minimum distance margin between top-1 and top-2 candidates
                        for borderline matches, preventing misattributing ambiguous
                        or occluded faces to another person.

        Returns:
            (person_id, distance) if matched unambiguously, otherwise (None, best_distance).
        """
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm == 0:
            return None, 1.0
        vec = vec / norm

        with self._lock:
            num_rows = self._matrix.shape[0]
            if num_rows == 0:
                return None, 1.0
            distances = 1.0 - np.clip(self._matrix @ vec, -1.0, 1.0)

            if num_rows == 1:
                best_dist = float(distances[0])
                if best_dist <= threshold:
                    return self._ids[0], best_dist
                return None, best_dist

            # Multiple candidates: check best and second best
            top_indices = np.argpartition(distances, 1)[:2]
            if distances[top_indices[0]] > distances[top_indices[1]]:
                top_indices = top_indices[::-1]

            best_row = int(top_indices[0])
            second_row = int(top_indices[1])
            best_dist = float(distances[best_row])
            second_dist = float(distances[second_row])

            if best_dist <= threshold:
                # Direct unmistakable match (distance <= 0.15, i.e. > 85% similarity)
                # or clear margin over the next closest candidate
                if best_dist <= 0.15 or (second_dist - best_dist) >= min_margin:
                    return self._ids[best_row], best_dist
                logger.debug(
                    "Reconhecimento ambíguo descartado: top1=%s (dist=%.3f), top2=%s (dist=%.3f), delta=%.3f < %.3f",
                    self._ids[best_row], best_dist, self._ids[second_row], second_dist,
                    second_dist - best_dist, min_margin
                )
                return None, best_dist
        return None, best_dist

    # ── Mutation ──────────────────────────────────────────────

    def _upsert_locked(self, person_id: int, vec: np.ndarray,
                       name: Optional[str], replace_name: bool) -> None:
        """Upsert a vector; caller must hold self._lock."""
        row = self._index.get(person_id)
        if row is not None:
            self._matrix[row] = vec
            if replace_name or name is not None:
                self._names[person_id] = name
            return
        self._matrix = np.vstack([self._matrix, vec.reshape(1, -1)])
        self._ids.append(person_id)
        self._index[person_id] = len(self._ids) - 1
        self._names[person_id] = name

    def add(self, person_id: int, embedding: np.ndarray, name: Optional[str] = None) -> None:
        """Insert a person; updating an existing id replaces its embedding."""
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        with self._lock:
            self._upsert_locked(person_id, vec, name, replace_name=False)

    def update(self, person_id: int, embedding: np.ndarray, name: Optional[str] = None,
               has_name: bool = False) -> None:
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        with self._lock:
            self._upsert_locked(person_id, vec, name, replace_name=has_name)

    def rename(self, person_id: int, name: Optional[str]) -> None:
        with self._lock:
            self._names[person_id] = name

    def remove(self, person_id: int) -> None:
        with self._lock:
            row = self._index.pop(person_id, None)
            if row is None:
                return
            self._matrix = np.delete(self._matrix, row, axis=0)
            self._ids.pop(row)
            self._names.pop(person_id, None)
            self._index = {pid: i for i, pid in enumerate(self._ids)}

    # ── Queries ───────────────────────────────────────────────

    def get_name(self, person_id: int) -> Optional[str]:
        with self._lock:
            return self._names.get(person_id)

    def display_name(self, person_id: int) -> str:
        name = self.get_name(person_id)
        return name if name else f"Pessoa #{person_id}"

    def count(self) -> int:
        with self._lock:
            return len(self._ids)


# Module-level singleton
face_cache = FaceCache()
