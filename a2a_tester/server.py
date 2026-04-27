from __future__ import annotations

import json
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from a2a_tester.a2a.client import A2ARequestConfig, HttpExchange, fetch_agent_card, post_json_rpc, stream_json_rpc
from a2a_tester.a2a.jsonrpc import build_message_request, build_task_request
from a2a_tester.a2a.render import RenderItem, extract_context_id, extract_render_items, pretty_json
from a2a_tester.storage.database import Database, Profile, loads


SECRET_HEADER_NAMES = {"authorization", "cookie", "x-api-key", "api-key", "proxy-authorization"}
INPUT_REQUIRED_STATES = {"input-required", "input_required"}
CERTIFICATE_UPLOAD_LIMIT_BYTES = 2 * 1024 * 1024


def frontend_dir() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        candidate = Path(bundled_root) / "a2a_tester" / "frontend"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent / "frontend"


def create_app(db: Database, data_dir: Path) -> FastAPI:
    app = FastAPI(title="A2A Tester")
    static_dir = frontend_dir()
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        profile = ensure_profile(db)
        conversation_id = ensure_conversation(db, profile.id)
        return {
            "profiles": profile_list(db),
            "selectedProfileId": profile.id,
            "conversations": conversation_list(db, profile.id),
            "selectedConversationId": conversation_id,
            "profile": profile_payload(profile),
            "conversation": conversation_payload(db, conversation_id),
            "theme": db.get_setting("theme", "studio"),
            "palettes": palettes(),
        }

    @app.post("/api/settings/theme")
    async def set_theme(payload: dict[str, Any]) -> dict[str, Any]:
        key = str(payload.get("theme") or "studio")
        db.set_setting("theme", key)
        return {"theme": key}

    @app.post("/api/profiles")
    async def create_profile(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or f"Connection {time.strftime('%Y-%m-%d %H:%M')}")
        profile_id = db.create_profile(name, "http://localhost:8000", {}, {})
        conversation_id = db.create_conversation(profile_id, default_chat_title(), context_id=new_context_id())
        profile = db.get_profile(profile_id)
        return {
            "profiles": profile_list(db),
            "selectedProfileId": profile_id,
            "conversations": conversation_list(db, profile_id),
            "selectedConversationId": conversation_id,
            "profile": profile_payload(profile),
            "conversation": conversation_payload(db, conversation_id),
        }

    @app.get("/api/profiles/{profile_id}")
    def get_profile(profile_id: int) -> dict[str, Any]:
        profile = db.get_profile(profile_id)
        conversation_id = ensure_conversation(db, profile_id)
        return {
            "profile": profile_payload(profile),
            "conversations": conversation_list(db, profile_id),
            "selectedConversationId": conversation_id,
            "conversation": conversation_payload(db, conversation_id),
        }

    @app.put("/api/profiles/{profile_id}")
    async def update_profile(profile_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        profile = db.get_profile(profile_id)
        metadata = parse_metadata(payload.get("metadataJson", profile.metadata_json))
        ca_bundle_path = str(payload.get("caBundlePath") or "")
        client_cert_path = str(payload.get("clientCertPath") or "")
        client_key_path = str(payload.get("clientKeyPath") or "")
        validate_certificate_paths(ca_bundle_path, client_cert_path, client_key_path)
        db.update_profile(
            profile_id,
            name=str(payload.get("name") or profile.name),
            endpoint=str(payload.get("endpoint") or ""),
            headers_json=pretty_json(headers_to_storage(payload.get("headers") or [])),
            metadata_json=pretty_json(metadata),
            tls_verify=bool(payload.get("tlsVerify", True)),
            ca_bundle_path=ca_bundle_path,
            client_cert_path=client_cert_path,
            client_key_path=client_key_path,
            timeout_seconds=float(payload.get("timeoutSeconds") or 60),
            protocol_version=str(payload.get("protocolVersion") or "1.0"),
        )
        return {"profile": profile_payload(db.get_profile(profile_id)), "profiles": profile_list(db)}

    @app.post("/api/profiles/{profile_id}/certificates/{field_name}")
    async def upload_certificate(profile_id: int, field_name: str, file: UploadFile = File(...)) -> dict[str, Any]:
        if field_name not in {"ca_bundle_path", "client_cert_path", "client_key_path"}:
            raise HTTPException(status_code=400, detail="Unknown certificate field")
        profile = db.get_profile(profile_id)
        cert_dir = data_dir / "certificates" / f"profile_{profile_id}"
        cert_dir.mkdir(parents=True, exist_ok=True)
        source_name = Path(file.filename or field_name)
        destination = cert_dir / f"{field_name}{source_name.suffix}"
        contents = await file.read()
        validate_certificate_upload(field_name, source_name.name, contents)
        with destination.open("wb") as handle:
            handle.write(contents)

        values = {
            "ca_bundle_path": profile.ca_bundle_path,
            "client_cert_path": profile.client_cert_path,
            "client_key_path": profile.client_key_path,
        }
        values[field_name] = str(destination)
        db.update_profile(
            profile_id,
            name=profile.name,
            endpoint=profile.endpoint,
            headers_json=profile.headers_json,
            metadata_json=profile.metadata_json,
            tls_verify=profile.tls_verify,
            ca_bundle_path=values["ca_bundle_path"],
            client_cert_path=values["client_cert_path"],
            client_key_path=values["client_key_path"],
            timeout_seconds=profile.timeout_seconds,
            protocol_version=profile.protocol_version,
        )
        return {"path": str(destination), "profile": profile_payload(db.get_profile(profile_id))}

    @app.post("/api/conversations")
    async def create_conversation(payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = int(payload.get("profileId") or 0)
        if not profile_id:
            raise HTTPException(status_code=400, detail="profileId is required")
        conversation_id = db.create_conversation(profile_id, default_chat_title(), context_id=new_context_id())
        return {
            "conversations": conversation_list(db, profile_id),
            "selectedConversationId": conversation_id,
            "conversation": conversation_payload(db, conversation_id),
        }

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: int) -> dict[str, Any]:
        conversation = db.get_conversation(conversation_id)
        if not conversation.context_id:
            db.update_conversation_context(conversation_id, new_context_id())
        return {"conversation": conversation_payload(db, conversation_id)}

    @app.post("/api/messages/send")
    async def send_message(payload: dict[str, Any]) -> dict[str, Any]:
        profile_id, conversation_id, text = request_ids_and_text(payload)
        profile = db.get_profile(profile_id)
        conversation = ensure_conversation_context(db, conversation_id)
        request_json = build_message_request(
            method="message/send",
            text=text,
            context_id=conversation.context_id,
            task_id=continuation_task_for_input_required(db, conversation_id),
            metadata=parse_metadata(profile.metadata_json),
        )
        db.add_message(conversation_id=conversation_id, role="user", kind="message", text=text, raw_json=request_json["params"]["message"])
        exchange = post_json_rpc(profile_config(profile), request_json)
        persist_exchange(db, conversation_id, profile_id, exchange, "message/send")
        if exchange.response_json:
            persist_payload(db, conversation_id, exchange.response_json)
        return refreshed(db, profile_id, conversation_id, status_after_send(db, conversation_id, "Request completed"))

    @app.post("/api/messages/stream")
    async def stream_message(payload: dict[str, Any]) -> StreamingResponse:
        profile_id, conversation_id, text = request_ids_and_text(payload)
        profile = db.get_profile(profile_id)
        conversation = ensure_conversation_context(db, conversation_id)
        request_json = build_message_request(
            method="message/stream",
            text=text,
            context_id=conversation.context_id,
            task_id=continuation_task_for_input_required(db, conversation_id),
            metadata=parse_metadata(profile.metadata_json),
        )
        db.add_message(conversation_id=conversation_id, role="user", kind="message", text=text, raw_json=request_json["params"]["message"])

        def events():
            yield sse({"type": "state", **refreshed(db, profile_id, conversation_id, "Streaming...")})
            try:
                for item in stream_json_rpc(profile_config(profile), request_json):
                    if item.get("type") == "headers":
                        db.add_http_event(
                            conversation_id=conversation_id,
                            profile_id=profile_id,
                            jsonrpc_id=str(request_json.get("id", "")),
                            method="message/stream",
                            request_json=request_json,
                            response_json={"stream": "opened"},
                            response_headers_json=item.get("headers", {}),
                            status_code=item.get("status_code"),
                            latency_ms=item.get("latency_ms"),
                        )
                    else:
                        payload = item.get("payload", {})
                        db.add_http_event(
                            conversation_id=conversation_id,
                            profile_id=profile_id,
                            jsonrpc_id=str(request_json.get("id", "")),
                            method="message/stream",
                            request_json={},
                            response_json=item,
                            response_headers_json={},
                        )
                        persist_payload(db, conversation_id, payload)
                    yield sse({"type": "state", **refreshed(db, profile_id, conversation_id, "Streaming...")})
            except Exception as exc:
                db.add_http_event(
                    conversation_id=conversation_id,
                    profile_id=profile_id,
                    jsonrpc_id=str(request_json.get("id", "")),
                    method="message/stream",
                    request_json=request_json,
                    error=str(exc),
                )
                db.add_message(conversation_id=conversation_id, role="system", kind="error", text=str(exc), raw_json={})
                yield sse({"type": "state", **refreshed(db, profile_id, conversation_id, f"Stream error: {exc}")})
                return
            yield sse({"type": "state", **refreshed(db, profile_id, conversation_id, status_after_send(db, conversation_id, "Stream completed"))})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/tasks/{method_name}")
    async def task_request(method_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        method_map = {"get": "tasks/get", "cancel": "tasks/cancel"}
        method = method_map.get(method_name)
        if not method:
            raise HTTPException(status_code=404, detail="Unknown task method")
        profile_id = int(payload.get("profileId") or 0)
        conversation_id = int(payload.get("conversationId") or 0)
        task_id = str(payload.get("taskId") or "").strip()
        if not task_id:
            raise HTTPException(status_code=400, detail="taskId is required")
        profile = db.get_profile(profile_id)
        request_json = build_task_request(method=method, task_id=task_id)
        exchange = post_json_rpc(profile_config(profile), request_json)
        persist_exchange(db, conversation_id, profile_id, exchange, method)
        if exchange.response_json:
            persist_payload(db, conversation_id, exchange.response_json)
        return refreshed(db, profile_id, conversation_id, f"{method} completed")

    @app.post("/api/agent-card")
    async def agent_card(payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = int(payload.get("profileId") or 0)
        conversation_id = int(payload.get("conversationId") or 0)
        profile = db.get_profile(profile_id)
        exchange = fetch_agent_card(profile_config(profile))
        persist_exchange(db, conversation_id, profile_id, exchange, "agent-card")
        return {
            "agentCard": exchange.response_json if not exchange.error else {"error": exchange.error},
            "conversation": conversation_payload(db, conversation_id) if conversation_id else None,
            "status": "Agent Card loaded" if not exchange.error else f"Agent Card error: {exchange.error}",
        }

    return app


def run_desktop_app(app: FastAPI, host: str, port: int, *, no_browser: bool = False) -> None:
    port = find_available_port(host, port)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for_server(host, port)
    url = f"http://{host}:{port}"

    if no_browser:
        print(f"A2A Tester running at {url}")
        try:
            while thread.is_alive():
                time.sleep(0.25)
        except KeyboardInterrupt:
            server.should_exit = True
            thread.join(timeout=3)
        return

    try:
        import webview

        window = webview.create_window("A2A Tester", url, width=1320, height=900, min_size=(980, 700))
        webview.start()
    except Exception:
        webbrowser.open(url)
        try:
            while thread.is_alive():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
    finally:
        server.should_exit = True
        thread.join(timeout=3)


def ensure_profile(db: Database) -> Profile:
    db.ensure_default_profile()
    return db.list_profiles()[0]


def ensure_conversation(db: Database, profile_id: int) -> int:
    conversations = db.list_conversations(profile_id)
    if conversations:
        conversation = conversations[0]
        if not conversation.context_id:
            db.update_conversation_context(conversation.id, new_context_id())
        return conversation.id
    return db.create_conversation(profile_id, default_chat_title(), context_id=new_context_id())


def ensure_conversation_context(db: Database, conversation_id: int):
    conversation = db.get_conversation(conversation_id)
    if conversation.context_id:
        return conversation
    db.update_conversation_context(conversation_id, new_context_id())
    return db.get_conversation(conversation_id)


def profile_payload(profile: Profile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "endpoint": profile.endpoint,
        "headers": headers_records(loads(profile.headers_json, {})),
        "metadataJson": profile.metadata_json,
        "tlsVerify": profile.tls_verify,
        "caBundlePath": profile.ca_bundle_path,
        "clientCertPath": profile.client_cert_path,
        "clientKeyPath": profile.client_key_path,
        "timeoutSeconds": profile.timeout_seconds,
        "protocolVersion": profile.protocol_version,
    }


def profile_list(db: Database) -> list[dict[str, Any]]:
    return [profile_payload(profile) for profile in db.list_profiles()]


def conversation_list(db: Database, profile_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": conversation.id,
            "profileId": conversation.profile_id,
            "title": conversation.title,
            "contextId": conversation.context_id,
            "createdAt": conversation.created_at,
            "updatedAt": conversation.updated_at,
        }
        for conversation in db.list_conversations(profile_id)
    ]


def conversation_payload(db: Database, conversation_id: int) -> dict[str, Any]:
    conversation = db.get_conversation(conversation_id)
    return {
        "id": conversation.id,
        "profileId": conversation.profile_id,
        "title": conversation.title,
        "contextId": conversation.context_id,
        "taskId": latest_task_id(db, conversation_id),
        "taskState": latest_task_state(db, conversation_id),
        "messages": messages_payload(db, conversation_id),
        "diagnostics": diagnostics_payload(db, conversation_id),
        "inputRequired": is_input_required(db, conversation_id),
    }


def messages_payload(db: Database, conversation_id: int) -> list[dict[str, Any]]:
    http_events = db.list_http_events(conversation_id)
    if http_events:
        return messages_payload_from_http_events(db, conversation_id, http_events)
    return stored_messages_payload(db, conversation_id)


def stored_messages_payload(db: Database, conversation_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "kind": row["kind"],
            "text": row["text"],
            "taskId": row["task_id"],
            "raw": loads(row["raw_json"], {}),
            "createdAt": row["created_at"],
        }
        for row in db.list_messages(conversation_id)
    ]


def messages_payload_from_http_events(db: Database, conversation_id: int, http_events: list[Any]) -> list[dict[str, Any]]:
    user_messages = [row for row in db.list_messages(conversation_id) if row["role"] == "user"]
    user_by_message_id = {
        str(raw.get("messageId")): row
        for row in user_messages
        for raw in [loads(row["raw_json"], {})]
        if isinstance(raw, dict) and raw.get("messageId")
    }
    emitted_user_ids: set[int] = set()
    emitted_render_items: set[str] = set()
    payload: list[dict[str, Any]] = []

    for event in http_events:
        request_json = loads(event["request_json"], {})
        request_message = request_json.get("params", {}).get("message") if isinstance(request_json, dict) else None
        if isinstance(request_message, dict):
            row = user_by_message_id.get(str(request_message.get("messageId") or ""))
            if row is not None and row["id"] not in emitted_user_ids:
                payload.append(message_row_payload(row))
                emitted_user_ids.add(row["id"])
            elif row is None:
                payload.append(render_item_payload(
                    f"request-{event['id']}",
                    RenderItem(
                        role="user",
                        kind="message",
                        text=parts_to_text_for_payload(request_message),
                        raw=request_message,
                        task_id=str(request_message.get("taskId") or ""),
                    ),
                    event["created_at"],
                ))

        if event["error"]:
            payload.append({
                "id": f"error-{event['id']}",
                "role": "system",
                "kind": "error",
                "text": event["error"],
                "taskId": "",
                "raw": loads(event["response_json"], {}),
                "createdAt": event["created_at"],
            })

        response_json = loads(event["response_json"], {})
        render_source = event_render_source(response_json)
        if render_source is None:
            continue

        for item_index, item in enumerate(extract_render_items(render_source)):
            if item.kind == "message" and item.role == "user":
                continue
            item_key = render_item_key(item)
            if item_key in emitted_render_items:
                continue
            emitted_render_items.add(item_key)
            payload.append(render_item_payload(f"http-{event['id']}-{item_index}", item, event["created_at"]))

    for row in user_messages:
        if row["id"] not in emitted_user_ids:
            payload.append(message_row_payload(row))

    return payload


def event_render_source(response_json: Any) -> dict[str, Any] | None:
    if not isinstance(response_json, dict) or response_json.get("stream") == "opened":
        return None
    if response_json.get("type") == "event" and isinstance(response_json.get("payload"), dict):
        return response_json["payload"]
    return response_json


def message_row_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role": row["role"],
        "kind": row["kind"],
        "text": row["text"],
        "taskId": row["task_id"],
        "raw": loads(row["raw_json"], {}),
        "createdAt": row["created_at"],
    }


