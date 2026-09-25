"""
IBVAP — Face Detector
Face detection using InsightFace/RetinaFace.
"""

import numpy as np
from loguru import logger


class FaceDetector:
    """Face detection using InsightFace."""

    def __init__(self, model_name: str = "buffalo_l", device: str = "auto"):
        self._model = None
        self._model_name = model_name
        self._requested_device = device
        self.device = "unavailable"
        self.providers: dict[str, list[str]] = {}
        self._load_model()

    def _load_model(self):
        try:
            wants_cuda = self._requested_device == "auto" or self._requested_device.startswith("cuda")
            if wants_cuda:
                # Loading PyTorch first makes its bundled CUDA 12/cuDNN 9 DLLs
                # visible to ONNX Runtime on Windows.
                import torch  # noqa: F401

            from insightface.app import FaceAnalysis

            try:
                import onnxruntime as ort

                available = ort.get_available_providers()
            except ImportError:
                available = []
            if wants_cuda and "CUDAExecutionProvider" in available:
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                ctx_id = 0
                self.device = "cuda:0"
            else:
                if self._requested_device.startswith("cuda"):
                    raise RuntimeError("CUDA face inference requested but ONNX CUDA provider is unavailable")
                providers = ["CPUExecutionProvider"]
                ctx_id = -1
                self.device = "cpu"
            # Only these two modules are required for identity matching. Avoid
            # loading landmark and age/gender networks into the 6 GB GPU.
            self._model = FaceAnalysis(
                name=self._model_name,
                providers=providers,
                allowed_modules=["detection", "recognition"],
            )
            self._model.prepare(ctx_id=ctx_id, det_size=(640, 640))
            self.providers = {
                name: model.session.get_providers()
                for name, model in self._model.models.items()
                if hasattr(model, "session")
            }
            if wants_cuda and (
                not self.providers or any("CUDAExecutionProvider" not in active for active in self.providers.values())
            ):
                self._model = None
                self.device = "unavailable"
                raise RuntimeError("InsightFace sessions silently fell back from CUDA")
            logger.success(f"Face detection model loaded on {self.device}")
        except ImportError:
            logger.warning("insightface not installed — face detection disabled")
        except Exception as e:
            logger.error(f"Face model load error: {e}")

    def detect_faces(self, frame: np.ndarray) -> list[dict]:
        """Detect faces in a frame. Returns list of face dicts."""
        if self._model is None:
            return []

        try:
            faces = self._model.get(frame)
            results = []
            for face in faces:
                bbox = face.bbox.astype(int).tolist()
                age = getattr(face, "age", None)
                gender = getattr(face, "gender", None)
                results.append(
                    {
                        "bbox": bbox,
                        "confidence": float(face.det_score),
                        "embedding": face.normed_embedding.tolist() if face.normed_embedding is not None else None,
                        "age": int(age) if age is not None else None,
                        "gender": "M" if gender == 1 else "F" if gender == 0 else None,
                    }
                )
            return results
        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return []
