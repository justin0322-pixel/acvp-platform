from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import current_subject
from app.models.envelope import wrap
from app.store import store

router = APIRouter()


@router.get("/requests/{request_id}")
def get_request(request_id: int, _: str = Depends(current_subject)) -> list:
    req = store.get_request(request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "request not found")
    if req["status"] == "processing":
        return wrap({"status": "processing", "retry": 2})  # tell client to poll again
    return wrap({"status": req["status"], "url": req["location"]})
