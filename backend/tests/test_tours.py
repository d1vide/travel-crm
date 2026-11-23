from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.main import create_app
from app.modules.tours.models import TourOffer
from app.modules.tours.normalization import normalize_destination
from app.modules.tours.seed import DEMO_TOURS
from app.seed import seed_demo
from tests.test_foundation import validate


@pytest.fixture
def headers(login):
    return {"Authorization": "Bearer " + login().json()["access_token"]}


def offer():
    return TourOffer(
        title="Учебный тур",
        destination="Сочи",
        destination_normalized="сочи",
        starts_on=date(2027, 6, 1),
        ends_on=date(2027, 6, 8),
        tourist_count=2,
        supplier="Учебный поставщик",
        services=["Отель"],
        price=Decimal("100000.00"),
        currency="RUB",
        is_active=True,
        version=1,
    )


def test_list_and_card_follow_frozen_contract(client, headers):
    response = client.get("/api/tours", headers=headers)
    assert response.status_code == 200
    page = response.json()
    validate("TourOfferPage", page)
    assert page["total"] == len(DEMO_TOURS) and page["page_size"] == 20
    prices = [Decimal(item["price"]) for item in page["items"]]
    assert prices == sorted(prices)
    row = page["items"][0]
    assert row["services"] and row["supplier"] and row["currency"] == "RUB"
    assert "destination_normalized" not in row and "created_at" not in row
    card = client.get(f"/api/tours/{row['id']}", headers=headers)
    assert card.status_code == 200 and card.json() == row
    validate("TourOffer", card.json())


