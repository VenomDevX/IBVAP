"""
IBVAP — Fine-grained classifier (stage 2)

Given a crop of a detection, name the specific type: F16 rather than "aircraft".
Trained by scripts/train_classifier.py; weights at models/classifier/ibvap_fine.pt.

Runs ONLY on the military coarse classes. ml/taxonomy.py states the intent:

    Fine-grained aircraft type ID (F-16 vs F-18) is Phase 2 - a separate
    classifier that runs only on `aircraft` / `helicopter` / `drone_uav` /
    `military_ground_vehicle` crops.

There is no value in a fine-grained "type of person", and running a second
network on every person and car would cost frame rate for nothing.

Degrades to a no-op when the weights or timm/torch are missing, so the pipeline
runs single-stage exactly as before - the same contract FaceRecognizer honours.
"""

from __future__ import annotations

import json
import os

import numpy as np
from loguru import logger

from src.classification.preprocess import preprocess_crop

# Coarse classes worth a second look. Matches ml.taxonomy.MILITARY_TYPES; kept
# as a literal so this module does not drag the data-prep package into the
# pipeline's import graph.
MILITARY_TYPES = frozenset(
    {"military_ground_vehicle", "aircraft", "helicopter", "drone_uav"}
)

DEFAULT_WEIGHTS = "./models/classifier/ibvap_fine.pt"


class FineClassifier:
    """Names the specific type of a military crop.

    Enabled by default, unlike FaceRecognizer: the weights are produced locally
    by our own training script rather than pulled as a 300 MB third-party
    dependency. `active` is still the real gate - absent weights disable it
    silently instead of raising at every frame.
    """

    def __init__(
        self,
        enabled: bool = True,
        weights: str = DEFAULT_WEIGHTS,
        min_confidence: float = 0.55,
        device: str | None = None,
        imgsz: int = 224,
    ):
        self.enabled = enabled
        self.min_confidence = min_confidence
        self.imgsz = imgsz
        self.classes: list[str] = []
        self._model = None
        self._torch = None
        self._device = device
        self._use_half = False

        if not enabled:
            return

        if not os.path.exists(weights):
            logger.warning(
                f"FineClassifier: weights not found at {weights} - "
                f"stage 2 disabled, pipeline stays single-stage"
            )
            self.enabled = False
            return

        try:
            import torch

            self._torch = torch
            if not device or device == "auto":
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                self._device = device

            # weights_only=True: this checkpoint holds tensors, str and float
            # only. Never unpickle arbitrary objects in the serving path.
            ckpt = torch.load(weights, map_location=self._device, weights_only=True)
            self.classes = list(ckpt["classes"])
            self.imgsz = int(ckpt.get("imgsz", imgsz))
            arch = ckpt.get("arch", "")

            self._model = self._build(arch, len(self.classes))
            self._model.load_state_dict(ckpt["model"])
            self._model.to(self._device).eval()
            self._use_half = str(self._device).startswith("cuda")
            if self._use_half:
                self._model.half()

            logger.info(
                f"FineClassifier: {len(self.classes)} classes, arch={arch}, "
                f"device={self._device}, min_confidence={min_confidence}"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"FineClassifier init failed ({e}) - disabling")
            self.enabled = False
            self._model = None

    @staticmethod
    def _build(arch: str, n_classes: int):
        """Rebuild the architecture the checkpoint was trained with."""
        try:
            import timm

            return timm.create_model(arch, pretrained=False, num_classes=n_classes)
        except ImportError:
            import torch.nn as nn
            from torchvision import models

            name = arch.split(".")[0]
            if not hasattr(models, name):
                raise RuntimeError(
                    f"timm is not installed and torchvision has no '{name}'"
                ) from None
            m = getattr(models, name)(weights=None)
            if hasattr(m, "fc"):
                m.fc = nn.Linear(m.fc.in_features, n_classes)
            elif hasattr(m, "classifier"):
                head = m.classifier[-1] if isinstance(m.classifier, nn.Sequential) else m.classifier
                new = nn.Linear(head.in_features, n_classes)
                if isinstance(m.classifier, nn.Sequential):
                    m.classifier[-1] = new
                else:
                    m.classifier = new
            return m

    @property
    def active(self) -> bool:
        return bool(self.enabled and self._model is not None and self.classes)

    def classify(self, crop: np.ndarray) -> dict | None:
        """Return {"type", "confidence"} for a crop, or None.

        None means "no usable answer" and the caller should keep the coarse
        label. That covers an inactive classifier, an empty crop, an inference
        error, and - deliberately - a prediction below min_confidence. In a
        border-security display, "aircraft" is a better answer than a confident
        guess of the wrong airframe.
        """
        if not self.active or crop is None or getattr(crop, "size", 0) == 0:
            return None
        try:
            tensor = preprocess_crop(crop, self.imgsz)
            t = self._torch
            with t.inference_mode():
                x = t.from_numpy(tensor).unsqueeze(0).to(self._device)
                if self._use_half:
                    x = x.half()
                probs = t.softmax(self._model(x), dim=1)[0]
                conf, idx = t.max(probs, dim=0)
            confidence = float(conf)
            if confidence < self.min_confidence:
                return None
            return {"type": self.classes[int(idx)], "confidence": confidence}
        except Exception as e:  # noqa: BLE001
            logger.debug(f"fine classify error: {e}")
            return None

    @staticmethod
    def is_military(object_type: str) -> bool:
        return object_type in MILITARY_TYPES


def load_classes(weights: str = DEFAULT_WEIGHTS) -> list[str]:
    """Class list without loading the model - for API schema or diagnostics."""
    side = os.path.join(os.path.dirname(weights), "classes.json")
    if os.path.exists(side):
        try:
            with open(side, encoding="utf-8") as fh:
                return list(json.load(fh))
        except Exception:  # noqa: BLE001
            pass
    return []