def render_item_payload(item_id: str, item: RenderItem, created_at: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "role": item.role,
        "kind": item.kind,
        "text": item.text,
        "taskId": item.task_id,
        "raw": item.raw,
        "createdAt": created_at,
    }


def render_item_key(item: RenderItem) -> str:
    return "|".join([
        item.role,
        item.kind,
        item.task_id,
        json.dumps(item.raw, ensure_ascii=False, sort_keys=True),
    ])


def parts_to_text_for_payload(message: dict[str, Any]) -> str:
    for item in extract_render_items(message):
        if item.kind == "message":
            return item.text
    return pretty_json(message)


def diagnostics_payload(db: Database, conversation_id: int) -> list[dict[str, Any]]:
    return [
        {
            "createdAt": event["created_at"],
            "method": event["method"],
            "jsonrpcId": event["jsonrpc_id"],
            "statusCode": event["status_code"],
            "latencyMs": event["latency_ms"],
            "request": loads(event["request_json"], {}),
            "response": loads(event["response_json"], {}),
            "responseHeaders": redact_headers(loads(event["response_headers_json"], {})),
            "error": event["error"],
        }
        for event in db.list_http_events(conversation_id)
    ]


def refreshed(db: Database, profile_id: int, conversation_id: int, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "conversations": conversation_list(db, profile_id),
        "conversation": conversation_payload(db, conversation_id),
    }


