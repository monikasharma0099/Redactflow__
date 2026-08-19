"""Security helper unit tests: magic bytes, filename sanitization."""

from app.core.security import sanitize_filename, sniff_file_type


def test_sniff_png():
    assert sniff_file_type(b"\x89PNG\r\n\x1a\nrest") == "png"


def test_sniff_jpeg():
    assert sniff_file_type(b"\xff\xd8\xff\xe0rest") == "jpeg"


def test_sniff_pdf():
    assert sniff_file_type(b"%PDF-1.7 body") == "pdf"


def test_sniff_rejects_exe_and_text():
    assert sniff_file_type(b"MZ\x90\x00") is None
    assert sniff_file_type(b"hello world") is None
    assert sniff_file_type(b"") is None


def test_sanitize_filename_strips_path_and_bad_chars():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("my file(1).png") == "my_file_1_.png"
    assert sanitize_filename("a\\b\\c.jpg") == "c.jpg"
    assert sanitize_filename("") == "upload"
    assert len(sanitize_filename("x" * 500 + ".png")) <= 100
    assert sanitize_filename("...") == "upload"
