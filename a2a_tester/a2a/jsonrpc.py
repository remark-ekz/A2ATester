from __future__ import annotations

import uuid
from typing import Any


def new_jsonrpc_id() -> str:
    return str(uuid.uuid4())


def build_message_request(
    *,
    method: str,
    text: str,
    context_id: str = "",
    task_id: str = "",
    metadata: dict[str, Any] | None = None,
    jsonrpc_id: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "kind": "message",
        "role": "user",
        "messageId": str(uuid.uuid4()),
        "parts": [
            {
                "kind": "text",
                "text": text,
            }
        ],
    }
    if context_id:
        message["contextId"] = context_id
    if task_id:
        message["taskId"] = task_id

    params: dict[str, Any] = {"message": message}
    if metadata:
        params["metadata"] = metadata

    return {
        "jsonrpc": "2.0",
        "id": jsonrpc_id or new_jsonrpc_id(),
        "method": method,
        "params": params,
    }


def build_task_request(*, method: str, task_id: str, jsonrpc_id: str | None = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": jsonrpc_id or new_jsonrpc_id(),
        "method": method,
        "params": {"id": task_id},
    }
