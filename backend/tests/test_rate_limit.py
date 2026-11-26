from app.core.rate_limit import get_storage_uri


def test_rate_limit_uses_memory_storage_without_redis():
    assert get_storage_uri(None) == "memory://"
    assert get_storage_uri("") == "memory://"
    assert get_storage_uri("   ") == "memory://"


def test_rate_limit_uses_configured_redis_storage():
    redis_url = "rediss://default:secret@redis.example.com:6380/0"

    assert get_storage_uri(redis_url) == redis_url
