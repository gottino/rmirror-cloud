"""Tests for Obsidian sync service."""

import hashlib

from app.services.obsidian_service import (
    compute_notebook_content_hash,
    generate_api_key,
    hash_api_key,
)


class TestApiKeyGeneration:
    def test_generate_api_key_returns_url_safe_string(self):
        key = generate_api_key()
        assert isinstance(key, str)
        assert len(key) == 43

    def test_generate_api_key_is_unique(self):
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1 != key2

    def test_hash_api_key_returns_sha256(self):
        key = "test-api-key-123"
        hashed = hash_api_key(key)
        expected = hashlib.sha256(key.encode()).hexdigest()
        assert hashed == expected
        assert len(hashed) == 64

    def test_hash_api_key_is_deterministic(self):
        key = "test-api-key-123"
        assert hash_api_key(key) == hash_api_key(key)


class TestNotebookContentHash:
    def test_empty_pages_returns_none(self):
        result = compute_notebook_content_hash([])
        assert result is None

    def test_single_page(self):
        pages = [(1, "Hello world")]
        result = compute_notebook_content_hash(pages)
        expected = hashlib.sha256("1:Hello world".encode()).hexdigest()
        assert result == expected

    def test_multiple_pages_ordered(self):
        pages = [(1, "Page one"), (2, "Page two")]
        result = compute_notebook_content_hash(pages)
        expected = hashlib.sha256("1:Page one2:Page two".encode()).hexdigest()
        assert result == expected

    def test_page_order_matters(self):
        pages_a = [(1, "First"), (2, "Second")]
        pages_b = [(2, "Second"), (1, "First")]
        assert compute_notebook_content_hash(pages_a) != compute_notebook_content_hash(
            pages_b
        )

    def test_content_change_changes_hash(self):
        pages_a = [(1, "Original text")]
        pages_b = [(1, "Modified text")]
        assert compute_notebook_content_hash(pages_a) != compute_notebook_content_hash(
            pages_b
        )