def profile_config(profile: Profile) -> A2ARequestConfig:
    return A2ARequestConfig(
        endpoint=profile.endpoint,
        headers=active_headers(loads(profile.headers_json, {})),
        tls_verify=profile.tls_verify,
        ca_bundle_path=profile.ca_bundle_path,
        client_cert_path=profile.client_cert_path,
        client_key_path=profile.client_key_path,
        timeout_seconds=profile.timeout_seconds,
    )


def request_ids_and_text(payload: dict[str, Any]) -> tuple[int, int, str]:
    profile_id = int(payload.get("profileId") or 0)
    conversation_id = int(payload.get("conversationId") or 0)
    text = str(payload.get("text") or "").strip()
    if not profile_id or not conversation_id:
        raise HTTPException(status_code=400, detail="profileId and conversationId are required")
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    return profile_id, conversation_id, text


def persist_exchange(db: Database, conversation_id: int | None, profile_id: int | None, exchange: HttpExchange, method: str) -> None:
    request_id = str(exchange.request_json.get("id", "")) if isinstance(exchange.request_json, dict) else ""
    db.add_http_event(
        conversation_id=conversation_id,
        profile_id=profile_id,
        jsonrpc_id=request_id,
        method=method,
        request_json=exchange.request_json,
        response_json=exchange.response_json,
        response_headers_json=redact_headers(exchange.response_headers),
        status_code=exchange.status_code,
        latency_ms=exchange.latency_ms,
        error=exchange.error,
    )
    if conversation_id is not None and exchange.error:
        db.add_message(conversation_id=conversation_id, role="system", kind="error", text=exchange.error, raw_json=exchange.response_json)


