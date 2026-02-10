"""Security tests for search functionality."""

import pytest
from unittest.mock import AsyncMock, patch

from server.app.services.search import search_memories

pytestmark = pytest.mark.asyncio


class TestVectorValidation:
    """Test vector validation to prevent SQL injection."""

    async def test_invalid_vector_with_non_numeric_values(
        self, db_session, test_tenant
    ):
        """Test that non-numeric vector values are rejected."""
        tenant, _ = test_tenant

        # Mock embedding service to return invalid data
        with patch(
            "server.app.services.search.get_embedding_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            # Simulate malicious vector with SQL injection attempt
            mock_service.embed.return_value = ["'; DROP TABLE embeddings; --"]
            mock_get_service.return_value = mock_service

            with pytest.raises(ValueError, match="Invalid vector data"):
                await search_memories(
                    db=db_session,
                    tenant_id=tenant.id,
                    user_id="test_user",
                    query="test query",
                )

    async def test_invalid_vector_with_boolean_values(
        self, db_session, test_tenant
    ):
        """Test that boolean values in vector are rejected."""
        tenant, _ = test_tenant

        with patch(
            "server.app.services.search.get_embedding_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            # Booleans should be rejected (True/False could be 1/0)
            mock_service.embed.return_value = [True, False, 0.5]
            mock_get_service.return_value = mock_service

            with pytest.raises(ValueError, match="Invalid vector data"):
                await search_memories(
                    db=db_session,
                    tenant_id=tenant.id,
                    user_id="test_user",
                    query="test query",
                )

    async def test_valid_vector_with_floats(self, db_session, test_tenant):
        """Test that valid float vectors are accepted."""
        tenant, _ = test_tenant

        with patch(
            "server.app.services.search.get_embedding_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            # Valid numeric vector
            mock_service.embed.return_value = [0.1, 0.2, 0.3, -0.5, 1.0]
            mock_get_service.return_value = mock_service

            # Should not raise ValueError
            result = await search_memories(
                db=db_session,
                tenant_id=tenant.id,
                user_id="test_user",
                query="test query",
            )
            # Result might be empty but shouldn't error on validation
            assert isinstance(result, list)

    async def test_valid_vector_with_integers(self, db_session, test_tenant):
        """Test that valid integer vectors are accepted."""
        tenant, _ = test_tenant

        with patch(
            "server.app.services.search.get_embedding_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            # Valid integer vector (though unusual for embeddings)
            mock_service.embed.return_value = [1, 2, 3, -1, 0]
            mock_get_service.return_value = mock_service

            # Should not raise ValueError
            result = await search_memories(
                db=db_session,
                tenant_id=tenant.id,
                user_id="test_user",
                query="test query",
            )
            assert isinstance(result, list)