@pytest.mark.parametrize(
    "actor,status",
    [("manager@example.com", 200), ("head@example.com", 200), ("accountant@example.com", 403)],
)
def test_role_access(client, login, database, actor, status):
    with database.sessions() as session:
        identity = session.scalar(select(TourOffer.id).limit(1))
    headers = {"Authorization": "Bearer " + login(actor).json()["access_token"]}
    for path in ("/api/tours", f"/api/tours/{identity}"):
        assert client.get(path, headers=headers).status_code == status
        assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "params,expected",
    [
        ({"destination": "сОЧ"}, 3),
        ({"destination": "  АНТАЛЬЯ  "}, 2),
        ({"tourist_count": 4}, 1),
        ({"max_price": "48000.00"}, 1),
        ({"max_price": "0.00"}, 0),
        ({"starts_from": "2027-07-01"}, 1),
        ({"ends_until": "2027-06-06"}, 2),
        (
            {
                "destination": "Сочи",
                "starts_from": "2027-06-01",
                "ends_until": "2027-06-08",
                "tourist_count": 2,
                "max_price": "100000.00",
            },
            1,
        ),
        ({"destination": "Сочи", "starts_from": "2027-06-02", "ends_until": "2027-06-08"}, 0),
    ],
)
def test_filters_and_inclusive_boundaries(client, headers, params, expected):
    response = client.get("/api/tours", params=params, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == expected
    validate("TourOfferPage", response.json())


@pytest.mark.parametrize(
    "params",
    [
        {"destination": ""},
        {"destination": " "},
        {"destination": "private\x00"},
        {"starts_from": "2027-02-30"},
        {"starts_from": "2027-06-01T00:00:00Z"},
        {"ends_until": "2027-05-31", "starts_from": "2027-06-01"},
        {"tourist_count": 0},
        {"tourist_count": "true"},
        {"tourist_count": 2**31},
        {"max_price": "-1.00"},
        {"max_price": "1.2"},
        {"max_price": "1e5"},
        {"max_price": "01.00"},
        {"max_price": "1000000000000.00"},
        {"page": 0},
        {"page": 10**30},
        {"page_size": 101},
        {"sort": "supplier"},
        {"is_active": "false"},
    ],
)
def test_invalid_queries_use_unified_errors(client, headers, params):
    response = client.get("/api/tours", params=params, headers=headers)
    assert response.status_code == 422
    validate("Error", response.json())
    assert "private" not in response.text


def test_inactive_offer_and_unknown_id_are_indistinguishable(client, headers, database):
    with database.sessions.begin() as session:
        row = session.scalar(select(TourOffer).limit(1))
        row.is_active = False
        identity = row.id
    page = client.get("/api/tours", headers=headers).json()
    assert page["total"] == len(DEMO_TOURS) - 1
    assert str(identity) not in [row["id"] for row in page["items"]]
    hidden = client.get(f"/api/tours/{identity}", headers=headers)
    missing = client.get(f"/api/tours/{uuid4()}", headers=headers)
    assert hidden.status_code == missing.status_code == 404 and hidden.json() == missing.json()
    assert client.get("/api/tours/invalid", headers=headers).status_code == 422


@pytest.mark.parametrize("sort", ["price", "-price", "starts_on"])
def test_stable_sort_and_pagination(client, headers, database, sort):
    with database.sessions.begin() as session:
        session.execute(delete(TourOffer))
        for identity in (UUID(int=3), UUID(int=1), UUID(int=2)):
            row = offer()
            row.id = identity
            session.add(row)
    pages = [
        client.get(
            "/api/tours", params={"sort": sort, "page": page, "page_size": 1}, headers=headers
        ).json()
        for page in (1, 2, 3)
    ]
    assert [page["items"][0]["id"] for page in pages] == [
        str(UUID(int=i)) for i in ((3, 2, 1) if sort == "-price" else (1, 2, 3))
    ]
    assert all(page["total"] == 3 for page in pages)
    empty = client.get("/api/tours", params={"page": 10, "page_size": 1}, headers=headers).json()
    assert empty["total"] == 3 and empty["items"] == []


def test_search_wildcards_are_literal(client, headers, database):
    with database.sessions.begin() as session:
        row = offer()
        row.destination = "Тест %_\\ Направление"
        row.destination_normalized = normalize_destination(row.destination)
        session.add(row)
        session.flush()
        identity = str(row.id)
    page = client.get("/api/tours", params={"destination": "%_\\"}, headers=headers).json()
    assert page["total"] == 1 and page["items"][0]["id"] == identity


@pytest.mark.parametrize(
    "field,value",
    [
        ("price", Decimal("-0.01")),
        ("currency", "USD"),
        ("ends_on", date(2027, 5, 31)),
        ("tourist_count", 0),
        ("title", " "),
        ("destination", ""),
        ("supplier", " "),
        ("version", 0),
        ("services", [""]),
        ("services", [None]),
    ],
)
def test_database_enforces_catalogue_constraints(database, field, value):
    with pytest.raises(IntegrityError), database.sessions.begin() as session:
        row = offer()
        setattr(row, field, value)
        session.add(row)
        session.flush()


def test_seed_is_idempotent_and_preserves_changes(settings, database):
    with database.sessions.begin() as session:
        row = session.scalar(select(TourOffer).limit(1))
        identity = row.id
        row.is_active = False
        row.price = Decimal("123.45")
        row.version = 2
    seed_demo(settings, database)
    seed_demo(settings, database)
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(TourOffer)) == len(DEMO_TOURS)
        row = session.get(TourOffer, identity)
        assert row.is_active is False and row.price == Decimal("123.45") and row.version == 2


def test_disabled_seed_leaves_catalogue_empty(client, headers, settings, database):
    with database.sessions.begin() as session:
        session.execute(delete(TourOffer))
    seed_demo(settings.model_copy(update={"seed_demo": False}), database)
    page = client.get("/api/tours", headers=headers).json()
    assert page["items"] == [] and page["total"] == 0


def test_zero_price_empty_services_and_restart(client, headers, database, settings):
    with database.sessions.begin() as session:
        row = offer()
        row.price = Decimal("0.00")
        row.services = []
        session.add(row)
        session.flush()
        identity = row.id
    with TestClient(create_app(settings)) as restarted:
        response = restarted.get(f"/api/tours/{identity}", headers=headers)
    assert response.status_code == 200
    assert response.json()["price"] == "0.00" and response.json()["services"] == []
    validate("TourOffer", response.json())


def test_catalogue_has_no_write_api(client, headers, database):
    with database.sessions() as session:
        identity = session.scalar(select(TourOffer.id).limit(1))
    for method, path in [
        ("POST", "/api/tours"),
        ("PUT", f"/api/tours/{identity}"),
        ("DELETE", f"/api/tours/{identity}"),
    ]:
        assert client.request(method, path, json={}, headers=headers).status_code == 405
