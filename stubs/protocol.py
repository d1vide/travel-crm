import base64
import hmac


def token(settings, identity):
    digest = hmac.digest(
        settings.payment_stub_key.get_secret_value().encode(),
        b"checkout-v1:" + identity.bytes,
        "sha256",
    )
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def dto(settings, row):
    return {
        "id": str(row.id),
        "client_operation_id": str(row.client_operation_id),
        "amount": f"{row.amount:.2f}",
        "currency": row.currency,
        "status": row.status,
        "checkout_token": token(settings, row.client_operation_id),
        "failure_reason": "Тестовый отказ платёжного сервиса" if row.status == "failed" else None,
        "succeeded_at": row.succeeded_at.isoformat().replace("+00:00", "Z")
        if row.succeeded_at is not None
        else None,
    }
