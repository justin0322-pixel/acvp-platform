from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import current_subject
from app.models.envelope import wrap
from app.models.paging import DEFAULT_LIMIT, paged
from app.store import store

router = APIRouter()


def _request_object(rid: int, req: dict) -> dict:
    """Spec 12.7 request object: url + status (+ approvedUrl / message)."""
    body = {"url": f"/acvp/v1/requests/{rid}", "status": req["status"]}
    if req.get("location"):
        body["approvedUrl"] = req["location"]
    if req.get("message"):
        body["message"] = req["message"]
    return body


@router.get("/requests")
def list_requests(
    offset: int = 0, limit: int = DEFAULT_LIMIT, subject: str = Depends(current_subject)
) -> list:
    """Paged listing of the current user's requests (spec 12.7.1)."""
    data = [_request_object(rid, req) for rid, req in store.list_requests(owner=subject)]
    return wrap(paged("requests", data, offset=offset, limit=limit))


@router.get("/requests/{requestId}")
def get_request(requestId: int, _: str = Depends(current_subject)) -> list:
    req = store.get_request(requestId)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "request not found")
    # The client keeps polling while status is initial/processing.
    return wrap(_request_object(requestId, req))
