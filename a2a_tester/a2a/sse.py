from __future__ import annotations

from collections.abc import Iterable, Iterator


def parse_sse_lines(lines: Iterable[str]) -> Iterator[dict[str, str]]:
    event: dict[str, list[str] | str] = {"data": []}

    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            data = event.get("data", [])
            if data:
                yield {
                    "event": str(event.get("event", "message")),
                    "id": str(event.get("id", "")),
                    "data": "\n".join(data if isinstance(data, list) else [str(data)]),
                }
            event = {"data": []}
            continue

        if line.startswith(":"):
            continue

        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]

        if field == "data":
            data = event.setdefault("data", [])
            if isinstance(data, list):
                data.append(value)
        elif field in {"event", "id"}:
            event[field] = value

    data = event.get("data", [])
    if data:
        yield {
            "event": str(event.get("event", "message")),
            "id": str(event.get("id", "")),
            "data": "\n".join(data if isinstance(data, list) else [str(data)]),
        }
