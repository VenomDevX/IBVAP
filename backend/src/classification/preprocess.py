"""
IBVAP — crop preprocessing for the stage-2 classifier.

The serving transform must match the validation transform in
scripts/train_classifier.py. Rather than reimplement it and hope the two stay
aligned, this builds the SAME torchvision transform, so divergence is
impossible by construction.

That choice was made after measuring: a hand-rolled cv2 equivalent matched the
channel order exactly but drifted 0.18 mean absolute error on real crops
because cv2 and PIL resample differently. Nothing raises when that happens - it
just quietly costs accuracy, which is the worst kind of bug to carry into a
demo. The transform runs at most once per 2 s per military track, so PIL's
extra cost is irrelevant next to getting it right.

Pipeline crops arrive from cv2 and are therefore BGR; training read them via
PIL, which is RGB. The channel swap is not cosmetic - without it every
prediction is made on colour-inverted input.
"""

from __future__ import annotations

import cv2
import numpy as np

# Must equal MEAN, STD in scripts/train_classifier.py
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
RESIZE_RATIO = 1.14  # matches Resize(int(size * 1.14)) in training

_TRANSFORMS: dict[int, object] = {}


def _build_transform(size: int):
    """The validation transform from scripts/train_classifier.py, verbatim."""
    from torchvision import transforms

    return transforms.Compose(
        [
            transforms.Resize(int(size * RESIZE_RATIO)),
            transforms.CenterCrop(size),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )


def get_transform(size: int = 224):
    """Cached transform — building it per crop would dominate the cost."""
    if size not in _TRANSFORMS:
        _TRANSFORMS[size] = _build_transform(size)
    return _TRANSFORMS[size]


def preprocess_crop(crop: np.ndarray, size: int = 224, bgr: bool = True) -> np.ndarray:
    """BGR (or RGB) HxWx3 uint8 crop -> normalised CHW float32, ready for the model."""
    if crop is None or crop.size == 0:
        raise ValueError("empty crop")

    from PIL import Image

    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) if bgr else crop
    tensor = get_transform(size)(Image.fromarray(rgb))
    return tensor.numpy()
