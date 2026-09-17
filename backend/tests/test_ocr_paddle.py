"""PaddleOCR 3.x adapter: two-row plates are read top row first."""

import numpy as np

from src.anpr import ocr


class FakePaddle3:
    def __init__(self, lines):
        self.lines = lines

    def predict(self, img):
        texts, scores, polys = zip(*self.lines)
        return [{"rec_texts": list(texts), "rec_scores": list(scores), "rec_polys": [np.array(p) for p in polys]}]


def _box(x, y, w=80, h=20):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_two_row_plate_is_joined_top_to_bottom():
    reader = FakePaddle3([("3456", 0.9, _box(20, 60)), ("MH12AB", 0.8, _box(10, 10))])
    text, conf = ocr._read_paddle(reader, np.zeros((100, 120, 3), np.uint8))
    assert text == "MH12AB3456"
    assert 0.8 < conf < 0.9


def test_low_confidence_fragments_are_dropped():
    reader = FakePaddle3([("MH12AB3456", 0.95, _box(0, 0)), ("~", 0.1, _box(100, 0))])
    assert ocr._read_paddle(reader, np.zeros((40, 200), np.uint8))[0] == "MH12AB3456"


def test_empty_result():
    class Empty:
        def predict(self, img):
            return []

    assert ocr._read_paddle(Empty(), np.zeros((10, 10, 3), np.uint8)) == ("", 0.0)


def test_subprocess_mode_round_trips_and_recovers(monkeypatch):
    """OCR runs in a child process so PaddlePaddle (which holds the GIL) can't
    freeze the backend. The child inherits the environment."""
    monkeypatch.setenv("IBVAP_OCR_ENGINE", "no-such-engine")  # child resolves to 'unavailable' fast
    ocr.use_subprocess(True)
    try:
        assert ocr.read_plate(np.zeros((30, 90, 3), np.uint8)) == ("", 0.0)
        assert ocr.engine_name() == "unavailable"
        # A dead worker is replaced on the next call.
        ocr._pool._processes and [p.kill() for p in ocr._pool._processes.values()]
        assert ocr.read_plate(np.zeros((30, 90, 3), np.uint8)) == ("", 0.0)
        assert ocr.read_plate(np.zeros((30, 90, 3), np.uint8)) == ("", 0.0)
    finally:
        ocr.use_subprocess(False)
    assert ocr._pool is None
