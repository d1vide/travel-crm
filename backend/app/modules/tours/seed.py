from datetime import date
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert

from app.modules.tours.models import TourOffer
from app.modules.tours.normalization import normalize_destination

# Fixed fictional offers aligned with the dates used in the request examples.
DEMO_TOURS = (
    (
        "sochi-sea",
        "Учебный тур: море в Сочи",
        "Сочи",
        "2027-06-01",
        "2027-06-08",
        2,
        "100000.00",
        ["Перелёт", "Отель", "Завтраки"],
    ),
    (
        "sochi-comfort",
        "Учебный тур: Сочи комфорт",
        "Сочи",
        "2027-06-01",
        "2027-06-08",
        2,
        "140000.00",
        ["Перелёт", "Отель", "Полупансион", "Трансфер"],
    ),
    (
        "sochi-july",
        "Учебный тур: июль в Сочи",
        "Сочи",
        "2027-07-01",
        "2027-07-08",
        2,
        "110000.00",
        ["Перелёт", "Отель"],
    ),
    (
        "antalya",
        "Учебный тур: Анталья",
        "Турция, Анталья",
        "2027-06-01",
        "2027-06-08",
        2,
        "160000.00",
        ["Перелёт", "Отель", "Всё включено", "Трансфер"],
    ),
    (
        "antalya-family",
        "Учебный тур: семейная Анталья",
        "Турция, Анталья",
        "2027-06-01",
        "2027-06-08",
        4,
        "260000.00",
        ["Перелёт", "Отель", "Всё включено"],
    ),
    (
        "kazan",
        "Учебный тур: выходные в Казани",
        "Казань",
        "2027-06-04",
        "2027-06-06",
        2,
        "48000.00",
        ["Отель", "Экскурсия"],
    ),
    (
        "altai",
        "Учебный тур: Алтай",
        "Алтай",
        "2027-06-01",
        "2027-06-08",
        1,
        "75000.00",
        ["Проживание", "Экскурсии"],
    ),
    (
        "petersburg",
        "Учебный тур: Санкт-Петербург",
        "Санкт-Петербург",
        "2027-06-02",
        "2027-06-05",
        2,
        "62000.00",
        ["Отель", "Экскурсия"],
    ),
)


def seed_tours(session):
    for slug, title, destination, starts, ends, count, price, services in DEMO_TOURS:
        session.execute(
            insert(TourOffer)
            .values(
                id=uuid5(NAMESPACE_URL, f"travelcrm-demo-tour:{slug}"),
                title=title,
                destination=destination,
                destination_normalized=normalize_destination(destination),
                starts_on=date.fromisoformat(starts),
                ends_on=date.fromisoformat(ends),
                tourist_count=count,
                supplier="Учебный туроператор",
                services=services,
                price=Decimal(price),
                currency="RUB",
                is_active=True,
                version=1,
            )
            .on_conflict_do_nothing(index_elements=[TourOffer.id])
        )
