"""ANPR OCR + face-recognition wiring."""

import numpy as np

# --------------------------------------------------------------------------- #
# ANPR
# --------------------------------------------------------------------------- #


def test_ocr_mock_when_no_engine(monkeypatch):
    import src.anpr.ocr as ocr

    monkeypatch.setattr(ocr, "_reader", None)
    monkeypatch.setattr(ocr, "_engine_name", "uninitialised")
    monkeypatch.setattr(ocr, "_ENGINES", [])  # nothing loadable
    txt, conf = ocr.read_plate(np.full((40, 120, 3), 255, np.uint8))
    assert (txt, conf) == ("MOCK-PLT", 0.0)


def test_ocr_normalises_and_length_gates(monkeypatch):
    import src.anpr.ocr as ocr

    def fake_reader():
        return object()

    def fake_read(_reader, _img):
        return "mh 12 ab-3456!", 0.91

    monkeypatch.setattr(ocr, "_reader", None)
    monkeypatch.setattr(ocr, "_engine_name", "uninitialised")
    monkeypatch.setattr(ocr, "_ENGINES", [("fake", fake_reader, fake_read)])
    txt, conf = ocr.read_plate(np.full((40, 200, 3), 255, np.uint8))
    assert txt == "MH12AB3456"
    assert conf == 0.91

    # too-short result is rejected
    monkeypatch.setattr(ocr, "_reader", None)
    monkeypatch.setattr(ocr, "_engine_name", "uninitialised")
    monkeypatch.setattr(ocr, "_ENGINES", [("fake", fake_reader, lambda r, i: ("AB", 0.9))])
    assert ocr.read_plate(np.full((40, 200, 3), 255, np.uint8)) == ("", 0.0)


def test_extract_plate_shape(monkeypatch):
    import src.features.anpr as anpr

    monkeypatch.setattr(anpr, "read_plate", lambda img: ("KA05MN9999", 0.8))
    monkeypatch.setattr(anpr, "_plate_detector", lambda: None)
    out = anpr.extract_plate(np.full((120, 240, 3), 255, np.uint8))
    assert out == {"text": "KA05MN9999", "confidence": 0.8, "bbox": None}
    assert anpr.extract_license_plate(np.full((120, 240, 3), 255, np.uint8)) == "KA05MN9999"


def test_extract_plate_empty_crop():
    import src.features.anpr as anpr

    assert anpr.extract_plate(None)["text"] == "Unknown"
    assert anpr.extract_plate(np.array([]))["text"] == "Unknown"


# --------------------------------------------------------------------------- #
# Face recognition
# --------------------------------------------------------------------------- #


def test_face_recognizer_disabled_is_noop():
    from src.face.face_recognizer import FaceRecognizer

    fr = FaceRecognizer(enabled=False)
    assert fr.active is False
    assert fr.identify(np.zeros((128, 64, 3), np.uint8)) is None


def test_face_recognizer_identifies_best_face(monkeypatch):
    from src.face.face_recognizer import FaceRecognizer

    fr = FaceRecognizer(enabled=False)
    fr.enabled = True

    class _Det:
        def detect_faces(self, _crop):
            return [
                {"confidence": 0.5, "embedding": [1, 0, 0]},  # below floor
                {"confidence": 0.9, "embedding": [0, 1, 0]},
            ]

    class _Match:
        def match(self, face):
            assert face["confidence"] == 0.9
            return {"identity": "guard_42", "similarity": 0.71, "status": "known"}

    fr._detector = _Det()
    fr._matcher = _Match()
    assert fr.active is True

    res = fr.identify(np.zeros((128, 64, 3), np.uint8))
    assert res == {"identity": "guard_42", "similarity": 0.71, "status": "known"}


def test_face_recognizer_no_usable_face(monkeypatch):
    from src.face.face_recognizer import FaceRecognizer

    fr = FaceRecognizer(enabled=False)
    fr.enabled = True
    fr._detector = type("D", (), {"detect_faces": lambda self, c: []})()
    fr._matcher = object()
    assert fr.identify(np.zeros((128, 64, 3), np.uint8)) is None


# --------------------------------------------------------------------------- #
# repository persistence
# --------------------------------------------------------------------------- #


def test_identity_and_anpr_results_persist(repo):
    idn = repo.create_identity_result(track_id=3, camera_id="cam1", identity_label="guard_1", similarity_score=0.8)
    plt = repo.create_anpr_result(track_id=4, camera_id="cam1", plate_text="MH12AB3456", ocr_confidence=0.77)
    assert idn.identity_id.startswith("IDN_")
    assert plt.plate_id.startswith("PLT_")
    assert repo.get_identity_results("cam1")[0].identity_label == "guard_1"
    assert repo.get_anpr_results("cam1")[0].plate_text == "MH12AB3456"
