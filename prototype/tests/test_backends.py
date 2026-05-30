"""Tests for backend factories and abstract base classes."""
import pytest

from wincrash_analyzer.backends.ai.factory import create_ai_backend
from wincrash_analyzer.backends.debug.factory import create_debug_backend
from wincrash_analyzer.backends.store.factory import create_storage_backend
from wincrash_analyzer.backends.ai.base import AIBackendBase
from wincrash_analyzer.backends.debug.base import DebugBackendBase
from wincrash_analyzer.backends.store.base import StorageBackendBase


def test_ai_factory_gemini():
    backend = create_ai_backend("gemini")
    assert isinstance(backend, AIBackendBase)


def test_ai_factory_openai():
    backend = create_ai_backend("openai")
    assert isinstance(backend, AIBackendBase)


def test_ai_factory_unknown():
    with pytest.raises(ValueError):
        create_ai_backend("unknown")


def test_debug_factory_cdb():
    backend = create_debug_backend("cdb")
    assert isinstance(backend, DebugBackendBase)


def test_debug_factory_js():
    backend = create_debug_backend("js")
    assert isinstance(backend, DebugBackendBase)


def test_debug_factory_unknown():
    with pytest.raises(ValueError):
        create_debug_backend("unknown")


def test_store_factory_filesystem():
    backend = create_storage_backend("filesystem")
    assert isinstance(backend, StorageBackendBase)


def test_store_factory_sqlite():
    backend = create_storage_backend("sqlite")
    assert isinstance(backend, StorageBackendBase)


def test_store_factory_unknown():
    with pytest.raises(ValueError):
        create_storage_backend("unknown")
