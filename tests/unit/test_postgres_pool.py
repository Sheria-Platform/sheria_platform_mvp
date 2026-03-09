"""Verify the async engine is created with explicit pool configuration."""
import services.api.app.memory.postgres as mem_module


def test_engine_has_pool_config():
    pool_impl = mem_module.engine.pool
    assert pool_impl.size() == 10, f"Expected pool_size=10, got {pool_impl.size()}"
    assert pool_impl._max_overflow == 20, f"Expected max_overflow=20, got {pool_impl._max_overflow}"
