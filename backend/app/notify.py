import logging

from sqlmodel import Session, select

from . import firebase
from .models import CaseMember, Device

log = logging.getLogger("medsure.notify")


def notify_case(
    session: Session,
    case_id: int,
    title: str,
    body: str,
    kind: str,
    ref_id: int | None = None,
    exclude_user_id: str | None = None,
) -> int:
    """Push to every device of the case's members. Call after commit. Never raises.

    Keep title/body generic: they show on lock screens, so no medical detail.
    The app uses data.kind + data.ref_id to open the right screen.
    """
    if not firebase.enabled():
        return 0
    stmt = (
        select(Device.token)
        .join(CaseMember, CaseMember.user_id == Device.user_id)
        .where(CaseMember.case_id == case_id)
    )
    if exclude_user_id:
        stmt = stmt.where(Device.user_id != exclude_user_id)
    tokens = list(session.exec(stmt).all())
    if not tokens:
        return 0
    data = {"case_id": str(case_id), "kind": kind, "ref_id": str(ref_id or "")}
    try:
        sent, dead = firebase.send_push(tokens, title, body, data)
        for token in dead:
            if device := session.get(Device, token):
                session.delete(device)
        if dead:
            session.commit()
        return sent
    except Exception:
        log.exception("Push failed for case %s", case_id)
        session.rollback()
        return 0
