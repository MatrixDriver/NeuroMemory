"""Tests for file upload and management."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from neuromem.services.files import FileService


@pytest.fixture
def mock_storage():
    """Mock object storage."""
    storage = MagicMock()
    storage.upload = AsyncMock(
        side_effect=lambda prefix, fn, data, ct="": f"{prefix}/{uuid.uuid4()}/{fn}"
    )
    storage.download = AsyncMock(return_value=b"file content")
    storage.get_presigned_url = AsyncMock(return_value="http://minio:9000/presigned-url")
    storage.delete = AsyncMock()
    storage.init = AsyncMock()
    return storage


@pytest.mark.asyncio
async def test_upload_text_file(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    doc = await svc.upload(
        user_id="u1",
        filename="hello.txt",
        file_data=b"Hello world content",
        category="notes",
    )
    assert doc.filename == "hello.txt"
    assert doc.file_type == "txt"
    assert doc.category == "notes"
    assert doc.file_size == len(b"Hello world content")
    assert doc.extracted_text is not None
    mock_storage.upload.assert_called_once()


@pytest.mark.asyncio
async def test_upload_image_file(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    doc = await svc.upload(
        user_id="u1",
        filename="photo.png",
        file_data=b"\x89PNG\r\n\x1a\n",
    )
    assert doc.filename == "photo.png"
    assert doc.file_type == "png"
    assert doc.extracted_text is None
    assert doc.embedding_id is None


@pytest.mark.asyncio
async def test_upload_invalid_type(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    with pytest.raises(ValueError, match="Unsupported file type"):
        await svc.upload(
            user_id="u1",
            filename="virus.exe",
            file_data=b"malware",
        )


@pytest.mark.asyncio
async def test_create_from_text(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    doc = await svc.create_from_text(
        user_id="u1",
        title="Meeting Notes",
        content="Discussed Q2 OKR targets",
        category="work",
        tags=["meeting", "okr"],
    )
    assert doc.filename == "Meeting Notes.txt"
    assert doc.file_type == "txt"
    assert doc.category == "work"
    assert doc.tags == ["meeting", "okr"]


@pytest.mark.asyncio
async def test_list_documents(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    await svc.upload(user_id="u1", filename="a.txt", file_data=b"aaa", category="notes")
    await svc.upload(user_id="u1", filename="b.md", file_data=b"bbb", category="docs")
    await db_session.commit()

    docs = await svc.list_documents(user_id="u1")
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_list_filter_by_category(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    await svc.upload(user_id="u1", filename="a.txt", file_data=b"aaa", category="notes")
    await svc.upload(user_id="u1", filename="b.txt", file_data=b"bbb", category="docs")
    await db_session.commit()

    docs = await svc.list_documents(user_id="u1", category="notes")
    assert len(docs) == 1
    assert docs[0].category == "notes"


@pytest.mark.asyncio
async def test_get_document(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    doc = await svc.upload(user_id="u1", filename="test.txt", file_data=b"test content")
    await db_session.commit()

    result = await svc.get_document(doc.id, "u1")
    assert result is not None
    assert result.filename == "test.txt"

    # Different user should not see it
    result2 = await svc.get_document(doc.id, "other-user")
    assert result2 is None


@pytest.mark.asyncio
async def test_delete_document(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    doc = await svc.upload(user_id="u1", filename="test.txt", file_data=b"test")
    await db_session.commit()

    # Different user cannot delete
    deleted = await svc.delete_document(doc.id, "other-user")
    assert deleted is False

    deleted = await svc.delete_document(doc.id, "u1")
    assert deleted is True

    result = await svc.get_document(doc.id, "u1")
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    deleted = await svc.delete_document(uuid.uuid4(), "u1")
    assert deleted is False


@pytest.mark.asyncio
async def test_search_files(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    await svc.upload(user_id="u1", filename="python.txt", file_data=b"Python is a programming language")
    await svc.upload(user_id="u1", filename="recipe.txt", file_data=b"How to make chocolate cake")
    await db_session.commit()

    results = await svc.search(user_id="u1", query="programming language")
    assert len(results) >= 1
    assert results[0]["filename"] in ("python.txt", "recipe.txt")
    assert "similarity" in results[0]
    assert "file_id" in results[0]
    assert "extracted_text" in results[0]


@pytest.mark.asyncio
async def test_search_files_filter_by_type(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    await svc.upload(user_id="u1", filename="doc.txt", file_data=b"Some text content")
    await svc.upload(user_id="u1", filename="notes.md", file_data=b"Markdown notes here")
    await db_session.commit()

    results = await svc.search(user_id="u1", query="content", file_types=["txt"])
    assert all(r["file_type"] == "txt" for r in results)


@pytest.mark.asyncio
async def test_search_files_filter_by_category(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    await svc.upload(user_id="u1", filename="a.txt", file_data=b"Work related stuff", category="work")
    await svc.upload(user_id="u1", filename="b.txt", file_data=b"Personal diary entry", category="personal")
    await db_session.commit()

    results = await svc.search(user_id="u1", query="stuff", category="work")
    assert all(r["category"] == "work" for r in results)


@pytest.mark.asyncio
async def test_search_files_no_results(db_session, mock_embedding, mock_storage):
    svc = FileService(db_session, mock_embedding, mock_storage)
    await svc.upload(user_id="u1", filename="a.txt", file_data=b"Some content")
    await db_session.commit()

    results = await svc.search(user_id="u2", query="anything")
    assert results == []
