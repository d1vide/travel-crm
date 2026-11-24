from decimal import Decimal

from sqlalchemy import func, select

from app.core.errors import ApiError
from app.modules.tours.models import TourOffer as Offer
from app.modules.tours.normalization import contains_destination
from app.modules.tours.schemas import TourOffer, TourOfferPage


def card(row: Offer) -> TourOffer:
    return TourOffer(
        id=row.id,
        title=row.title,
        destination=row.destination,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        tourist_count=row.tourist_count,
        supplier=row.supplier,
        services=row.services,
        price=f"{row.price:.2f}",
        currency=row.currency,
        is_active=row.is_active,
        version=row.version,
    )


def list_tours(session, query):
    conditions = [Offer.is_active.is_(True)]
    if query.destination is not None:
        conditions.append(
            Offer.destination_normalized.like(contains_destination(query.destination), escape="\\")
        )
    if query.starts_from is not None:
        conditions.append(Offer.starts_on >= query.starts_from)
    if query.ends_until is not None:
        conditions.append(Offer.ends_on <= query.ends_until)
    if query.tourist_count is not None:
        conditions.append(Offer.tourist_count == query.tourist_count)
    if query.max_price is not None:
        conditions.append(Offer.price <= Decimal(query.max_price))
    ordering = {
        "price": (Offer.price.asc(), Offer.id.asc()),
        "-price": (Offer.price.desc(), Offer.id.desc()),
        "starts_on": (Offer.starts_on.asc(), Offer.id.asc()),
    }[query.sort]
    total = session.scalar(select(func.count()).select_from(Offer).where(*conditions))
    rows = session.scalars(
        select(Offer)
        .where(*conditions)
        .order_by(*ordering)
        .offset(query.offset)
        .limit(query.page_size)
    )
    return TourOfferPage(
        items=[card(row) for row in rows], page=query.page, page_size=query.page_size, total=total
    )


def get_tour(session, identity):
    row = session.scalar(select(Offer).where(Offer.id == identity, Offer.is_active.is_(True)))
    if row is None:
        raise ApiError(404, "not_found", "Предложение не найдено")
    return card(row)


def snapshots_for_selection(session, identities):
    from app.modules.requests.schemas import OfferSnapshot

    rows = session.scalars(
        select(Offer)
        .where(Offer.id.in_(identities), Offer.is_active.is_(True))
        .order_by(Offer.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).all()
    if len(rows) != len(identities):
        raise ApiError(404, "not_found", "Предложение не найдено")
    return {
        row.id: OfferSnapshot.model_validate(
            card(row).model_dump(exclude={"id", "version", "is_active"})
        ).model_dump(mode="json")
        for row in rows
    }
