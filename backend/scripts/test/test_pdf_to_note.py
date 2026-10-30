# IA/backend/scripts/test/test_pdf_to_note.py
"""PDF text extraction and authenticated note creation from reviewed content."""

import datetime
import io
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import create_app, config
from app.notes import manager as notes_manager
from app.notes import pdf_extract
from app.notes.pdf_extract import PdfExtractError, extract_text_from_pdf


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
        elif whence == 2:
            self._pos = len(self._data) + pos


def _escape_pdf_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_bytes(text: str = "Sample lesson text.", *, encrypt_password: str | None = None) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text:
        stream = DecodedStreamObject()
        stream.set_data(
            f"BT /F1 12 Tf 72 720 Td ({_escape_pdf_literal(text)}) Tj ET".encode("latin-1")
        )
        page[NameObject("/Contents")] = stream
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject("/Helvetica"),
                            }
                        )
                    }
                )
            }
        )
    if encrypt_password:
        writer.encrypt(encrypt_password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class PdfExtractUnitTests(unittest.TestCase):
    def test_extracts_text_from_valid_pdf(self):
        data = _pdf_bytes("Hello PDF note body.")
        result = extract_text_from_pdf(_FileStub(data, "lesson.pdf"))
        self.assertIn("Hello PDF note body.", result.text)
        self.assertGreaterEqual(result.page_count, 1)

    def test_rejects_non_pdf_extension(self):
        with self.assertRaises(PdfExtractError):
            extract_text_from_pdf(_FileStub(b"%PDF-1.4", "notes.txt"))

    def test_rejects_invalid_magic(self):
        with self.assertRaises(PdfExtractError):
            extract_text_from_pdf(_FileStub(b"not a pdf", "bad.pdf"))

    def test_rejects_corrupt_pdf(self):
        with self.assertRaises(PdfExtractError):
            extract_text_from_pdf(_FileStub(b"%PDF-1.4\nbroken", "broken.pdf"))

    def test_rejects_encrypted_pdf(self):
        data = _pdf_bytes("Secret", encrypt_password="secret")
        with self.assertRaises(PdfExtractError) as ctx:
            extract_text_from_pdf(_FileStub(data, "locked.pdf"))
        self.assertIn("password", str(ctx.exception).lower())

    def test_rejects_blank_pdf(self):
        data = _pdf_bytes("")
        with self.assertRaises(PdfExtractError) as ctx:
            extract_text_from_pdf(_FileStub(data, "blank.pdf"))
        self.assertIn("No text found", str(ctx.exception))

    def test_rejects_oversized_upload(self):
        data = _pdf_bytes("x")
        stub = _FileStub(data, "big.pdf")
        with patch.object(pdf_extract, "NOTES_PDF_MAX_BYTES", 10):
            with self.assertRaises(PdfExtractError) as ctx:
                extract_text_from_pdf(stub)
        self.assertIn("size limit", str(ctx.exception))

    def test_rejects_extracted_text_over_limit(self):
        data = _pdf_bytes("a" * 100)
        with patch.object(pdf_extract, "NOTES_MAX_CONTENT_CHARS", 50):
            with self.assertRaises(PdfExtractError) as ctx:
                extract_text_from_pdf(_FileStub(data, "long.pdf"))
        self.assertIn("character limit", str(ctx.exception))


class PdfExtractRouteTests(unittest.TestCase):
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

    def user_id(self):
        return str(uuid.uuid4())

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    def post_extract(self, data, headers=None, filename="lesson.pdf"):
        return self.client.post(
            "/notes/from-pdf/extract",
            data={"file": (io.BytesIO(data), filename)},
            headers=headers or {},
            content_type="multipart/form-data",
        )

    def test_extract_requires_auth(self):
        response = self.post_extract(_pdf_bytes("Auth test"))
        self.assertEqual(response.status_code, 401)

    def test_extract_success(self):
        user_id = self.user_id()
        response = self.post_extract(_pdf_bytes("Route extract text."), headers=self.headers(user_id))
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("Route extract text.", body["text"])
        self.assertGreaterEqual(body["page_count"], 1)
        self.assertGreater(body["char_count"], 0)

    def test_extract_invalid_pdf_returns_400(self):
        response = self.post_extract(b"%PDF-broken", headers=self.headers(self.user_id()), filename="bad.pdf")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_create_note_rejects_oversized_content(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        limit = config.NOTES_MAX_CONTENT_CHARS
        response = self.client.post(
            "/notes/",
            json={
                "title": "Too long",
                "category": "study",
                "content": "x" * (limit + 1),
                "tags": [],
            },
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("character limit", response.get_json().get("error", ""))

    def test_create_note_after_extract(self):
        user_id = self.user_id()
        headers = self.headers(user_id)
        extracted = self.post_extract(_pdf_bytes("Saved lesson content."), headers=headers)
        text = extracted.get_json()["text"]
        created = self.client.post(
            "/notes/",
            json={
                "title": "Biology PDF",
                "category": "science",
                "content": text,
                "tags": [],
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 201)
        note = created.get_json()
        self.assertIn("Saved lesson content.", note["content"])
        stored = notes_manager.get_note(note["id"], user_id)
        self.assertIsNotNone(stored)


class ImageExtractRouteTests(unittest.TestCase):
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

    def user_id(self):
        return str(uuid.uuid4())

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    @patch("app.notes.routes.extract_text_from_images", return_value="OCR sample text")
    def test_extract_images_returns_text_without_creating_note(self, _mock_ocr):
        user_id = self.user_id()
        response = self.client.post(
            "/notes/from-images/extract",
            data={"files": (io.BytesIO(b"fake-png"), "scan.png")},
            headers=self.headers(user_id),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["text"], "OCR sample text")
        self.assertEqual(body["char_count"], len("OCR sample text"))
        self.assertEqual(notes_manager.load_notes(user_id), [])

    def test_extract_images_requires_auth(self):
        response = self.client.post(
            "/notes/from-images/extract",
            data={"files": (io.BytesIO(b"x"), "a.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
