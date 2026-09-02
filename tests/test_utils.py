import os
import tempfile
import pytest
from app.utils import validate_file_extension, check_disk_space, cleanup_dir, save_upload

def test_validate_docx_extension():
    assert validate_file_extension("test.docx", [".docx"]) is True

def test_validate_fake_extension():
    assert validate_file_extension("malicious.exe", [".docx"]) is False

def test_validate_case_insensitive():
    assert validate_file_extension("test.DOCX", [".docx"]) is True

def test_cleanup_dir_removes_files():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.txt"), "w").close()
        cleanup_dir(d)
        assert not os.path.exists(d)

def test_cleanup_dir_nonexistent_no_error():
    cleanup_dir("/tmp/lingguang/nonexistent_dir_12345")

def test_save_upload_writes_file():
    content = b"fake docx content"
    path = save_upload(content, ".docx")
    assert os.path.exists(path)
    assert path.endswith(".docx")
    os.unlink(path)
