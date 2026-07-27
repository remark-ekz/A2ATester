from __future__ import annotations

import uuid
from typing import Any


SUPPORTED_PROTOCOL_VERSIONS = ("0.1", "0.2", "0.3", "1.0")


def normalize_protocol_version(value: str | None) -> str:
    candidate = str(value or "1.0").strip().lower()
    aliases = {
        "0.1.0": "0.1",
        "0.2.0": "0.2",
        "0.2.6": "0.2",
        "0.3.0": "0.3",
        "1": "1.0",
        "1.0.0": "1.0",
    }
    normalized = aliases.get(candidate, candidate)
    if normalized not in SUPPORTED_PROTOCOL_VERSIONS:
        supported = ", ".join(SUPPORTED_PROTOCOL_VERSIONS)
        raise ValueError(f"Unsupported A2A protocol version: {value}. Supported versions: {supported}")
    return normalized


def is_v1(protocol_version: str | None) -> bool:
    return normalize_protocol_version(protocol_version) == "1.0"


def message_method(protocol_version: str | None, *, stream: bool = False) -> str:
    if is_v1(protocol_version):
        return "SendStreamingMessage" if stream else "SendMessage"
    return "message/stream" if stream else "message/send"


def task_method(protocol_version: str | None, action: str) -> str:
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"get", "cancel"}:
        raise ValueError(f"Unsupported task action: {action}")
    if is_v1(protocol_version):
        return "GetTask" if normalized_action == "get" else "CancelTask"
    return "tasks/get" if normalized_action == "get" else "tasks/cancel"


def new_jsonrpc_id() -> str:
    return str(uuid.uuid4())


def build_message_request(
    *,
    method: str,
    text: str = "",
    parts: list[dict[str, Any]] | None = None,
    context_id: str = "",
    task_id: str = "",
    metadata: dict[str, Any] | None = None,
    protocol_version: str = "1.0",
    tenant: str = "",
    jsonrpc_id: str | None = None,
) -> dict[str, Any]:
    version_is_v1 = is_v1(protocol_version)
    message_parts = build_message_parts(
        text=text,
        parts=parts,
        protocol_version=protocol_version,
    )
    message: dict[str, Any] = {
        "role": "ROLE_USER" if version_is_v1 else "user",
        "messageId": str(uuid.uuid4()),
        "parts": message_parts,
    }
    if not version_is_v1:
        message["kind"] = "message"
    if context_id:
        message["contextId"] = context_id
    if task_id:
        message["taskId"] = task_id

    params: dict[str, Any] = {"message": message}
    if version_is_v1 and tenant:
        params["tenant"] = tenant
    if metadata:
        params["metadata"] = metadata

    return {
        "jsonrpc": "2.0",
        "id": jsonrpc_id or new_jsonrpc_id(),
        "method": method,
        "params": params,
    }


def build_message_parts(
    *,
    text: str = "",
    parts: list[dict[str, Any]] | None = None,
    protocol_version: str = "1.0",
) -> list[dict[str, Any]]:
    """Build protocol-specific message parts from the tester's neutral format."""
    source_parts = parts if parts is not None else [{"type": "text", "text": text}]
    version_is_v1 = is_v1(protocol_version)
    built: list[dict[str, Any]] = []

    for source in source_parts:
        if not isinstance(source, dict):
            raise ValueError("Each message part must be an object")
        part_type = str(source.get("type") or "").strip().lower()

        if part_type == "text":
            value = str(source.get("text") or "")
            if not value:
                continue
            built.append({"text": value, "mediaType": "text/plain"} if version_is_v1 else {"kind": "text", "text": value})
            continue

        if part_type == "data":
            data = source.get("data")
            if not isinstance(data, dict):
                raise ValueError("JSON data part must contain an object")
            built.append({"data": data, "mediaType": "application/json"} if version_is_v1 else {"kind": "data", "data": data})
            continue

        if part_type == "file":
            filename = str(source.get("filename") or "file").strip() or "file"
            media_type = str(source.get("mediaType") or "application/octet-stream").strip() or "application/octet-stream"
            content = str(source.get("contentBase64") or "")
            if not content:
                raise ValueError(f"File content is missing: {filename}")
            if version_is_v1:
                built.append({"raw": content, "filename": filename, "mediaType": media_type})
            else:
                built.append(
                    {
                        "kind": "file",
                        "file": {"bytes": content, "name": filename, "mimeType": media_type},
                    }
                )
            continue

        raise ValueError(f"Unsupported message part type: {part_type or 'unknown'}")

    if not built:
        raise ValueError("Message is empty")
    return built


def build_task_request(
    *,
    method: str,
    task_id: str,
    protocol_version: str = "1.0",
    tenant: str = "",
    jsonrpc_id: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"id": task_id}
    if is_v1(protocol_version) and tenant:
        params["tenant"] = tenant
    return {
        "jsonrpc": "2.0",
        "id": jsonrpc_id or new_jsonrpc_id(),
        "method": method,
        "params": params,
    }
