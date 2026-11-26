from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.bookings.completion import business_date
from tests.payment_gateway import gateway as gateway
from tests.test_bookings import card as booking_card
from tests.test_bookings import command as booking_command
from tests.test_bookings import create as create_booking
from tests.test_clients import actors as actors
from tests.test_clients import create as create_client
from tests.test_clients import payload as client_payload
from tests.test_communications import create as communicate
from tests.test_payments import create as pay
from tests.test_payments import read as payment_card
from tests.test_refunds import create as refund
from tests.test_requests import action, write
from tests.test_requests import create as create_request
from tests.test_selections import issue as selection_link
from tests.test_selections import public_path, publish, read_request
from tests.test_tourists import body, issue, path, staff_list, submit


def accepted(response, status=200):
    assert response.status_code == status
    return response.json()


def select(client, actors, request, item, actor="manager"):
    return accepted(
        write(
            client,
            actors,
            "PUT",
            f"/api/requests/{request['id']}/selected-tour",
            {"version": request["version"], "selection_item_id": item["id"]},
            actor,
        )
    )


def test_acceptance_scenario_sections_1_to_10(client, actors, gateway, database):
    """The ordered business scenario complements, but does not replace, UI acceptance."""
    manager, head, accountant = (
        actors[name]["headers"] for name in ("manager", "head", "accountant")
    )
    # 1-2: actual login is performed by actors; duplicate contacts remain a conflict.
    values = client_payload(
        full_name="Учебный клиент приёмки", phone=None, email="acceptance@example.com"
    )
    customer = accepted(create_client(client, actors, body=values), 201)
    assert create_client(client, actors, body=values).status_code == 409
    request = accepted(create_request(client, actors, customer["id"]), 201)
    request = accepted(action(client, actors, request, "start-work"))
    # 3-4: catalogue filters, anonymous selection and anonymous full tourist submission.
    catalog = accepted(
        client.get(
            "/api/tours",
            params={
                "destination": "Сочи",
                "tourist_count": 2,
                "max_price": "120000.00",
                "starts_from": "2027-06-01",
                "ends_until": "2027-06-08",
            },
            headers=manager,
        )
    )
    assert catalog["items"]
    offer = catalog["items"][0]
    selection = accepted(publish(client, actors, request, [offer["id"]]), 201)
    link = accepted(selection_link(client, actors, selection), 201)
    public = accepted(client.get(public_path(link)))
    assert public["items"][0]["offer_snapshot"]["price"] == offer["price"]
    request = select(
        client, actors, read_request(client, actors, request["id"]), selection["items"][0]
    )
    tourists = accepted(issue(client, actors, request), 201)
    assert accepted(client.get(path(tourists)))["is_editable"]
    accepted(submit(client, tourists, body(request)))
    assert len(accepted(staff_list(client, actors, request))) == 2
    request = read_request(client, actors, request["id"])
    assert request["tourists_received"] == 2
    # 5-6: confirmation, two partial payments and repeated processing.
    booking = accepted(create_booking(client, actors, request), 201)
    booking = accepted(
        booking_command(
            client, actors, booking, "confirm", supplier_booking_number="DEMO-ACCEPTANCE-19"
        )
    )
    first = accepted(pay(client, actors, booking, "30000.00"), 202)
    assert gateway.outcome(first, "succeeded").status_code == 200
    assert accepted(payment_card(client, actors, first["id"]))["status"] == "succeeded"
    booking = accepted(booking_card(client, actors, booking["id"]))
    assert booking["paid_amount"] == "30000.00" and booking["remaining_amount"] == "70000.00"
    second = accepted(pay(client, actors, booking, "70000.00"), 202)
    assert gateway.outcome(second, "succeeded").status_code == 200
    accepted(payment_card(client, actors, second["id"]))
    for payment in (first, second):
        accepted(client.post(f"/api/payments/{payment['id']}/reconcile", headers=manager), 202)
    booking = accepted(booking_card(client, actors, booking["id"]))
    assert booking["paid_amount"] == booking["total_amount"] == "100000.00"
    assert booking["remaining_amount"] == "0.00"
    assert accepted(client.get("/api/notifications", headers=manager))["unread_count"] == 2
    # 7: restart the real provider and use a fresh backend instance against the same DB.
    accepted(
        communicate(
            client, actors, customer["id"], request_id=request["id"], text="Учебная запись приёмки"
        ),
        201,
    )
    gateway.restart()
    with TestClient(create_app(gateway.crm_settings)) as restarted:
        found = accepted(
            restarted.get("/api/clients", params={"q": "acceptance@example.com"}, headers=manager)
        )
        assert found["total"] == 1
        history = accepted(
            restarted.get(f"/api/requests/{request['id']}/communications", headers=manager)
        )
        assert history["items"][0]["text"] == "Учебная запись приёмки"
        assert accepted(payment_card(restarted, actors, second["id"]))["status"] == "succeeded"
    # 8: cancellation, independent refunds and a strict aggregate limit.
    booking = accepted(
        booking_command(
            client, actors, booking, "request-cancellation", reason="Учебная просьба об отмене"
        )
    )
    booking = accepted(
        booking_command(
            client,
            actors,
            booking,
            "confirm-cancellation",
            supplier_response="Поставщик подтвердил отмену",
        )
    )
    assert booking["status"] == "cancelled" and booking["paid_amount"] == "100000.00"
    assert refund(client, actors, first, "30000.01").json()["code"] == "refund_limit_exceeded"
    for payment in (first, second):
        returned = accepted(refund(client, actors, payment, payment["amount"]), 202)
        assert returned["status"] == "succeeded"
        assert accepted(payment_card(client, actors, payment["id"]))["status"] == "succeeded"
    booking = accepted(booking_card(client, actors, booking["id"]))
    assert booking["refunded_amount"] == "100000.00" and booking["status"] == "cancelled"
    assert (
        client.get(public_path(link)).status_code == client.get(path(tourists)).status_code == 404
    )
    # 9: reassignment, report facts and the accountant's safe projections.
    request = read_request(client, actors, request["id"], "head")
    accepted(
        write(
            client,
            actors,
            "PATCH",
            f"/api/requests/{request['id']}/assignee",
            {"version": request["version"], "manager_id": str(actors["other"]["id"])},
            "head",
        )
    )
    assert client.get(f"/api/requests/{request['id']}", headers=manager).status_code == 404
    with database.sessions() as session:
        today = str(business_date(session))
    report = accepted(
        client.get(
            "/api/reports/summary", params={"date_from": today, "date_to": today}, headers=head
        )
    )
    assert report["requests_created"] == report["bookings_confirmed"] == 1
    assert report["payments_succeeded_amount"] == report["refunds_succeeded_amount"] == "100000.00"
    returns = client.get("/api/refunds", headers=accountant)
    assert accepted(returns)["total"] == 2 and "document_number" not in returns.text
    assert all(not item["can_open_request"] for item in returns.json()["items"])
    # 10: another attempt can be rejected; an explicit later choice creates a new booking.
    another = accepted(create_request(client, actors, customer["id"], actor="head"), 201)
    another = accepted(action(client, actors, another, "start-work", actor="head"))
    selected = accepted(publish(client, actors, another, [offer["id"]], actor="head"), 201)
    another = select(
        client,
        actors,
        read_request(client, actors, another["id"], "head"),
        selected["items"][0],
        "head",
    )
    tourist_link = accepted(issue(client, actors, another, "head"), 201)
    accepted(submit(client, tourist_link, body(another)))
    another = read_request(client, actors, another["id"], "head")
    attempt = accepted(create_booking(client, actors, another, actor="head"), 201)
    assert (
        accepted(
            booking_command(client, actors, attempt, "reject", actor="head", reason="Учебный отказ")
        )["status"]
        == "rejected"
    )
    another = select(
        client,
        actors,
        read_request(client, actors, another["id"], "head"),
        selected["items"][0],
        "head",
    )
    attempt = accepted(create_booking(client, actors, another, actor="head"), 201)
    attempt = accepted(
        booking_command(
            client,
            actors,
            attempt,
            "confirm",
            actor="head",
            supplier_booking_number="DEMO-ACCEPTANCE-RETRY",
        )
    )
    failed = accepted(pay(client, actors, attempt, "1000.00", actor="head"), 202)
    assert gateway.outcome(failed, "failed").status_code == 200
    assert accepted(payment_card(client, actors, failed["id"], "head"))["status"] == "failed"
    assert accepted(booking_card(client, actors, attempt["id"], "head"))["paid_amount"] == "0.00"
    assert (
        client.get(
            "/api/reports/summary", params={"date_from": today, "date_to": today}, headers=manager
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/bookings/{attempt['id']}/payments",
            json={"version": attempt["version"], "amount": "1.00", "currency": "RUB"},
            headers=accountant,
        ).status_code
        == 403
    )
    report = accepted(
        client.get(
            "/api/reports/summary", params={"date_from": today, "date_to": today}, headers=head
        )
    )
    assert report["requests_created"] == report["bookings_confirmed"] == 2
    assert report["payments_succeeded_amount"] == report["refunds_succeeded_amount"] == "100000.00"
