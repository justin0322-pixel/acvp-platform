"""ACVP paged responses (spec 12.5.2).

totalCount / incomplete / links{first,next,prev,last} / data. Shared by every
resource listing, so the shape stays identical across them.
"""
from typing import Any

DEFAULT_LIMIT = 20


def paged(resource: str, items: list[Any], *, offset: int = 0, limit: int = DEFAULT_LIMIT) -> dict:
    offset, limit = max(0, offset), max(1, limit)
    total = len(items)
    page = items[offset : offset + limit]

    def link(o: int) -> str:
        return f"/acvp/v1/{resource}?offset={o}&limit={limit}"

    last = ((total - 1) // limit) * limit if total else 0
    return {
        "totalCount": total,
        "incomplete": offset + len(page) < total,
        "links": {
            "first": link(0),
            "next": link(offset + limit) if offset + limit < total else None,
            "prev": link(max(0, offset - limit)) if offset > 0 else None,
            "last": link(last),
        },
        "data": page,
    }