def persist_payload(db: Database, conversation_id: int, payload: dict[str, Any]) -> None:
    context_id = extract_context_id(payload)
    if context_id:
        db.update_conversation_context(conversation_id, context_id)
    for item in extract_render_items(payload):
        persist_render_item(db, conversation_id, item)


def persist_render_item(db: Database, conversation_id: int, item: RenderItem) -> None:
    if item.context_id:
        db.update_conversation_context(conversation_id, item.context_id)
    if should_skip_render_item(db, conversation_id, item):
        return
    db.add_message(
        conversation_id=conversation_id,
        role=item.role,
        kind=item.kind,
        text=item.text,
        raw_json=item.raw,
        task_id=item.task_id,
    )
    if item.kind == "artifact":
        db.add_artifact(
            conversation_id=conversation_id,
            task_id=item.task_id,
            name=item.artifact_name,
            mime_type=item.artifact_mime_type,
            content_text=item.text,
            content_json=item.artifact_json,
            raw_json=item.raw,
        )


def should_skip_render_item(db: Database, conversation_id: int, item: RenderItem) -> bool:
    if item.kind == "message" and item.role == "user":
        return True
    return db.message_exists(
        conversation_id=conversation_id,
        role=item.role,
        kind=item.kind,
        task_id=item.task_id,
        raw_json=item.raw,
    )


