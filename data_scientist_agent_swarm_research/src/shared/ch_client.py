"""ClickHouse connection helper. Singleton via @lru_cache."""
import os
from functools import lru_cache
import clickhouse_connect
from clickhouse_connect.driver import Client


@lru_cache(maxsize=1)
def get_client() -> Client:
    return clickhouse_connect.get_client(
        host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        username=os.environ.get("CLICKHOUSE_USERNAME", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database=os.environ.get("CLICKHOUSE_DATABASE", "cervid_analytics"),
        secure=os.environ.get("CLICKHOUSE_SECURE", "false").lower() == "true",
        verify=os.environ.get("CLICKHOUSE_VERIFY_SSL", "true").lower() == "true",
    )
