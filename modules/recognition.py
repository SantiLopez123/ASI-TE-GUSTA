# -*- coding: utf-8 -*-
"""Motor facial local: OpenCV YuNet (detección) + SFace (embedding de 128 dim).

* 100 % CPU y 100 % local: ninguna imagen sale del computador.
* No se guardan fotografías: sólo el embedding numérico.
* Si los modelos o la cámara no están disponibles, la app sigue funcionando
  en modo demostración (ver `FaceEngine.available`).
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # silencia avisos de OpenCV 5

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
import numpy as np

import config

_LOCK = threading.Lock()          # YuNet/SFace no son seguros entre hilos
MAX_SIDE = 640                    # se reescala antes de analizar (estabilidad > velocidad)


@dataclass
class FaceInfo:
    box: tuple          # (x, y, w, h) en la imagen reescalada
    score: float
    row: np.ndarray     # fila de 15 valores de YuNet (caja + 5 puntos + score)


@dataclass
class EmbedResult:
    ok: bool
    message: str
    embedding: Optional[np.ndarray] = None
    face: Optional[FaceInfo] = None
    n_faces: int = 0


@dataclass
class IdentifyResult:
    status: str                      # MATCH | UNKNOWN | NO_FACE | ERROR
    message: str
    customer_id: Optional[int] = None
    score: Optional[float] = None
    face: Optional[FaceInfo] = None


class FaceEngine:
    def __init__(self) -> None:
        self.available = False
        self.reason = ""
        self._det = None
        self._rec = None
        self._load()

    def _load(self) -> None:
        try:
            for p in (config.YUNET_MODEL, config.SFACE_MODEL):
                if not p.exists():
                    raise FileNotFoundError(f"Falta el modelo {p.name} en la carpeta models/")
            if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
                raise RuntimeError("Esta versión de OpenCV no incluye FaceDetectorYN/FaceRecognizerSF")
            self._det = cv2.FaceDetectorYN.create(
                str(config.YUNET_MODEL), "", (320, 320), config.FACE_DETECT_SCORE, 0.3, 5000)
            self._rec = cv2.FaceRecognizerSF.create(str(config.SFACE_MODEL), "")
            self.available = True
        except Exception as exc:                       # noqa: BLE001 - degradamos a modo demo
            self.available = False
            self.reason = str(exc)

    # -------------------------------------------------------------- utilidades
    @staticmethod
    def decode(data: bytes) -> Optional[np.ndarray]:
        """Bytes de imagen (JPEG/PNG) -> BGR, o None si no es una imagen válida."""
        if not data:
            return None
        arr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    @staticmethod
    def shrink(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        scale = MAX_SIDE / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    # --------------------------------------------------------------- detección
    def detect(self, img: np.ndarray) -> tuple[np.ndarray, list[FaceInfo]]:
        """Devuelve (imagen reescalada, rostros ordenados de mayor a menor)."""
        if not self.available:
            return img, []
        img = self.shrink(img)
        h, w = img.shape[:2]
        with _LOCK:
            self._det.setInputSize((w, h))
            _, faces = self._det.detect(img)
        infos: list[FaceInfo] = []
        if faces is not None:
            for row in faces:
                x, y, fw, fh = (float(v) for v in row[:4])
                infos.append(FaceInfo((int(x), int(y), int(fw), int(fh)), float(row[-1]), row.copy()))
        infos.sort(key=lambda f: f.box[2] * f.box[3], reverse=True)
        return img, infos

    def _embed_face(self, img: np.ndarray, face: FaceInfo) -> np.ndarray:
        with _LOCK:
            aligned = self._rec.alignCrop(img, face.row)
            feat = self._rec.feature(aligned)
        return np.asarray(feat, dtype=np.float32).ravel().copy()

    # ----------------------------------------------------------------- registro
    def embedding_for_enrollment(self, img: Optional[np.ndarray]) -> EmbedResult:
        """Valida la calidad de la foto y devuelve el embedding del rostro."""
        if not self.available:
            return EmbedResult(False, "El reconocimiento facial no está disponible en este equipo.")
        if img is None:
            return EmbedResult(False, "No se pudo leer la imagen.")
        img, faces = self.detect(img)
        if not faces:
            return EmbedResult(False, "No detectamos ningún rostro. Mira a la cámara con buena luz.")
        if len(faces) > 1:
            return EmbedResult(False, "Hay más de un rostro en la imagen. Debe aparecer solo una persona.",
                               n_faces=len(faces))
        face = faces[0]
        if face.score < config.FACE_ENROLL_MIN_SCORE:
            return EmbedResult(False, "El rostro no se ve con suficiente claridad. Mejora la luz y mira de frente.",
                               face=face, n_faces=1)
        if min(face.box[2], face.box[3]) < config.FACE_MIN_SIZE_PX:
            return EmbedResult(False, "Acércate un poco más a la cámara.", face=face, n_faces=1)
        return EmbedResult(True, "Rostro detectado correctamente.", self._embed_face(img, face), face, 1)

    # ------------------------------------------------------------ identificación
    @staticmethod
    def best_match(embedding: np.ndarray, gallery: list[tuple[int, np.ndarray]]) -> tuple[Optional[int], float]:
        """(customer_id, similitud coseno) del mejor candidato; (None, 0) si no hay galería."""
        if not gallery:
            return None, 0.0
        q = embedding / (np.linalg.norm(embedding) or 1.0)
        best_id, best = None, -1.0
        for cid, ref in gallery:
            s = float(q @ ref)
            if s > best:
                best_id, best = cid, s
        return best_id, best

    def identify(self, img: Optional[np.ndarray], gallery: list[tuple[int, np.ndarray]]) -> IdentifyResult:
        if not self.available:
            return IdentifyResult("ERROR", "El reconocimiento facial no está disponible en este equipo.")
        if img is None:
            return IdentifyResult("ERROR", "No se pudo leer la imagen.")
        img, faces = self.detect(img)
        if not faces:
            return IdentifyResult("NO_FACE", "No detectamos ningún rostro.")
        face = faces[0]                                   # el más grande = el más cercano
        if min(face.box[2], face.box[3]) < config.FACE_MIN_SIZE_PX:
            return IdentifyResult("NO_FACE", "Acércate un poco más a la cámara.", face=face)
        emb = self._embed_face(img, face)
        cid, score = self.best_match(emb, gallery)
        if cid is not None and score >= config.FACE_MATCH_THRESHOLD:
            return IdentifyResult("MATCH", "Cliente identificado.", cid, score, face)
        return IdentifyResult("UNKNOWN", "Persona no registrada.", None, score if cid is not None else None, face)


# ---------------------------------------------------------------------------
# Singleton perezoso
# ---------------------------------------------------------------------------
_ENGINE: Optional[FaceEngine] = None


def get_engine() -> FaceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = FaceEngine()
    return _ENGINE


# ---------------------------------------------------------------------------
# Cámara del sistema: UNA sola vía (OpenCV, local) para registrar y para reconocer
# ---------------------------------------------------------------------------
BLACK_FRAME_MEAN = 3.0          # promedio de brillo por debajo del cual el cuadro se considera "negro"
CAMERA_SCAN_INDICES = (0, 1, 2, 3)


class ImageCamera:
    """Cámara de PRUEBA: entrega siempre la misma imagen (o un video en bucle).

    Se activa con la variable de entorno ATG_FAKE_CAMERA=<ruta a imagen o video>. Sirve para
    probar el flujo completo sin una persona frente a la webcam. Desactivada por defecto.
    """

    def __init__(self, source):
        """`source`: ruta a una imagen/video, o un arreglo BGR de numpy."""
        self._video = None
        self._frame = None
        if isinstance(source, np.ndarray):
            self._frame = source
        elif str(source).lower().endswith((".mp4", ".avi", ".mov", ".mjpeg", ".mkv")):
            self._video = cv2.VideoCapture(str(source))
        else:
            self._frame = cv2.imread(str(source))
        self.released = False

    def isOpened(self) -> bool:
        if self._video is not None:
            return self._video.isOpened()
        return self._frame is not None

    def read(self):
        if self._video is not None:
            ok, fr = self._video.read()
            if not ok:
                self._video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, fr = self._video.read()
            return ok, fr
        time.sleep(0.03)                                   # ritmo parecido al de una webcam
        return (True, self._frame.copy()) if self._frame is not None else (False, None)

    def set(self, *_args) -> bool:
        return True

    def release(self) -> None:
        self.released = True
        if self._video is not None:
            self._video.release()


def _try_open(index: int):
    """Intenta abrir UNA cámara; devuelve el objeto sólo si entrega imagen real (no negra)."""
    cap = None
    try:
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(index)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        brightest = -1.0
        for _ in range(12):                                # descarta cuadros iniciales (exposición)
            ok, frame = cap.read()
            if ok and frame is not None and frame.size:
                brightest = max(brightest, float(frame.mean()))
            time.sleep(0.03)
        if brightest < BLACK_FRAME_MEAN:                   # sin imagen o cámara virtual/tapada
            cap.release()
            return None
        return cap
    except Exception:                                      # noqa: BLE001
        try:
            if cap is not None:
                cap.release()
        except Exception:                                  # noqa: BLE001
            pass
        return None


def open_camera(index: Optional[int] = None):
    """Abre la cámara o devuelve None si no hay una disponible (ocupada, sin permiso o inexistente).

    index=None  -> automático: prueba el índice configurado y luego 0..3 hasta hallar una cámara con imagen.
    index=<n>   -> sólo esa cámara.
    """
    fake = os.environ.get("ATG_FAKE_CAMERA")
    if fake:
        cam = ImageCamera(fake)
        return cam if cam.isOpened() else None
    if index is not None and index >= 0:
        return _try_open(int(index))
    candidates = [config.CAMERA_INDEX] + [i for i in CAMERA_SCAN_INDICES if i != config.CAMERA_INDEX]
    for i in candidates:
        cap = _try_open(i)
        if cap is not None:
            return cap
    return None


@dataclass
class CaptureResult:
    status: str                                  # OK | PARTIAL | NO_FACE
    message: str
    samples: list = field(default_factory=list)  # embeddings (128,) float32


def capture_samples(engine: "FaceEngine", cap, *, wanted: int = 3, seconds: float = 25.0, spacing: float = 0.8,
                    on_frame: Optional[Callable] = None, now: Callable[[], float] = time.time) -> CaptureResult:
    """Captura hasta `wanted` muestras faciales de calidad desde una cámara abierta.

    * Sólo se acepta un rostro por cuadro, nítido y de tamaño suficiente (mismos controles que el registro).
    * Las muestras deben parecerse a la primera (misma persona); si no, se descartan.
    * `on_frame(imagen_bgr_para_mostrar, mensaje)` permite pintar la vista previa. Nada se guarda en disco.
    """
    samples: list[np.ndarray] = []
    last_t = -1e9
    last_msg = "Mira de frente a la cámara."
    t0 = now()
    while now() - t0 < seconds and len(samples) < wanted:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.03)
            continue
        small = engine.shrink(frame)
        res = engine.embedding_for_enrollment(frame)
        msg = res.message if not res.ok else last_msg
        if res.ok and now() - last_t >= spacing:
            same = True
            if samples:
                _, sim = engine.best_match(res.embedding, [(0, samples[0] / (np.linalg.norm(samples[0]) or 1.0))])
                same = sim >= config.FACE_MATCH_THRESHOLD
            if same:
                samples.append(res.embedding)
                last_t = now()
                if len(samples) < wanted:
                    msg = f"Muestra {len(samples)} de {wanted}. Gira un poco la cabeza y mantén la mirada."
                else:
                    msg = f"Muestra {wanted} de {wanted}. ¡Listo!"
            else:
                msg = "Debe aparecer siempre la misma persona."
            last_msg = msg
        elif not res.ok:
            last_msg = "Mira de frente a la cámara."
        if on_frame is not None:
            on_frame(draw_face(small, res.face, f"{len(samples)}/{wanted}" if res.face else "", mirror=True), msg)
    if len(samples) >= wanted:
        return CaptureResult("OK", f"Rostro capturado ({len(samples)} muestras).", samples)
    if samples:
        return CaptureResult("PARTIAL", f"Rostro capturado con {len(samples)} muestra(s). Puedes repetir la captura para mejorar la precisión.", samples)
    return CaptureResult("NO_FACE", last_msg if last_msg != "Mira de frente a la cámara." else
                         "No detectamos un rostro claro. Mira de frente a la cámara con buena luz y vuelve a intentarlo.")


def draw_face(img: np.ndarray, face: Optional[FaceInfo], label: str, color=(143, 45, 107), mirror: bool = False) -> np.ndarray:
    """Dibuja la caja del rostro con una etiqueta (BGR). mirror=True: vista tipo espejo (más natural en pantalla)."""
    out = img.copy()
    if mirror:
        out = cv2.flip(out, 1)
    if face is not None:
        x, y, w, h = face.box
        if mirror:
            x = out.shape[1] - x - w
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        if label:
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(out, (x, max(0, y - th - 12)), (x + tw + 10, y), color, -1)
            cv2.putText(out, label, (x + 5, max(th, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return out

