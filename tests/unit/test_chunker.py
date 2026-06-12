import pytest

from src.ingestion.chunker import DocumentChunker


@pytest.fixture
def chunker():
    return DocumentChunker()


def test_chunker_splits_long_text(chunker):
    doc = {
        "url": "https://www.cni.it/test",
        "title": "Test Document",
        "content": "Parola " * 1000,
        "meta": {"source": "https://www.cni.it/test", "type": "html"},
    }
    chunks = chunker.chunk_document(doc)
    assert len(chunks) > 1
    assert all("content" in c for c in chunks)
    assert all("metadata" in c for c in chunks)


def test_chunker_short_text_single_chunk(chunker):
    doc = {
        "url": "https://www.cni.it/test",
        "title": "Short Doc",
        "content": "Breve testo di esempio per il chunker.",
        "meta": {"source": "https://www.cni.it/test"},
    }
    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0]["content"] == doc["content"]


def test_chunker_empty_content(chunker):
    doc = {
        "url": "https://www.cni.it/test",
        "title": "Empty",
        "content": "",
        "meta": {},
    }
    chunks = chunker.chunk_document(doc)
    assert chunks == []


def test_chunker_preserves_metadata(chunker):
    doc = {
        "url": "https://www.cni.it/test",
        "title": "Test",
        "content": "Contenuto di prova.",
        "meta": {"source": "https://www.cni.it/test", "category": "normativa"},
    }
    chunks = chunker.chunk_document(doc)
    assert chunks[0]["metadata"]["source"] == "https://www.cni.it/test"
    assert chunks[0]["metadata"]["title"] == "Test"
    assert chunks[0]["metadata"]["category"] == "normativa"


def test_chunker_has_chunk_index(chunker):
    doc = {
        "url": "https://www.cni.it/test",
        "title": "Test",
        "content": "Parola " * 1000,
        "meta": {},
    }
    chunks = chunker.chunk_document(doc)
    for i, c in enumerate(chunks):
        assert c["metadata"]["chunk_index"] == i
    assert chunks[0]["metadata"]["total_chunks"] == len(chunks)
