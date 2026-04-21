from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8090
    log_level: str = "INFO"

    # Default database (optional, for single-db mode)
    database_uri: str = ""

    # Access mode: "unrestricted" (read/write) or "restricted" (read-only + timeouts)
    access_mode: str = "unrestricted"

    # Query timeout in seconds
    query_timeout: int = 30

    # Pool settings
    pool_min_size: int = 2
    pool_max_size: int = 10

    # Metadata cache TTL in seconds
    metadata_cache_ttl: int = 600

    # Session idle timeout in seconds (8 hours)
    session_timeout: int = 28800

    # API key for Bearer token authentication (empty = no auth required)
    api_key: str = ""

    # In-memory rate limiting for auth-sensitive endpoints.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_mcp_requests: int = 60
    rate_limit_api_requests: int = 60
    rate_limit_oauth_requests: int = 10

    # Compatibility-only OAuth token endpoint (/oauth/token).
    # Disabled by default to avoid exposing static bearer secrets via browser/API clients.
    enable_simple_token_endpoint: bool = False

    model_config = {"env_prefix": "PG_MCP_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
