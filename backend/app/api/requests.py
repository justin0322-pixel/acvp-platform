from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import current_subject
from app.models.envelope import wrap
from app.store import store

router = APIRouter()


@router.get("/requests/{requestId}")
def get_request(requestId: int, _: str = Depends(current_subject)) -> list:
    req = store.get_request(requestId)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "request not found")
    # Spec request object: url + status (+ approvedUrl / message). The client
    # keeps polling while status is initial/processing.
    body = {"url": f"/acvp/v1/requests/{requestId}", "status": req["status"]}
    if req.get("location"):
        body["approvedUrl"] = req["location"]
    if req.get("message"):
        body["message"] = req["message"]
    return wrap(body)
