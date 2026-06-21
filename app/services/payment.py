import uuid

from app.core.config import settings


async def create_payment_intent(amount_paise: int, order_id: str) -> dict:
    if settings.mock_payments or not settings.stripe_secret_key:
        mock_id = f"pi_mock_{uuid.uuid4().hex[:16]}"
        return {
            "client_secret": f"{mock_id}_secret_mock",
            "payment_intent_id": mock_id,
            "mock": True,
        }

    # Production Stripe integration
    import stripe

    stripe.api_key = settings.stripe_secret_key
    intent = stripe.PaymentIntent.create(
        amount=amount_paise,
        currency="inr",
        metadata={"order_id": order_id},
    )
    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
        "mock": False,
    }


async def confirm_mock_payment(payment_intent_id: str) -> bool:
    return payment_intent_id.startswith("pi_mock_")


async def handle_stripe_webhook(payload: bytes, sig_header: str) -> dict | None:
    if settings.mock_payments:
        return None

    import stripe

    stripe.api_key = settings.stripe_secret_key
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
        return event
    except Exception:
        return None
