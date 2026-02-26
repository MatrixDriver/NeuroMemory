"""Tests for KV storage CRUD."""

import pytest

from neuromem.services.kv import KVService


@pytest.mark.asyncio
async def test_set_and_get_string(db_session):
    """Set and get a string value."""
    svc = KVService(db_session)
    kv = await svc.set("user", "u1", "name", "Alice")
    assert kv.namespace == "user"
    assert kv.scope_id == "u1"
    assert kv.key == "name"
    assert kv.value == "Alice"

    result = await svc.get("user", "u1", "name")
    assert result is not None
    assert result.value == "Alice"


@pytest.mark.asyncio
async def test_set_and_get_number(db_session):
    svc = KVService(db_session)
    kv = await svc.set("app", "s1", "count", 42)
    assert kv.value == 42


@pytest.mark.asyncio
async def test_set_and_get_object(db_session):
    svc = KVService(db_session)
    obj = {"theme": "dark", "font_size": 14, "notifications": True}
    kv = await svc.set("user", "u1", "settings", obj)
    assert kv.value == obj


@pytest.mark.asyncio
async def test_set_and_get_array(db_session):
    svc = KVService(db_session)
    arr = [1, "two", {"three": 3}]
    kv = await svc.set("user", "u1", "tags", arr)
    assert kv.value == arr


@pytest.mark.asyncio
async def test_set_and_get_bool(db_session):
    svc = KVService(db_session)
    kv = await svc.set("user", "u1", "active", True)
    assert kv.value is True


@pytest.mark.asyncio
async def test_set_and_get_null(db_session):
    svc = KVService(db_session)
    kv = await svc.set("user", "u1", "optional", None)
    assert kv.value is None


@pytest.mark.asyncio
async def test_upsert(db_session):
    """Setting same key twice should update the value."""
    svc = KVService(db_session)
    await svc.set("user", "u1", "color", "red")
    kv = await svc.set("user", "u1", "color", "blue")
    assert kv.value == "blue"

    result = await svc.get("user", "u1", "color")
    assert result.value == "blue"


@pytest.mark.asyncio
async def test_batch_set(db_session):
    svc = KVService(db_session)
    items = {"max_retries": 3, "timeout": 30.5, "enabled": True}
    results = await svc.batch_set("app", "config", items)
    assert len(results) == 3

    result = await svc.get("app", "config", "max_retries")
    assert result.value == 3


@pytest.mark.asyncio
async def test_list(db_session):
    svc = KVService(db_session)
    await svc.set("session", "s1", "a", 1)
    await svc.set("session", "s1", "b", 2)

    results = await svc.list("session", "s1")
    assert len(results) >= 2
    keys = [item.key for item in results]
    assert "a" in keys
    assert "b" in keys


@pytest.mark.asyncio
async def test_list_with_prefix(db_session):
    svc = KVService(db_session)
    await svc.set("cache", "c1", "user:1:name", "A")
    await svc.set("cache", "c1", "user:1:email", "a@b.c")
    await svc.set("cache", "c1", "user:2:name", "B")
    await svc.set("cache", "c1", "product:1", "X")

    results = await svc.list("cache", "c1", prefix="user:1:")
    assert len(results) == 2
    keys = [item.key for item in results]
    assert "user:1:name" in keys
    assert "user:1:email" in keys
    assert "product:1" not in keys


@pytest.mark.asyncio
async def test_delete(db_session):
    svc = KVService(db_session)
    await svc.set("tmp", "t1", "del_me", "bye")
    deleted = await svc.delete("tmp", "t1", "del_me")
    assert deleted is True

    result = await svc.get("tmp", "t1", "del_me")
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent(db_session):
    svc = KVService(db_session)
    deleted = await svc.delete("no", "such", "key")
    assert deleted is False


@pytest.mark.asyncio
async def test_get_nonexistent(db_session):
    svc = KVService(db_session)
    result = await svc.get("no", "such", "key")
    assert result is None


@pytest.mark.asyncio
async def test_namespace_isolation(db_session):
    svc = KVService(db_session)
    await svc.set("ns1", "s1", "shared_key", "val1")
    await svc.set("ns2", "s1", "shared_key", "val2")

    r1 = await svc.get("ns1", "s1", "shared_key")
    r2 = await svc.get("ns2", "s1", "shared_key")
    assert r1.value == "val1"
    assert r2.value == "val2"
