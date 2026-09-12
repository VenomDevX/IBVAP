"""IBVAP — stage 2: fine-grained classification of detector crops.

Stage 1 (YOLO, src/detection) answers "there is an aircraft here". Stage 2
answers "it is an F-16". It runs only on the military coarse classes, because
that is the distinction this system exists to make — see ml/taxonomy.py.
"""

from src.classification.fine_classifier import MILITARY_TYPES, FineClassifier

__all__ = ["FineClassifier", "MILITARY_TYPES"]
