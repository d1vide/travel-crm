from urllib.parse import urlsplit

import httpx
import pytest

from tests.payment_gateway import gateway as gateway
from tests.test_bookings import context as context
from tests.test_clients import actors as actors
from tests.test_payments import create
from tests.test_payments import ready as ready


@pytest.mark.parametrize("origin", [None, "null", "https://other.example"])
def test_checkout_keeps_strict_origin_after_script_submission_fix(
    client, actors, ready, gateway, origin
):
    payment = create(client, actors, ready[1]).json()
    with httpx.Client(base_url=gateway.url, trust_env=False) as browser:
        page = browser.get(urlsplit(payment["payment_url"]).path)
        assert page.status_code == 200
        assert page.headers["Referrer-Policy"] == "no-referrer"
        assert 'src="/payment-stub/checkout.js"' in page.text
        script = browser.get("/payment-stub/checkout.js")
        assert script.status_code == 200
        assert script.headers["Cache-Control"] == "no-store"
        assert script.headers["Referrer-Policy"] == "no-referrer"
        response = browser.post(
            urlsplit(payment["payment_url"]).path,
            data={"outcome": "succeeded"},
            headers={"Origin": origin} if origin is not None else {},
        )
        assert response.status_code == 403
        assert "Ожидает оплаты" in browser.get(urlsplit(payment["payment_url"]).path).text
