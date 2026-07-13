"""Metadata resources: vendors, persons, modules, OEs, dependencies (spec 12.8-12.13).

All five are the same resource shape — a collection of JSON objects addressed by
`/acvp/v1/{resource}/{id}` — so they are registered from one generic implementation
rather than five near-identical routers.

Creates and updates go through the spec's request-approval flow (12.7): POST/PUT
returns a request URL, and `GET /requests/{id}` yields the `approvedUrl` of the
resource once the authority has processed it. That is the same flow certification
already uses.

[HUMAN REVIEW] Every URL a client supplies here is checked against core.refs before
it is stored. An unchecked reference is how a certificate ends up pointing at a
module that does not exist.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel, ValidationError

from app.core.auth import current_subject
from app.core import refs
from app.core.jobs import submit
from app.models.envelope import wrap, unwrap
from app.models.metadata import METADATA_MODELS, dump
from app.models.paging import DEFAULT_LIMIT, paged
from app.store import METADATA_RESOURCES, store

router = APIRouter()


def _url(resource: str, rid: int) -> str:
    return f"/acvp/v1/{resource}/{rid}"


def _served(resource: str, rid: int, obj: dict) -> dict:
    """The resource as served: its own url first (spec: `url` is a property)."""
    return {"url": _url(resource, rid), **obj}


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    where = ".".join(str(p) for p in err["loc"])
    return f"{where}: {err['msg']}" if where else err["msg"]


def _parse(resource: str, payload: dict) -> BaseModel:
    model, references = METADATA_MODELS[resource]
    try:
        parsed = model(**payload)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _first_error(exc))

    # A reference the client supplied must name something that exists.
    for field, target in references:
        value = getattr(parsed, field, None)
        for url in value if isinstance(value, list) else [value]:
            if url is not None and not refs.exists(url, resource=target):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{field} does not resolve to an existing {target} resource: {url}",
                )
    if resource == "modules" and parsed.addressUrl is not None:
        if not refs.exists(parsed.addressUrl, resource="addresses"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"addressUrl does not resolve to an existing address: {parsed.addressUrl}",
            )
    return parsed


def _materialise(resource: str, rid: int, obj: dict) -> dict:
    """Mint URLs for sub-resources created alongside their parent.

    A vendor's addresses are addressable (spec 12.9) but have no collection of
    their own — they come into being with the vendor that owns them.
    """
    if resource == "vendors":
        obj["addresses"] = [
            {"url": f"{_url('vendors', rid)}/addresses/{i}", **address}
            for i, address in enumerate(obj.get("addresses", []), start=1)
        ]
        obj["contactsUrl"] = f"{_url('vendors', rid)}/contacts"
    return obj


def _request_response(rid: int) -> list:
    return wrap({"url": f"/acvp/v1/requests/{rid}", "status": "processing"})


def _register(resource: str) -> None:
    """Wire the five CRUD operations for one metadata resource."""

    @router.get(f"/{resource}", operation_id=f"list_{resource}")
    def _list(
        offset: int = 0, limit: int = DEFAULT_LIMIT, _: str = Depends(current_subject)
    ) -> list:
        data = [_served(resource, rid, obj) for rid, obj in store.list_metadata(resource)]
        return wrap(paged(resource, data, offset=offset, limit=limit))

    @router.post(f"/{resource}", operation_id=f"create_{resource}")
    def _create(body: list = Body(...), subject: str = Depends(current_subject)) -> list:
        obj = dump(_parse(resource, unwrap(body)))

        async def _run(rid: int) -> None:
            new_id = store.add_metadata(resource, obj)
            store.replace_metadata(resource, new_id, _materialise(resource, new_id, obj))
            store.complete_request(rid, _url(resource, new_id))

        return _request_response(submit(_run, owner=subject))

    @router.get(f"/{resource}/{{resourceId}}", operation_id=f"get_{resource}")
    def _get(resourceId: int, _: str = Depends(current_subject)) -> list:
        obj = store.get_metadata(resource, resourceId)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{resource} resource not found")
        return wrap(_served(resource, resourceId, obj))

    @router.put(f"/{resource}/{{resourceId}}", operation_id=f"update_{resource}")
    def _update(
        resourceId: int, body: list = Body(...), subject: str = Depends(current_subject)
    ) -> list:
        if store.get_metadata(resource, resourceId) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{resource} resource not found")
        obj = _materialise(resource, resourceId, dump(_parse(resource, unwrap(body))))

        async def _run(rid: int) -> None:
            store.replace_metadata(resource, resourceId, obj)
            store.complete_request(rid, _url(resource, resourceId))

        return _request_response(submit(_run, owner=subject))

    @router.delete(
        f"/{resource}/{{resourceId}}",
        operation_id=f"delete_{resource}",
        status_code=status.HTTP_200_OK,
    )
    def _delete(resourceId: int, _: str = Depends(current_subject)) -> Response:
        if not store.delete_metadata(resource, resourceId):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{resource} resource not found")
        return Response(status_code=status.HTTP_200_OK)


for _resource in METADATA_RESOURCES:
    _register(_resource)


# --- vendor sub-resources (spec 12.9, 12.8.6) -----------------------------------

def _vendor_or_404(vendorId: int) -> dict:
    vendor = store.get_metadata("vendors", vendorId)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    return vendor


@router.get("/vendors/{vendorId}/addresses")
def list_vendor_addresses(
    vendorId: int, offset: int = 0, limit: int = DEFAULT_LIMIT,
    _: str = Depends(current_subject),
) -> list:
    addresses = _vendor_or_404(vendorId).get("addresses", [])
    return wrap(paged(f"vendors/{vendorId}/addresses", addresses, offset=offset, limit=limit))


@router.get("/vendors/{vendorId}/addresses/{addressId}")
def get_vendor_address(
    vendorId: int, addressId: int, _: str = Depends(current_subject)
) -> list:
    url = f"/acvp/v1/vendors/{vendorId}/addresses/{addressId}"
    address = next(
        (a for a in _vendor_or_404(vendorId).get("addresses", []) if a.get("url") == url), None
    )
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "address not found")
    return wrap(address)


@router.get("/vendors/{vendorId}/contacts")
def list_vendor_contacts(
    vendorId: int, offset: int = 0, limit: int = DEFAULT_LIMIT,
    _: str = Depends(current_subject),
) -> list:
    """The person resources associated with this vendor (spec 12.8.6)."""
    _vendor_or_404(vendorId)
    vendor_url = _url("vendors", vendorId)
    contacts = [
        _served("persons", rid, obj)
        for rid, obj in store.list_metadata("persons")
        if obj.get("vendorUrl") == vendor_url
    ]
    return wrap(paged(f"vendors/{vendorId}/contacts", contacts, offset=offset, limit=limit))