def headers_records(headers: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(headers, dict):
        iterable = headers.items()
    elif isinstance(headers, list):
        iterable = [(item.get("name") or item.get("header") or item.get("key") or "", item) for item in headers if isinstance(item, dict)]
    else:
        iterable = []
    for key, value in iterable:
        name = str(key or "").strip()
        if not name:
            continue
        if isinstance(value, dict):
            cell_value = str(value.get("value") or "")
            enabled = bool(value.get("enabled", True))
            secret = bool(value.get("secret", is_secret_header(name)))
        else:
            cell_value = str(value)
            enabled = True
            secret = is_secret_header(name)
        records.append({"name": name, "value": cell_value, "enabled": enabled, "secret": secret})
    return records


def headers_to_storage(records: Any) -> dict[str, dict[str, Any]]:
    return {
        record["name"]: {
            "enabled": bool(record.get("enabled", True)),
            "value": str(record.get("value") or ""),
            "secret": bool(record.get("secret", is_secret_header(record["name"]))),
        }
        for record in headers_records(records)
    }


def active_headers(records: Any) -> dict[str, str]:
    return {record["name"]: str(record.get("value") or "") for record in headers_records(records) if bool(record.get("enabled", True))}


def parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Metadata must be a JSON object")
    return parsed


def validate_certificate_paths(ca_bundle_path: str, client_cert_path: str, client_key_path: str) -> None:
    if client_key_path and not client_cert_path:
        raise HTTPException(status_code=400, detail="Client certificate is required when client key is configured")

    for field_name, path in {
        "ca_bundle_path": ca_bundle_path,
        "client_cert_path": client_cert_path,
        "client_key_path": client_key_path,
    }.items():
        if not path:
            continue
        path_obj = Path(path).expanduser()
        if not path_obj.exists():
            raise HTTPException(status_code=400, detail=f"{certificate_label(field_name)} not found: {path_obj}")
        if not path_obj.is_file():
            raise HTTPException(status_code=400, detail=f"{certificate_label(field_name)} is not a file: {path_obj}")
        validate_certificate_upload(field_name, path_obj.name, path_obj.read_bytes())


def validate_certificate_upload(field_name: str, filename: str, contents: bytes) -> None:
    if not contents:
        raise HTTPException(status_code=400, detail=f"{certificate_label(field_name)} file is empty")
    if len(contents) > CERTIFICATE_UPLOAD_LIMIT_BYTES:
        raise HTTPException(status_code=400, detail=f"{certificate_label(field_name)} is too large")

    if field_name in {"ca_bundle_path", "client_cert_path"}:
        if b"-----BEGIN CERTIFICATE-----" not in contents:
            raise HTTPException(
                status_code=400,
                detail=f"{certificate_label(field_name)} must be a PEM certificate file with BEGIN CERTIFICATE: {filename}",
            )
        return

    if field_name == "client_key_path" and b"PRIVATE KEY-----" not in contents:
        raise HTTPException(
            status_code=400,
            detail=f"{certificate_label(field_name)} must be a PEM private key file: {filename}",
        )


def certificate_label(field_name: str) -> str:
    return {
        "ca_bundle_path": "CA bundle",
        "client_cert_path": "Client certificate",
        "client_key_path": "Client key",
    }.get(field_name, "Certificate")


def latest_task_id(db: Database, conversation_id: int | None) -> str:
    if conversation_id is None:
        return ""
    for row in reversed(db.list_messages(conversation_id)):
        if row["task_id"]:
            return str(row["task_id"])
    return ""


def latest_task_state(db: Database, conversation_id: int | None) -> str:
    if conversation_id is None:
        return ""
    for row in reversed(db.list_messages(conversation_id)):
        state = extract_status_state(loads(row["raw_json"], {}))
        if state:
            return state
    return ""


def extract_status_state(value: Any) -> str:
    if isinstance(value, dict):
        status = value.get("status")
        if isinstance(status, dict) and status.get("state"):
            return str(status["state"])
        if value.get("state") and ("message" in value or "timestamp" in value):
            return str(value["state"])
        for child in value.values():
            found = extract_status_state(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = extract_status_state(child)
            if found:
                return found
    return ""


def is_input_required(db: Database, conversation_id: int | None) -> bool:
    return latest_task_state(db, conversation_id).lower() in INPUT_REQUIRED_STATES


def continuation_task_for_input_required(db: Database, conversation_id: int | None) -> str:
    return latest_task_id(db, conversation_id) if is_input_required(db, conversation_id) else ""


def status_after_send(db: Database, conversation_id: int, fallback: str) -> str:
    if is_input_required(db, conversation_id):
        task_id = latest_task_id(db, conversation_id)
        suffix = f" {task_id}" if task_id else ""
        return f"Input required for task{suffix}"
    return fallback


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    return {key: "***" if key.lower() in SECRET_HEADER_NAMES else value for key, value in headers.items()}


def is_secret_header(name: str) -> bool:
    return name.lower() in SECRET_HEADER_NAMES


def default_chat_title() -> str:
    return "Chat " + time.strftime("%Y-%m-%d %H:%M")


def new_context_id() -> str:
    import uuid

    return str(uuid.uuid4())


def palettes() -> list[dict[str, str]]:
    return [
        {"key": "studio", "name": "Studio"},
        {"key": "graphite", "name": "Graphite"},
        {"key": "harbor", "name": "Harbor"},
    ]


def sse(payload: dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def find_available_port(host: str, preferred_port: int) -> int:
    for port in [preferred_port, *range(preferred_port + 1, preferred_port + 30)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available port found")


def wait_for_server(host: str, port: int, timeout: float = 10) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.connect((host, port))
                return
            except OSError:
                time.sleep(0.05)
    raise RuntimeError("Server did not start")
