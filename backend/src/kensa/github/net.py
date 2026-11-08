"""Outbound HTTP for the GitHub integration: public addresses only, checked when connecting.

``PublicAddressBackend`` resolves the host once, refuses the connection if any address is not
globally routable (private, loopback, link-local, shared, reserved, multicast; IPv4-mapped IPv6
included), and then connects to the vetted address itself. TLS still verifies the certificate
against the original hostname (httpcore passes it as the SNI name), so a DNS answer that changes
between a check and the connection (DNS rebinding) cannot reach an internal service.

Clients are built with ``trust_env=False``: no proxy variables and no ``.netrc`` credentials are
picked up from the environment, and no cookies are kept.
"""

import socket
from collections.abc import Callable, Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

import httpcore
import httpx

Resolver = Callable[[str, int], list[str]]


class PrivateAddressError(httpcore.ConnectError):
    """The destination resolved to an address that is not globally routable."""


def is_public_address(value: str) -> bool:
    try:
        address: IPv4Address | IPv6Address = ip_address(value)
    except ValueError:
        return False
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


class PublicAddressBackend(httpcore.NetworkBackend):
    def __init__(
        self,
        resolver: Resolver = system_resolver,
        inner: httpcore.NetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._inner = inner or httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        try:
            addresses = self._resolver(host, port)
        except OSError as exc:
            raise httpcore.ConnectError(f"cannot resolve {host}") from exc
        if not addresses:
            raise httpcore.ConnectError(f"cannot resolve {host}")
        refused = [a for a in addresses if not is_public_address(a)]
        if refused:
            raise PrivateAddressError(f"{host} resolves to a non-public address")
        return self._inner.connect_tcp(addresses[0], port, timeout, local_address, socket_options)

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


class PublicOnlyTransport(httpx.HTTPTransport):
    """An httpx transport whose connection pool uses ``PublicAddressBackend``."""

    def __init__(self, backend: httpcore.NetworkBackend | None = None) -> None:
        super().__init__(trust_env=False, retries=0)
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=4,
            max_keepalive_connections=2,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=backend or PublicAddressBackend(),
        )


def build_client(
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    backend: httpcore.NetworkBackend | None = None,
) -> httpx.Client:
    """A client that follows no redirects and takes nothing from the environment."""
    return httpx.Client(
        transport=PublicOnlyTransport(backend),
        timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        follow_redirects=False,
        trust_env=False,
        headers=headers or {},
    )
