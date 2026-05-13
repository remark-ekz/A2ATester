from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse, urlunparse

import httpx

from a2a_tester.a2a.sse import parse_sse_lines


@dataclass(frozen=True)
class A2ARequestConfig:
    endpoint: str
    headers: dict[str, str]
    tls_verify: bool = True
    ca_bundle_path: str = ""
    client_cert_path: str = ""
    client_key_path: str = ""
    timeout_seconds: float = 60


@dataclass(frozen=True)
class HttpExchange:
    request_json: dict[str, Any]
    response_json: dict[str, Any]
    response_headers: dict[str, str]
    status_code: int | None
    latency_ms: float | None
    error: str = ""
    request_url: str = ""
    request_method: str = "POST"


def _uses_tls(endpoint: str) -> bool:
    return urlparse(endpoint).scheme.lower() == "https"


def _existing_path(value: str, label: str) -> str:
    path = Path(value).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if not path.is_file():
        raise ValueError(f"{label} is not a file: {path}")
    return str(path)


def _verify_value(config: A2ARequestConfig) -> bool | ssl.SSLContext:
    if not _uses_tls(config.endpoint):
        return True

    has_custom_tls = bool(config.ca_bundle_path or config.client_cert_path or config.client_key_path)
    if not config.tls_verify:
        if not has_custom_tls:
            return False
        context = ssl._create_unverified_context()
    elif has_custom_tls:
        context = ssl.create_default_context(
            cafile=_existing_path(config.ca_bundle_path, "CA bundle") if config.ca_bundle_path else None
        )
    else:
        return True

    if config.client_cert_path or config.client_key_path:
        if not config.client_cert_path:
            raise ValueError("Client certificate is required when client key is configured")
        certfile = _existing_path(config.client_cert_path, "Client certificate")
        keyfile = _existing_path(config.client_key_path, "Client key") if config.client_key_path else None
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    return context


def _headers(config: A2ARequestConfig, *, stream: bool = False) -> dict[str, str]:
    headers = dict(config.headers)
    headers.setdefault("Content-Type", "application/json")
    if stream:
        headers.setdefault("Accept", "text/event-stream")
    else:
        headers.setdefault("Accept", "application/json")
    return headers


def _timeout(config: A2ARequestConfig) -> httpx.Timeout:
    request_timeout = max(1.0, float(config.timeout_seconds or 60))
    return httpx.Timeout(
        request_timeout,
        connect=min(5.0, request_timeout),
        read=request_timeout,
        write=min(10.0, request_timeout),
        pool=min(5.0, request_timeout),
    )


def _network_error(exc: Exception, config: A2ARequestConfig) -> str:
    request_timeout = max(1.0, float(config.timeout_seconds or 60))
    connect_timeout = min(5.0, request_timeout)
    if isinstance(exc, httpx.ConnectTimeout):
        return f"Таймаут подключения {connect_timeout:.0f}s: {config.endpoint}"
    if isinstance(exc, httpx.ReadTimeout):
        return f"Таймаут ответа {request_timeout:.0f}s: {config.endpoint}"
    if isinstance(exc, httpx.WriteTimeout):
        return f"Таймаут отправки {min(10.0, request_timeout):.0f}s: {config.endpoint}"
    if isinstance(exc, httpx.PoolTimeout):
        return f"Таймаут ожидания HTTP-клиента {min(5.0, request_timeout):.0f}s"
    if isinstance(exc, httpx.ConnectError):
        return f"Ошибка подключения к {config.endpoint}: {exc}"
    if isinstance(exc, httpx.TimeoutException):
        return f"Таймаут запроса {request_timeout:.0f}s: {config.endpoint}"
    return str(exc)


def post_json_rpc(config: A2ARequestConfig, request_json: dict[str, Any]) -> HttpExchange:
    started = time.perf_counter()
    try:
        with httpx.Client(
            verify=_verify_value(config),
            timeout=_timeout(config),
            trust_env=False,
        ) as client:
            response = client.post(config.endpoint, json=request_json, headers=_headers(config))
            elapsed = (time.perf_counter() - started) * 1000
            response_headers = dict(response.headers)
            try:
                response_json = response.json()
            except json.JSONDecodeError:
                response_json = {"raw": response.text}
            return HttpExchange(
                request_json=request_json,
                response_json=response_json,
                response_headers=response_headers,
                status_code=response.status_code,
                latency_ms=elapsed,
                error="" if response.is_success else response.text[:2000],
                request_url=config.endpoint,
                request_method="POST",
            )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return HttpExchange(
            request_json=request_json,
            response_json={},
            response_headers={},
            status_code=None,
            latency_ms=elapsed,
            error=_network_error(exc, config),
            request_url=config.endpoint,
            request_method="POST",
        )


def stream_json_rpc(config: A2ARequestConfig, request_json: dict[str, Any]) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    try:
        with httpx.Client(
            verify=_verify_value(config),
            timeout=_timeout(config),
            trust_env=False,
        ) as client:
            with client.stream(
                "POST",
                config.endpoint,
                json=request_json,
                headers=_headers(config, stream=True),
            ) as response:
                elapsed = (time.perf_counter() - started) * 1000
                yield {
                    "type": "headers",
                    "method": "POST",
                    "url": config.endpoint,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "latency_ms": elapsed,
                }
                response.raise_for_status()
                for event in parse_sse_lines(response.iter_lines()):
                    raw_data = event.get("data", "")
                    try:
                        payload = json.loads(raw_data)
                    except json.JSONDecodeError:
                        payload = {"raw": raw_data}
                    yield {
                        "type": "event",
                        "event": event,
                        "payload": payload,
                    }
    except Exception as exc:
        raise RuntimeError(_network_error(exc, config)) from exc


def derive_agent_card_url(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        return endpoint.rstrip("/") + "/.well-known/agent-card.json"
    return urlunparse((parsed.scheme, parsed.netloc, "/.well-known/agent-card.json", "", "", ""))


def fetch_agent_card(config: A2ARequestConfig, *, url: str | None = None) -> HttpExchange:
    url = url or derive_agent_card_url(config.endpoint)
    request_json = {"method": "GET", "url": url}
    started = time.perf_counter()
    try:
        with httpx.Client(
            verify=_verify_value(config),
            timeout=_timeout(config),
            trust_env=False,
        ) as client:
            response = client.get(url, headers=config.headers)
            elapsed = (time.perf_counter() - started) * 1000
            try:
                payload = response.json()
            except json.JSONDecodeError:
                payload = {"raw": response.text}
            return HttpExchange(
                request_json=request_json,
                response_json=payload,
                response_headers=dict(response.headers),
                status_code=response.status_code,
                latency_ms=elapsed,
                error="" if response.is_success else response.text[:2000],
                request_url=url,
                request_method="GET",
            )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return HttpExchange(
            request_json=request_json,
            response_json={},
            response_headers={},
            status_code=None,
            latency_ms=elapsed,
            error=_network_error(exc, config),
            request_url=url,
            request_method="GET",
        )
