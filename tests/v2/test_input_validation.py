"""Tests for input validation in time-based queries."""

import pytest
from datetime import datetime, date, timedelta, timezone

from server.app.services.memory import MemoryService

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def memory_service(db_session):
    """Create MemoryService instance."""
    return MemoryService(db_session)


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test_user_validation"


class TestTimeRangeValidation:
    """Test time range validation."""

    async def test_invalid_time_range_start_after_end(
        self, memory_service, test_tenant, test_user_id
    ):
        """Test that start_time >= end_time raises ValueError."""
        tenant, _ = test_tenant
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now - timedelta(hours=1)  # End before start

        with pytest.raises(ValueError, match="start_time must be before end_time"):
            await memory_service.get_memories_by_time_range(
                tenant_id=tenant.id,
                user_id=test_user_id,
                start_time=start_time,
                end_time=end_time,
            )

    async def test_invalid_time_range_equal_times(
        self, memory_service, test_tenant, test_user_id
    ):
        """Test that start_time == end_time raises ValueError."""
        tenant, _ = test_tenant
        now = datetime.now(timezone.utc)

        with pytest.raises(ValueError, match="start_time must be before end_time"):
            await memory_service.get_memories_by_time_range(
                tenant_id=tenant.id,
                user_id=test_user_id,
                start_time=now,
                end_time=now,
            )


class TestDateRangeValidation:
    """Test date range validation."""

    async def test_invalid_date_range_daily_stats(
        self, memory_service, test_tenant, test_user_id
    ):
        """Test that start_date > end_date raises ValueError in daily stats."""
        tenant, _ = test_tenant
        today = date.today()
        start_date = today
        end_date = today - timedelta(days=1)

        with pytest.raises(
            ValueError, match="start_date must be before or equal to end_date"
        ):
            await memory_service.get_daily_memory_stats(
                tenant_id=tenant.id,
                user_id=test_user_id,
                start_date=start_date,
                end_date=end_date,
            )

    async def test_invalid_date_range_timeline(
        self, memory_service, test_tenant, test_user_id
    ):
        """Test that start_date > end_date raises ValueError in timeline."""
        tenant, _ = test_tenant
        today = date.today()
        start_date = today
        end_date = today - timedelta(days=1)

        with pytest.raises(
            ValueError, match="start_date must be before or equal to end_date"
        ):
            await memory_service.get_memory_timeline(
                tenant_id=tenant.id,
                user_id=test_user_id,
                start_date=start_date,
                end_date=end_date,
                granularity="day",
            )

    async def test_valid_equal_dates(self, memory_service, test_tenant, test_user_id):
        """Test that start_date == end_date is valid (same day query)."""
        tenant, _ = test_tenant
        today = date.today()

        # Should not raise
        stats = await memory_service.get_daily_memory_stats(
            tenant_id=tenant.id,
            user_id=test_user_id,
            start_date=today,
            end_date=today,
        )
        assert isinstance(stats, list)
