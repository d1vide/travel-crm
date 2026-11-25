from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import Field, model_validator

from app.core.schemas import Dto
from app.core.validation import Money


class ProviderError(Exception):
    pass


class ProviderPayment(Dto):
    id: UUID
    client_operation_id: UUID
    amount: Money
    currency: Literal["RUB"]
    status: Literal["pending", "succeeded", "failed"]
    checkout_token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)
    failure_reason: str | None
    succeeded_at: datetime | None

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == "succeeded") != (self.succeeded_at is not None):
            raise ValueError("Invalid success timestamp")
        if self.succeeded_at is not None and (
            self.succeeded_at.tzinfo is None or self.succeeded_at.utcoffset().total_seconds() != 0
        ):
            raise ValueError("Expected UTC timestamp")
        if (self.status == "failed") != (bool(self.failure_reason)):
            raise ValueError("Invalid failure reason")
        return self


class ProviderRefund(Dto):
    id: UUID
    client_operation_id: UUID
    payment_id: UUID
    amount: Money
    currency: Literal["RUB"]
    status: Literal["processing", "succeeded", "failed"]
    failure_reason: str | None
    succeeded_at: datetime | None

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == "succeeded") != (self.succeeded_at is not None):
            raise ValueError("Invalid success timestamp")
        if self.succeeded_at is not None and (
            self.succeeded_at.tzinfo is None or self.succeeded_at.utcoffset().total_seconds() != 0
        ):
            raise ValueError("Expected UTC timestamp")
        if (self.status == "failed") != bool(self.failure_reason):
            raise ValueError("Invalid failure reason")
        return self


class StubAdapter:
    def __init__(self, settings):
        self.settings = settings

    def configured(self):
        return (
            self.settings.payment_stub_key is not None
            and len(self.settings.payment_stub_key.get_secret_value()) >= 32
        )

    def fetch(self, identity, external_id, amount, currency):
        if not self.configured():
            raise ProviderError("Платёжный сервис не настроен")
        try:
            with httpx.Client(
                base_url=self.settings.payment_stub_url,
                timeout=self.settings.payment_timeout_seconds,
                trust_env=False,
                follow_redirects=False,
                headers={
                    "Authorization": "Bearer " + self.settings.payment_stub_key.get_secret_value()
                },
            ) as client:
                response = (
                    client.get(f"/v1/payments/{external_id}")
                    if external_id
                    else client.post(
                        "/v1/payments",
                        json={
                            "client_operation_id": str(identity),
                            "amount": f"{amount:.2f}",
                            "currency": currency,
                        },
                    )
                )
                response.raise_for_status()
                data = ProviderPayment.model_validate(response.json())
            if (
                data.client_operation_id != identity
                or data.amount != f"{amount:.2f}"
                or data.currency != currency
                or (external_id is not None and str(data.id) != external_id)
            ):
                raise ProviderError("Ответ сервиса не соответствует платежу; требуется сверка")
            return data
        except httpx.TimeoutException:
            raise ProviderError("Платёжный сервис не ответил вовремя; требуется сверка") from None
        except (httpx.HTTPError, ValueError):
            raise ProviderError(
                "Платёжный сервис недоступен или вернул некорректный ответ; требуется сверка"
            ) from None

    def url(self, data):
        return f"{self.settings.public_app_url}/payment-stub/pay/{data.checkout_token}"

    def fetch_refund(self, identity, external_id, payment_id, amount, currency):
        if not self.configured():
            raise ProviderError("Платёжный сервис не настроен")
        try:
            with httpx.Client(
                base_url=self.settings.payment_stub_url,
                timeout=self.settings.payment_timeout_seconds,
                trust_env=False,
                follow_redirects=False,
                headers={
                    "Authorization": "Bearer " + self.settings.payment_stub_key.get_secret_value()
                },
            ) as client:
                response = (
                    client.get(f"/v1/refunds/{external_id}")
                    if external_id
                    else client.post(
                        "/v1/refunds",
                        json={
                            "client_operation_id": str(identity),
                            "payment_id": str(payment_id),
                            "amount": f"{amount:.2f}",
                            "currency": currency,
                        },
                    )
                )
                response.raise_for_status()
                data = ProviderRefund.model_validate(response.json())
            if (
                data.client_operation_id != identity
                or str(data.payment_id) != str(payment_id)
                or data.amount != f"{amount:.2f}"
                or data.currency != currency
                or (external_id is not None and str(data.id) != external_id)
            ):
                raise ProviderError("Ответ сервиса не соответствует возврату; требуется сверка")
            return data
        except httpx.TimeoutException:
            raise ProviderError(
                "Платёжный сервис не ответил вовремя; требуется сверка возврата"
            ) from None
        except (httpx.HTTPError, ValueError):
            raise ProviderError(
                "Платёжный сервис недоступен или вернул некорректный возврат; требуется сверка"
            ) from None
