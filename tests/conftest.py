"""
Shared pytest configuration for all Massi-Bot tests.
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def anyio_backend():
    """Lock all anyio tests to asyncio — trio is not installed."""
    return "asyncio"


@pytest.fixture(autouse=True)
def mock_memory_manager():
    """
    Patch memory_manager globally to prevent real Supabase/sentence-transformers
    calls during tests. Without this, anyio event-loop teardown fails because
    httpx transports can't close after the loop is shut down.
    """
    try:
        from llm import memory_manager as mm_module
        with patch.object(mm_module.memory_manager, "get_context_memories",
                          new=AsyncMock(return_value=[])), \
             patch.object(mm_module.memory_manager, "maybe_extract_and_store",
                          new=AsyncMock(return_value=None)):
            yield
    except Exception:
        # Module not importable in this test context — skip patching
        yield
