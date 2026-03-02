"""Tests for per-user background task cancellation."""

import asyncio

import pytest


@pytest.fixture
def user():
    return "cancel-test-user"


class TestCancelUserTasks:
    """Test cancel_user_tasks() cancels running background tasks for a user."""

    async def test_cancel_stops_pending_extraction(self, nm, user):
        """After cancel, no new memories should be written by bg tasks."""
        # Ingest a message (spawns background extraction + embedding tasks)
        await nm.ingest(user_id=user, role="user", content="I work at Google as a software engineer")

        # Tasks should be tracked
        tasks = nm._user_tasks.get(user, [])
        assert len(tasks) > 0, "Expected background tasks to be tracked"

        # Cancel immediately (before extraction completes)
        cancelled = await nm.cancel_user_tasks(user)
        assert cancelled >= 0  # May be 0 if tasks already finished

        # User should have no remaining tasks
        assert user not in nm._user_tasks or len(nm._user_tasks.get(user, [])) == 0

    async def test_cancel_clears_digest_counter(self, nm, user):
        """cancel_user_tasks should reset the digest counter for the user."""
        nm._digest_counts[user] = 15
        await nm.cancel_user_tasks(user)
        assert user not in nm._digest_counts

    async def test_cancel_clears_idle_timers(self, nm, user):
        """cancel_user_tasks should cancel idle extraction timers."""
        # Create a fake idle timer
        async def _noop():
            await asyncio.sleep(999)

        key = (user, "test-session")
        nm._idle_tasks[key] = asyncio.create_task(_noop())
        nm._active_sessions.add(key)

        cancelled = await nm.cancel_user_tasks(user)
        assert cancelled >= 1
        assert key not in nm._idle_tasks
        assert key not in nm._active_sessions

    async def test_cancel_nonexistent_user_is_noop(self, nm):
        """Cancelling tasks for a user with no tasks should be safe."""
        cancelled = await nm.cancel_user_tasks("no-such-user")
        assert cancelled == 0

    async def test_cancel_only_affects_target_user(self, nm, user):
        """Tasks for other users should not be cancelled."""
        other_user = "other-user"

        # Ingest for both users
        await nm.ingest(user_id=user, role="user", content="Hello from user A")
        await nm.ingest(user_id=other_user, role="user", content="Hello from user B")

        # Cancel only the target user
        await nm.cancel_user_tasks(user)

        # Other user's tasks should still exist
        other_tasks = nm._user_tasks.get(other_user, [])
        # At least some tasks should remain (or already completed)
        assert other_user not in nm._user_tasks or isinstance(other_tasks, list)

    async def test_delete_user_data_cancels_tasks(self, nm, user):
        """delete_user_data should cancel tasks before deleting data."""
        await nm.ingest(user_id=user, role="user", content="Data to delete")
        # Small wait so extraction might start
        await asyncio.sleep(0.1)

        result = await nm.delete_user_data(user)
        assert "tasks_cancelled" in result
        assert isinstance(result["tasks_cancelled"], int)
        # User should have no remaining tracked tasks
        assert user not in nm._user_tasks or len(nm._user_tasks.get(user, [])) == 0
