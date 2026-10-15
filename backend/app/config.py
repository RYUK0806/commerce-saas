"""
Application settings loaded from environment variables.

Every secret and connection string lives here, validated at startup.
If a required variable is missing, the app fails immediately with a
clear error — not halfway through a request.

Uses Pydantic BaseSettings: it reads from environment variables
automatically, with type validation and defaults where safe.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All configuration for the application.

    Required variables (no default — app won't start without them):
    - DATABASE_URL: PostgreSQL connection string
    - REDIS_URL: Redis connection for background jobs
    - CLERK_SECRET_KEY: Clerk backend API key for verifying session tokens
    - CLERK_PUBLISHABLE_KEY: Clerk frontend key (passed to the React app)
    - CLERK_ISSUER: Clerk Frontend API URL, the expected token issuer
    - ENCRYPTION_KEY: Fernet key for encrypting channel credentials at rest

    Optional variables (safe defaults provided):
    - APP_NAME, DEBUG, CORS origins, etc.
    """

    # --- App ---
    app_name: str = "Commerce SaaS"
    debug: bool = False

    # --- Database ---
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    # asyncpg because our FastAPI app is fully async
    database_url: str

    # --- Redis ---
    # Used by arq for background job processing
    redis_url: str

    # --- Authentication (Clerk) ---
    # Secret key: used server-side to verify JWT session tokens
    # Never expose this to the frontend
    clerk_secret_key: str

    # Publishable key: safe to expose, used by the React frontend
    clerk_publishable_key: str

    # Clerk Frontend API URL, no trailing slash (e.g. https://xxx.clerk.accounts.dev).
    # Tokens' "iss" must equal it; public keys are served at <issuer>/.well-known/jwks.json
    clerk_issuer: str

    # --- Encryption ---
    # Fernet symmetric key for encrypting OAuth tokens in the database
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str

    # --- CORS ---
    # Comma-separated list of allowed frontend origins
    # In production: "https://app.yourdomain.com"
    # In development: "http://localhost:5173"
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- File Storage ---
    # S3-compatible storage for product images and campaign assets
    s3_bucket_name: str = "commerce-saas-assets"
    s3_region: str = "ap-south-1"
    # AWS credentials are optional here — in production, use IAM roles instead
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    model_config = {
        # Reads from a .env file in the project root if it exists
        # Environment variables override .env file values
        "env_file": ".env",
        # Makes variable names case-insensitive
        # DATABASE_URL, database_url, Database_Url all work
        "case_sensitive": False,
    }


# Single instance used across the app
# Imported as: from app.config import settings
settings = Settings()
