from sqlalchemy import func, select

from app.core.link_schemas import PublicLinkInfo
from app.core.public_links import PublicLink
from app.modules.requests.models import RequestStatus
from app.modules.tourists.models import Tourist


def is_editable(request):
    # The active-booking guard is added together with booking creation in #14.
    return request.status in (RequestStatus.IN_PROGRESS, RequestStatus.OFFER_PREPARED)


def request_details(session, rows):
    identities = [row.id for row in rows if row.status != RequestStatus.NEW]
    counts, links = {}, {}
    if identities:
        counts = dict(
            session.execute(
                select(Tourist.request_id, func.count())
                .where(Tourist.request_id.in_(identities), Tourist.removed_at.is_(None))
                .group_by(Tourist.request_id)
            ).all()
        )
        now = session.scalar(select(func.clock_timestamp()))
        links = {
            link.request_id: PublicLinkInfo(
                id=link.id,
                purpose=link.purpose,
                expires_at=link.expires_at,
                is_active=link.revoked_at is None and link.expires_at > now,
            )
            for link in session.scalars(
                select(PublicLink)
                .where(PublicLink.request_id.in_(identities), PublicLink.purpose == "tourists")
                .distinct(PublicLink.request_id)
                .order_by(PublicLink.request_id, PublicLink.created_at.desc(), PublicLink.id.desc())
                .execution_options(populate_existing=True)
            )
        }
    return {
        row.id: {
            "tourists_received": counts.get(row.id, 0),
            "tourist_form_editable": is_editable(row),
            "tourist_link": links.get(row.id),
        }
        for row in rows
    }
