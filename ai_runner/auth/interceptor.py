"""CLI stdout link interceptor for capturing authentication URLs."""

import re
import asyncio
from typing import List, Callable, Optional, Awaitable

URL_REGEX = re.compile(r"https?://[^\s<>\"']+")

# Patterns that suggest an OAuth / login verification URL
AUTH_KEYWORDS = ["oauth", "auth", "login", "authenticate", "device", "verification", "accounts.google.com", "github.com/login"]

class CliLinkInterceptor:
    def __init__(self):
        self.callbacks: List[Callable[[str], Awaitable[None]]] = []
        self._latest_url: Optional[str] = None
        self._auth_event = asyncio.Event()

    def register_callback(self, cb: Callable[[str], Awaitable[None]]) -> None:
        self.callbacks.append(cb)

    async def inspect_line(self, line: str) -> Optional[str]:
        """Scans a line for URLs that match auth keywords. If found, dispatches to callbacks."""
        matches = URL_REGEX.findall(line)
        for url in matches:
            url_lower = url.lower()
            if any(kw in url_lower for kw in AUTH_KEYWORDS):
                self._latest_url = url
                self._auth_event.set()
                for cb in self.callbacks:
                    try:
                        await cb(url)
                    except Exception:
                        pass
                return url
        return None

    @property
    def latest_url(self) -> Optional[str]:
        return self._latest_url

    async def wait_for_url(self, timeout: float = 30.0) -> Optional[str]:
        """Waits until an auth URL has been intercepted or timeout expires."""
        try:
            await asyncio.wait_for(self._auth_event.wait(), timeout=timeout)
            return self._latest_url
        except asyncio.TimeoutError:
            return None

    def reset(self) -> None:
        self._latest_url = None
        self._auth_event.clear()

link_interceptor = CliLinkInterceptor()
