# IA/backend/scripts/test/test_image_ocr.py
"""Tesseract detection and OCR-unavailable API responses."""

import io
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt

from app import create_app, config
from app.notes import manager as notes_manager
from app.notes.tesseract_runtime import (
    OCR_UNAVAILABLE_MESSAGE,
    ensure_tesseract_ready,
    is_tesseract_available,
    tesseract_executable,
    OcrUnavailableError,
)


class TesseractRuntimeTests(unittest.TestCase):
    def test_tesseract_executable_honors_env(self):
        with patch.dict(os.environ, {"TESSERACT_CMD": "/custom/tesseract"}, clear=False):
            self.assertEqual(tesseract_executable(), "/custom/tesseract")

    @patch("app.notes.tesseract_runtime.shutil.which", return_value="/usr/bin/tesseract")
    def test_tesseract_executable_falls_back_to_path(self, _which):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TESSERACT_CMD", None)
            self.assertEqual(tesseract_executable(), "/usr/bin/tesseract")

    @patch("app.notes.tesseract_runtime.tesseract_executable", return_value=None)
    def test_is_tesseract_available_false_without_binary(self, _exe):
        self.assertFalse(is_tesseract_available())

    @patch("app.notes.tesseract_runtime.is_tesseract_available", return_value=False)
    def test_ensure_tesseract_ready_raises_clear_error(self, _available):
        with self.assertRaises(OcrUnavailableError) as ctx:
            ensure_tesseract_ready()
        self.assertIn("Image OCR is not available", str(ctx.exception))


class ImageExtractOcrUnavailableRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.notes_data_patch = patch.object(notes_manager, "DATA_DIR", cls.temp_dir.name)
        cls.notes_data_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.notes_data_patch.stop()
        cls.temp_dir.cleanup()

    def headers(self):
        user_id = str(uuid.uuid4())
        token = jwt.encode(
            {"sub": user_id, "exp": 9999999999},
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    @patch("app.notes.image_to_note.ensure_tesseract_ready")
    def test_extract_returns_503_when_ocr_unavailable(self, mock_ready):
        mock_ready.side_effect = OcrUnavailableError(OCR_UNAVAILABLE_MESSAGE)
        response = self.client.post(
            "/notes/from-images/extract",
            data={"files": (io.BytesIO(b"fake"), "scan.png")},
            headers=self.headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("Image OCR is not available", response.get_json().get("error", ""))


if __name__ == "__main__":
    unittest.main()
