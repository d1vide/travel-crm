from sqlalchemy import func, select

from app.core.link_schemas import PublicLinkInfo
from app.core.public_links import PublicLink
from app.modules.requests.schemas import OfferSnapshot
from app.modules.tours.selection_models import Selection, SelectionItem
from app.modules.tours.selection_schemas import Selection as SelectionDto
from app.modules.tours.selection_schemas import SelectionItem as ItemDto


def latest_ids(session, request_ids):
    if not request_ids:
        return {}
    return dict(
        session.execute(
            select(Selection.request_id, Selection.id)
            .where(Selection.request_id.in_(request_ids))
            .distinct(Selection.request_id)
            .order_by(Selection.request_id, Selection.created_at.desc(), Selection.id.desc())
        ).all()
    )


def request_details(session, rows):
    latest = latest_ids(session, [row.id for row in rows if row.status == "offer_prepared"])
    identities = {
        row.selected_selection_item_id for row in rows if row.selected_selection_item_id is not None
    }
    items = (
        {
            item.id: item
            for item in session.scalars(
                select(SelectionItem).where(SelectionItem.id.in_(identities))
            )
        }
        if identities
        else {}
    )
    return {
        row.id: {
            "latest_selection_id": latest.get(row.id),
            "selected_selection_id": items[row.selected_selection_item_id].selection_id
            if row.selected_selection_item_id in items
            else None,
            "selected_offer": OfferSnapshot.model_validate(
                items[row.selected_selection_item_id].offer_snapshot
            )
            if row.selected_selection_item_id in items
            else None,
        }
        for row in rows
    }


def project(session, rows):
    identities = [row.id for row in rows]
    if not identities:
        return []
    items = {identity: [] for identity in identities}
    for item in session.scalars(
        select(SelectionItem)
        .where(SelectionItem.selection_id.in_(identities))
        .order_by(SelectionItem.position, SelectionItem.id)
    ):
        items[item.selection_id].append(
            ItemDto(
                id=item.id,
                tour_offer_id=item.tour_offer_id,
                position=item.position,
                offer_snapshot=OfferSnapshot.model_validate(item.offer_snapshot),
            )
        )
    now = session.scalar(select(func.clock_timestamp()))
    links = {
        link.selection_id: PublicLinkInfo(
            id=link.id,
            purpose=link.purpose,
            expires_at=link.expires_at,
            is_active=link.revoked_at is None and link.expires_at > now,
        )
        for link in session.scalars(
            select(PublicLink)
            .where(PublicLink.selection_id.in_(identities))
            .distinct(PublicLink.selection_id)
            .order_by(PublicLink.selection_id, PublicLink.created_at.desc(), PublicLink.id.desc())
            .execution_options(populate_existing=True)
        )
    }
    return [
        SelectionDto(
            id=row.id,
            request_id=row.request_id,
            items=items[row.id],
            created_at=row.created_at,
            public_link=links.get(row.id),
        )
        for row in rows
    ]
