# IA/backend/scripts/test/test_pptx_extract.py
"""PowerPoint text extraction. The original file is not stored."""

import io
import os
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt
from pptx import Presentation
from pptx.util import Inches

from app import config, create_app
from app.notes import manager as notes_manager
from app.notes import pptx_extract
from app.notes.pptx_extract import PptxExtractError, extract_text_from_pptx
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


class _FileStub:
    def __init__(self, data: bytes, filename: str):
        self._data = data
        self.filename = filename
        self._pos = 0

    def read(self, n=-1):
        if n < 0:
            chunk = self._data[self._pos :]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def seek(self, pos, whence=0):
        if whence == 0:
            self._pos = pos
        elif whence == 1:
            self._pos += pos
        else:
            self._pos = len(self._data) + pos


def _slide(presentation, text):
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    if text:
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(8), Inches(1))
        box.text_frame.text = text
    return slide


def _pptx_bytes(*slide_texts: str) -> bytes:
    presentation = Presentation()
    for text in slide_texts:
        _slide(presentation, text)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


class PptxExtractUnitTests(unittest.TestCase):
    def test_extracts_slides_in_order(self):
        data = _pptx_bytes("First slide lesson", "Second slide lesson")
        result = extract_text_from_pptx(_FileStub(data, "lesson.pptx"))
        self.assertLess(result.text.index("Slide 1"), result.text.index("Slide 2"))
        self.assertLess(result.text.index("First slide lesson"), result.text.index("Second slide lesson"))
        self.assertEqual(result.slide_count, 2)
        self.assertIn("--- Slide 1 ---", result.text)
        self.assertIn("--- Slide 2 ---", result.text)

    def test_rejects_non_pptx_extension(self):
        with self.assertRaises(PptxExtractError):
            extract_text_from_pptx(_FileStub(b"PK\x03\x04", "notes.txt"))

    def test_rejects_empty_upload(self):
        with self.assertRaises(PptxExtractError) as ctx:
            extract_text_from_pptx(_FileStub(b"", "empty.pptx"))
        self.assertIn("empty", str(ctx.exception).lower())

    def test_rejects_invalid_magic(self):
        with self.assertRaises(PptxExtractError):
            extract_text_from_pptx(_FileStub(b"not a pptx", "bad.pptx"))

    def test_rejects_corrupt_pptx(self):
        with self.assertRaises(PptxExtractError):
            extract_text_from_pptx(_FileStub(b"PK\x03\x04broken", "broken.pptx"))

    def test_rejects_textless_pptx(self):
        data = _pptx_bytes("")
        with self.assertRaises(PptxExtractError) as ctx:
            extract_text_from_pptx(_FileStub(data, "blank.pptx"))
        self.assertIn("No text found", str(ctx.exception))

    def test_rejects_oversized_upload(self):
        data = _pptx_bytes("Short")
        with patch.object(pptx_extract, "NOTES_PPTX_MAX_BYTES", 10):
            with self.assertRaises(PptxExtractError) as ctx:
                extract_text_from_pptx(_FileStub(data, "big.pptx"))
        self.assertIn("size limit", str(ctx.exception))

    def test_rejects_extracted_text_over_limit(self):
        data = _pptx_bytes("a" * 80)
        with patch.object(pptx_extract, "NOTES_MAX_CONTENT_CHARS", 20):
            with self.assertRaises(PptxExtractError) as ctx:
                extract_text_from_pptx(_FileStub(data, "long.pptx"))
        self.assertIn("character limit", str(ctx.exception))


class PptxExtractRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def headers(self, user_id):
        token = jwt.encode(
            {"sub": user_id, "exp": 9999999999},
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    def post_extract(self, data, headers=None, filename="lesson.pptx"):
        return self.client.post(
            "/notes/from-pptx/extract",
            data={"file": (io.BytesIO(data), filename)},
            headers=headers or {},
            content_type="multipart/form-data",
        )

    def test_extract_requires_auth(self):
        response = self.post_extract(_pptx_bytes("Auth slide"))
        self.assertEqual(response.status_code, 401)

    def test_extract_returns_text_without_creating_note(self):
        user_id = ensure_note_owner(str(uuid.uuid4()))
        response = self.post_extract(_pptx_bytes("Route slide text"), headers=self.headers(user_id))
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("Route slide text", body["text"])
        self.assertEqual(body["slide_count"], 1)
        self.assertGreater(body["char_count"], 0)
        self.assertEqual(notes_manager.load_notes(user_id), [])

    def test_extract_invalid_pptx_returns_400(self):
        user_id = ensure_note_owner(str(uuid.uuid4()))
        response = self.post_extract(b"PK\x03\x04broken", headers=self.headers(user_id), filename="bad.pptx")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
