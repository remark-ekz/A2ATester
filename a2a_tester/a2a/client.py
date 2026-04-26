from __future__ import annotations

import json
import time
from dataclasses import dataclass
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


def _verify_value(config: A2ARequestConfig) -> bool | str:
    if not config.tls_verify:
        return False
    if config.ca_bundle_path:
        return config.ca_bundle_path
    return True


def _cert_value(config: A2ARequestConfig) -> str | tuple[str, str] | None:
    if config.client_cert_path and config.client_key_path:
        return (config.client_cert_path, config.client_key_path)
    if config.client_cert_path:
        return config.client_cert_path
    return None


def _headers(config: A2ARequestConfig, *, stream: bool = False) -> dict[str, str]:
    headers = dict(config.headers)
    headers.setdefault("Content-Type", "application/json")
    if stream:
        headers.setdefault("Accept", "text/event-stream")
    else:
        headers.setdefault("Accept", "application/json")
    return headers


def post_json_rpc(config: A2ARequestConfig, request_json: dict[str, Any]) -> HttpExchange:
    started = time.perf_counter()
    try:
        with httpx.Client(
            verify=_verify_value(config),
            cert=_cert_value(config),
            timeout=config.timeout_seconds,
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
            )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return HttpExchange(
            request_json=request_json,
            response_json={},
            response_headers={},
            status_code=None,
            latency_ms=elapsed,
            error=str(exc),
        )


def stream_json_rpc(config: A2ARequestConfig, request_json: dict[str, Any]) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    with httpx.Client(
        verify=_verify_value(config),
        cert=_cert_value(config),
        timeout=httpx.Timeout(config.timeout_seconds, read=None),
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


def derive_agent_card_url(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        return endpoint.rstrip("/") + "/.well-known/agent-card.json"
    return urlunparse((parsed.scheme, parsed.netloc, "/.well-known/agent-card.json", "", "", ""))


def fetch_agent_card(config: A2ARequestConfig) -> HttpExchange:
    url = derive_agent_card_url(config.endpoint)
    request_json = {"method": "GET", "url": url}
    started = time.perf_counter()
    try:
        with httpx.Client(
            verify=_verify_value(config),
            cert=_cert_value(config),
            timeout=config.timeout_seconds,
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
            )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return HttpExchange(
            request_json=request_json,
            response_json={},
            response_headers={},
            status_code=None,
            latency_ms=elapsed,
            error=str(exc),
        )
