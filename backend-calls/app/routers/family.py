from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import case_for_user, membership
from ..escalation import audit
from ..models import CaseMember, Device, User
from ..schemas import DeviceIn, MemberIn, MemberOut, SettingsIn
from ..security import current_user, normalize_email, normalize_phone

router = APIRouter(tags=["family"])


def _out(m: CaseMember) -> MemberOut:
    return MemberOut(user_id=m.user_id, name=m.user.name, relation=m.relation, permission=m.permission,
                     allow_alert_calls=m.allow_alert_calls, priority=m.priority)


@router.put("/devices")
def register_device(body: DeviceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Call on every app start and from FirebaseMessagingService.onNewToken."""
    dev = db.scalar(select(Device).where(Device.fcm_token == body.fcm_token))
    if dev is None:
        db.add(Device(user_id=user.id, fcm_token=body.fcm_token))
    else:
        dev.user_id = user.id  # token moved to a different account on the same phone
    db.commit()
    return {"ok": True}


@router.delete("/devices")
def unregister_device(body: DeviceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Call on logout so a signed-out phone stops receiving alerts."""
    dev = db.scalar(select(Device).where(Device.fcm_token == body.fcm_token, Device.user_id == user.id))
    if dev:
        db.delete(dev)
        db.commit()
    return {"ok": True}


@router.get("/members", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db), user: User = Depends(current_user)):
    case = case_for_user(db, user)
    return [_out(m) for m in case.members]


@router.post("/members", response_model=MemberOut, status_code=201)
def add_member(body: MemberIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Patient: may add exactly one (the first helper). Family with 'approve': may add as many as they like."""
    case = case_for_user(db, user)
    if user.role == "patient":
        if case.members:
            raise HTTPException(403, "You have already added your family member. Ask them to add more people.")
        permission = "approve"          # the first helper always gets approve rights
    else:
        me = membership(db, case, user)
        if me is None or me.permission != "approve":
            raise HTTPException(403, "Only family members who can approve may invite others")
        permission = body.permission
    try:
        phone = normalize_phone(body.phone)
    except ValueError:
        raise HTTPException(422, "Enter a valid mobile number")
    email = normalize_email(body.email)

    invited = db.scalar(select(User).where(User.phone == phone))
    if invited is None:
        invited = User(name=body.name.strip(), phone=phone, email=email, role="family")
        db.add(invited)
        db.flush()
    elif invited.role != "family" or invited.email != email:
        raise HTTPException(409, "That number is already registered with different details")
    if invited.id == case.patient_id:
        raise HTTPException(422, "The patient can't be their own family member")
    if membership(db, case, invited):
        raise HTTPException(409, "Already in the family circle")

    m = CaseMember(case_id=case.id, user_id=invited.id, relation=body.relation, permission=permission,
                   priority=len(case.members), added_by=user.id)
    db.add(m)
    audit(db, case.id, None, f"user:{user.id}", "member_added", member=invited.id, permission=permission)
    db.commit()
    db.refresh(m)
    return _out(m)


@router.patch("/me/settings")
def update_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Family members can switch alert calls off for themselves. Patients can change language."""
    if body.language:
        user.language = body.language
    if body.allow_alert_calls is not None:
        if user.role != "family":
            raise HTTPException(400, "Only family members receive alert calls")
        case = case_for_user(db, user)
        m = membership(db, case, user)
        m.allow_alert_calls = body.allow_alert_calls
        audit(db, case.id, None, f"user:{user.id}", "alert_calls_" + ("on" if body.allow_alert_calls else "off"))
    db.commit()
    return {"ok": True}
