"""HTTP client for publishing messages to ntfy topics."""

from __future__ import annotations

import requests
from requests.auth import HTTPBasicAuth


class NtfyPublishError(Exception):
    """Raised when ntfy returns a non-success HTTP response or the request fails."""


class NtfyClient:
    """Publish plain-text notifications to an ntfy server topic.

    Uses ntfy's HTTP publish API: POST ``{server_url}/{topic}`` with metadata
    supplied via headers (Title, Priority, Tags). See https://docs.ntfy.sh/publish/
    """

    def __init__(
        self,
        server_url: str,
        topic: str,
        *,
        access_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: int = 10,
    ) -> None:
        """Initialize the client.

        :param server_url: Base ntfy server URL (e.g. ``https://ntfy.sh``).
        :param topic: Topic name to publish to.
        :param access_token: Optional bearer token for authenticated topics.
        :param username: Optional basic-auth username.
        :param password: Optional basic-auth password.
        :param timeout: HTTP request timeout in seconds.
        """
        self.server_url = server_url.rstrip('/')
        self.topic = topic.strip('/')
        self.access_token = access_token or None
        self.username = username or None
        self.password = password or None
        self.timeout = timeout

    @property
    def publish_url(self) -> str:
        """Return the fully qualified publish URL for this topic."""
        return f'{self.server_url}/{self.topic}'

    def _build_headers(self, *, title: str, priority: int, tags: list[str]) -> dict[str, str]:
        """Build ntfy metadata headers for a publish request."""
        headers = {
            'Title': title,
            'Priority': str(priority),
        }
        if tags:
            headers['Tags'] = ','.join(tags)
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers

    def _build_auth(self) -> HTTPBasicAuth | None:
        """Return HTTP basic auth when username and password are configured."""
        if self.username and self.password:
            return HTTPBasicAuth(self.username, self.password)
        return None

    def publish(
        self,
        message: str,
        *,
        title: str,
        priority: int,
        tags: list[str],
    ) -> None:
        """Publish a notification to the configured topic.

        :param message: Plain-text message body.
        :param title: Notification title (ntfy ``Title`` header).
        :param priority: ntfy priority (1=min, 5=max).
        :param tags: List of emoji shortcodes or tag names.
        :raises NtfyPublishError: On HTTP errors or network failures.
        """
        try:
            response = requests.post(
                self.publish_url,
                data=message.encode('utf-8'),
                headers=self._build_headers(title=title, priority=priority, tags=tags),
                auth=self._build_auth(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NtfyPublishError(str(exc)) from exc

        if not response.ok:
            detail = response.text.strip() or response.reason
            raise NtfyPublishError(
                f'ntfy publish failed ({response.status_code}): {detail}'
            )
