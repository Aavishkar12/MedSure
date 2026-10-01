from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..deps import current_user
from ..models import Device, User, now

router = APIRouter(tags=["account"])


class DeviceRegister(BaseModel):
    token: str
    platform: str = "android"


@router.get("/me", response_model=User)
def me(user: User = Depends(current_user)):
    return user


@router.post("/devices", status_code=204)
def register_device(body: DeviceRegister, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Call after sign-in and whenever FCM issues a new token. A token moves to whoever registered it last."""
    session.merge(Device(token=body.token, user_id=user.id, platform=body.platform, updated_at=now()))
    session.commit()


@router.delete("/devices/{token}", status_code=204)
def unregister_device(token: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Call on sign-out so this phone stops getting the previous user's notifications."""
    device = session.get(Device, token)
    if device and device.user_id == user.id:
        session.delete(device)
        session.commit()
