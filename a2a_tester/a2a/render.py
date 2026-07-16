from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RenderItem:
    role: str
    kind: str
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    context_id: str = ""
    artifact_name: str = ""
    artifact_mime_type: str = ""
    artifact_json: Any | None = None


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def parts_to_text(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""

    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            chunks.append(str(part))
            continue

        if "text" in part:
            chunks.append(str(part.get("text", "")))
            continue

        if "data" in part:
            chunks.append(pretty_json(part.get("data")))
            continue

        if "url" in part:
            label = str(part.get("filename") or part.get("url") or "file")
            media_type = str(part.get("mediaType") or part.get("mimeType") or "")
            chunks.append(f"[Файл: {label}]({part['url']}) {media_type}".strip())
            continue

        if "raw" in part:
            label = str(part.get("filename") or "file")
            media_type = str(part.get("mediaType") or part.get("mimeType") or "")
            size = len(str(part.get("raw") or ""))
            chunks.append(f"[Файл: {label}] {media_type} (base64, {size} символов)".strip())
            continue

        if "file" in part:
            file_obj = part.get("file") or {}
            if isinstance(file_obj, dict):
                name = file_obj.get("name") or file_obj.get("uri") or file_obj.get("fileWithUri") or "file"
                mime_type = file_obj.get("mimeType") or file_obj.get("mime_type") or ""
                chunks.append(f"[Файл] {name} {mime_type}".strip())
            else:
                chunks.append("[Файл]")
            continue

        chunks.append(pretty_json(part))

    return "\n\n".join(chunk for chunk in chunks if chunk)


def extract_context_id(value: Any) -> str:
    if isinstance(value, dict):
        context_id = value.get("contextId") or value.get("context_id") or ""
        if context_id:
            return str(context_id)
        for child in value.values():
            found = extract_context_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = extract_context_id(child)
            if found:
                return found
    return ""


def extract_task_id(value: Any) -> str:
    if isinstance(value, dict):
        task_id = value.get("taskId") or value.get("task_id") or ""
        if task_id:
            return str(task_id)
        if value.get("id") and _looks_like_task_container(value):
            return str(value["id"])
        for child in value.values():
            found = extract_task_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = extract_task_id(child)
            if found:
                return found
    return ""


def extract_render_items(envelope: dict[str, Any]) -> list[RenderItem]:
    if "error" in envelope and envelope["error"]:
        error = envelope["error"]
        text = pretty_json(error) if isinstance(error, (dict, list)) else str(error)
        return [RenderItem(role="system", kind="error", text=text, raw=envelope)]

    payload = envelope.get("result", envelope)
    items: list[RenderItem] = []
    _walk(payload, items)

    if not items and payload:
        items.append(
            RenderItem(
                role="system",
                kind="debug",
                text=pretty_json(payload),
                raw=envelope,
                context_id=extract_context_id(payload),
                task_id=extract_task_id(payload),
            )
        )
    return items


def _walk(value: Any, items: list[RenderItem]) -> None:
    if isinstance(value, list):
        for child in value:
            _walk(child, items)
        return

    if not isinstance(value, dict):
        return

    context_id = str(value.get("contextId") or value.get("context_id") or "")
    task_id = str(value.get("taskId") or value.get("task_id") or extract_task_id(value))

    if "role" in value and "parts" in value:
        _message_to_item(value, items, fallback_task_id=task_id, fallback_context_id=context_id)
        return

    if _is_task_snapshot(value):
        _task_snapshot_to_items(value, items, task_id=task_id, context_id=context_id)
        return

    for key, child in value.items():
        if key == "task" and isinstance(child, dict):
            _task_snapshot_to_items(child, items, task_id=extract_task_id(child), context_id=extract_context_id(child))
            continue

        if key == "message" and isinstance(child, dict):
            _message_to_item(child, items, fallback_task_id=task_id, fallback_context_id=context_id)
            continue

        if key in {"statusUpdate", "status_update", "taskStatusUpdate", "task_status_update"} and isinstance(child, dict):
            _status_to_item(
                child.get("status") if isinstance(child.get("status"), dict) else child,
                items,
                raw=child,
                task_id=str(child.get("taskId") or child.get("task_id") or task_id),
                context_id=str(child.get("contextId") or child.get("context_id") or context_id),
            )
            continue

        if key in {"artifactUpdate", "artifact_update", "taskArtifactUpdate", "task_artifact_update"} and isinstance(child, dict):
            artifact = child.get("artifact")
            if isinstance(artifact, dict):
                _artifact_to_item(
                    artifact,
                    items,
                    task_id=str(child.get("taskId") or child.get("task_id") or task_id),
                    context_id=str(child.get("contextId") or child.get("context_id") or context_id),
                )
            continue

        if key == "status" and isinstance(child, dict):
            _status_to_item(child, items, raw=value, task_id=task_id, context_id=context_id)
            continue

        if key == "artifact" and isinstance(child, dict):
            _artifact_to_item(child, items, task_id=task_id, context_id=context_id)
            continue

        if key == "artifacts" and isinstance(child, list):
            for artifact in child:
                if isinstance(artifact, dict):
                    _artifact_to_item(artifact, items, task_id=task_id, context_id=context_id)
            continue

        if key in {"messages", "history", "result", "data"} and isinstance(child, (dict, list)):
            _walk(child, items)


def _looks_like_task_container(value: dict[str, Any]) -> bool:
    kind = str(value.get("kind") or "").lower()
    return (
        "status" in value
        or "artifact" in value
        or "artifacts" in value
        or "history" in value
        or kind in {"task", "status-update", "artifact-update", "taskstatusupdateevent", "taskartifactupdateevent"}
    )


def _is_task_snapshot(value: dict[str, Any]) -> bool:
    return str(value.get("kind") or "").lower() == "task" or (
        bool(value.get("id")) and isinstance(value.get("status"), dict) and "role" not in value
    )


def _task_snapshot_to_items(
    task: dict[str, Any],
    items: list[RenderItem],
    *,
    task_id: str = "",
    context_id: str = "",
) -> None:
    resolved_task_id = str(task.get("id") or task.get("taskId") or task_id)
    resolved_context_id = str(task.get("contextId") or task.get("context_id") or context_id)

    history = task.get("history")
    if isinstance(history, list):
        for message in history:
            if isinstance(message, dict) and "role" in message and "parts" in message:
                _message_to_item(
                    message,
                    items,
                    fallback_task_id=resolved_task_id,
                    fallback_context_id=resolved_context_id,
                )
            else:
                _walk(message, items)

    artifacts = task.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                _artifact_to_item(artifact, items, task_id=resolved_task_id, context_id=resolved_context_id)

    status = task.get("status")
    if isinstance(status, dict):
        _status_to_item(status, items, raw=task, task_id=resolved_task_id, context_id=resolved_context_id)


def _status_to_item(
    status: dict[str, Any],
    items: list[RenderItem],
    *,
    raw: dict[str, Any],
    task_id: str = "",
    context_id: str = "",
) -> None:
    message = status.get("message")
    if isinstance(message, dict):
        _message_to_item(message, items, fallback_task_id=task_id, fallback_context_id=context_id)

    if status.get("state") is not None or not isinstance(message, dict):
        items.append(_status_render_item(status, raw=raw, task_id=task_id, context_id=context_id))


def _status_render_item(
    status: dict[str, Any],
    *,
    raw: dict[str, Any],
    task_id: str = "",
    context_id: str = "",
) -> RenderItem:
    state = str(status.get("state", "unknown"))
    return RenderItem(
        role="system",
        kind="status",
        text=f"Task status: {state}",
        raw=_status_raw(status, raw),
        task_id=task_id or extract_task_id(raw),
        context_id=context_id or extract_context_id(raw),
    )


def _status_raw(status: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    status_payload = {key: value for key, value in status.items() if key != "message"}
    payload: dict[str, Any] = {"status": status_payload}
    for key in ("id", "kind", "taskId", "task_id", "contextId", "context_id", "final", "index"):
        if key in raw:
            payload[key] = raw[key]
    return payload


def _message_to_item(
    message: dict[str, Any],
    items: list[RenderItem],
    *,
    fallback_task_id: str = "",
    fallback_context_id: str = "",
) -> None:
    text = parts_to_text(message.get("parts"))
    if not text:
        text = pretty_json(message)
    items.append(
        RenderItem(
            role=_normalize_role(message.get("role")),
            kind="message",
            text=text,
            raw=message,
            task_id=str(message.get("taskId") or message.get("task_id") or fallback_task_id),
            context_id=str(message.get("contextId") or message.get("context_id") or fallback_context_id),
        )
    )


def _normalize_role(value: Any) -> str:
    role = str(value or "agent").lower()
    if role in {"user", "role_user"}:
        return "user"
    if role in {"agent", "role_agent"}:
        return "agent"
    return role


def _artifact_to_item(
    artifact: dict[str, Any],
    items: list[RenderItem],
    *,
    task_id: str = "",
    context_id: str = "",
) -> None:
    text = parts_to_text(artifact.get("parts"))
    if not text:
        text = pretty_json(artifact)
    name = str(artifact.get("name") or artifact.get("artifactId") or artifact.get("artifact_id") or "Artifact")
    mime_type = str(artifact.get("mimeType") or artifact.get("mediaType") or artifact.get("mime_type") or "")
    items.append(
        RenderItem(
            role="agent",
            kind="artifact",
            text=text,
            raw=artifact,
            task_id=str(artifact.get("taskId") or artifact.get("task_id") or task_id),
            context_id=str(artifact.get("contextId") or artifact.get("context_id") or context_id),
            artifact_name=name,
            artifact_mime_type=mime_type,
            artifact_json=artifact,
        )
    )
