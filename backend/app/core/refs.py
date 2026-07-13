"""Resolving `/acvp/v1/...` references to the metadata resources they name.

Certification binds a test session to a module and an operating environment by URL.
If those URLs are never checked, the server will happily issue a certificate that
points at nothing — which is the same as issuing a certificate that says nothing.
Every inbound reference goes through here. [HUMAN REVIEW]
"""
import re

from app.store import store

_RESOURCE = re.compile(r"^/acvp/v1/(vendors|persons|modules|oes|dependencies)/(\d+)$")
_ADDRESS = re.compile(r"^/acvp/v1/vendors/(\d+)/addresses/(\d+)$")


def exists(url: str, *, resource: str | None = None) -> bool:
    """True when `url` names a metadata resource that is actually there.

    `resource` pins the expected kind, so an oeUrl cannot be satisfied by handing
    us a module URL.
    """
    if not isinstance(url, str):
        return False

    match = _RESOURCE.match(url)
    if match:
        kind, rid = match.group(1), int(match.group(2))
        if resource is not None and kind != resource:
            return False
        return store.get_metadata(kind, rid) is not None

    # Addresses are sub-resources of a vendor (spec 12.9), not a top-level collection.
    address = _ADDRESS.match(url)
    if address and resource in (None, "addresses"):
        vendor = store.get_metadata("vendors", int(address.group(1)))
        return bool(vendor) and any(
            a.get("url") == url for a in vendor.get("addresses", [])
        )

    return False
