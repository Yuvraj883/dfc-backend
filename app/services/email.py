import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str) -> bool:
    if settings.mock_email:
        logger.info("MOCK EMAIL to=%s subject=%s body=%s", to, subject, body[:200])
        return True

    # Production: integrate SendGrid/SES
    logger.warning("Email not configured; skipping send to %s", to)
    return False


async def send_order_confirmation(email: str, order_id: str, total: float, guest_token: Optional[str] = None) -> None:
    link = f"{settings.frontend_url}/orders/{order_id}"
    if guest_token:
        link += f"?token={guest_token}"
    body = f"Your DFC order #{str(order_id)[:8]} is confirmed. Total: ₹{total:.2f}. Track: {link}"
    await send_email(email, "Order Confirmed — Delhi Fried Chicken", body)


async def send_reservation_confirmation(
    email: str, name: str, date_str: str, time_str: str, cancel_token: str
) -> None:
    cancel_link = f"{settings.frontend_url}/reservations/cancel?token={cancel_token}"
    body = (
        f"Hi {name}, your table at Delhi Fried Chicken is booked for {date_str} at {time_str}. "
        f"Cancel/reschedule: {cancel_link}"
    )
    await send_email(email, "Reservation Confirmed — Delhi Fried Chicken", body)


async def send_reservation_reminder(email: str, name: str, date_str: str, time_str: str) -> None:
    body = f"Reminder: Hi {name}, your DFC reservation is tomorrow at {time_str} on {date_str}."
    await send_email(email, "Reservation Reminder — Delhi Fried Chicken", body)
