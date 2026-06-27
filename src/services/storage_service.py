"""Persistent storage service — same pattern as Sherlock's StorageService."""

import flet as ft


class StorageService:
    """Wraps flet's client_storage for persistent key-value storage."""

    def __init__(self, page: ft.Page):
        self.page = page

    async def get(self, key: str, default=None):
        """Get a value from client storage."""
        try:
            val = await self.page.client_storage.get_async(key)
            return val if val is not None else default
        except Exception:
            return default

    async def set(self, key: str, value):
        """Set a value in client storage."""
        try:
            await self.page.client_storage.set_async(key, value)
        except Exception:
            pass

    async def remove(self, key: str):
        """Remove a value from client storage."""
        try:
            await self.page.client_storage.remove_async(key)
        except Exception:
            pass

    async def contains(self, key: str) -> bool:
        """Check if a key exists in storage."""
        try:
            return await self.page.client_storage.contains_key_async(key)
        except Exception:
            return False
