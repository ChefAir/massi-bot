"""
Massi-Bot - Supabase Client

Singleton client for all Supabase operations.
Uses service_role key to bypass RLS.
"""

import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    """
    Return the singleton Supabase client, initializing it on first call.
    Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from environment.
    """
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
        logger.info("Supabase client initialized")
    return _client
