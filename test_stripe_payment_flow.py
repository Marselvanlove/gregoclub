import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from services.stripe_api import create_checkout_session
from web.stripe_webhook import handle_invoice_payment_succeeded


class StripePaymentFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_checkout_session_stores_subscription_metadata(self):
        session_obj = SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.test/session")
        client = SimpleNamespace(
            checkout=SimpleNamespace(
                sessions=SimpleNamespace(create=MagicMock(return_value=session_obj))
            )
        )
        config = SimpleNamespace(
            stripe_price_1_month="price_1",
            stripe_price_3_months="price_3",
            stripe_price_6_months="price_6",
            bot_username="@gregoclub_bot",
        )

        url = await create_checkout_session(client, config, telegram_id=7834118080, tariff="1month")

        self.assertEqual(url, "https://checkout.stripe.test/session")
        params = client.checkout.sessions.create.call_args.kwargs["params"]
        self.assertEqual(params["client_reference_id"], "7834118080")
        self.assertEqual(params["metadata"]["telegram_id"], "7834118080")
        self.assertEqual(params["subscription_data"]["metadata"]["telegram_id"], "7834118080")
        self.assertEqual(params["subscription_data"]["metadata"]["tariff"], "1month")

    async def test_initial_invoice_recovers_activation_from_subscription_metadata(self):
        invoice = {
            "id": "in_test_1",
            "customer": "cus_test_1",
            "subscription": "sub_test_1",
            "billing_reason": "subscription_create",
            "amount_paid": 4900,
            "lines": {"data": [{"period": {"end": 1775564566}}]},
        }
        subscription = {
            "id": "sub_test_1",
            "metadata": {"telegram_id": "7834118080", "tariff": "1month"},
            "current_period_end": datetime(2026, 4, 7, 12, 22, 46),
        }
        expected_end = datetime(2026, 4, 7, 12, 0, 0)
        gspread_client = object()

        with (
            patch("web.stripe_webhook.get_user_by_stripe_customer_id", new=AsyncMock(return_value=None)),
            patch("web.stripe_webhook.init_stripe", return_value=object()),
            patch("web.stripe_webhook.get_subscription_by_id", new=AsyncMock(return_value=subscription)),
            patch("web.stripe_webhook.calculate_initial_subscription_end", return_value=expected_end),
            patch("web.stripe_webhook.activate_initial_subscription", new=AsyncMock()) as activate_initial,
            patch("web.stripe_webhook.activate_recurring_subscription", new=AsyncMock()) as activate_recurring,
        ):
            await handle_invoice_payment_succeeded(
                invoice,
                session=object(),
                bot=object(),
                config=object(),
                gspread_client=gspread_client,
            )

        activate_initial.assert_awaited_once()
        activate_recurring.assert_not_awaited()
        kwargs = activate_initial.await_args.kwargs
        self.assertEqual(kwargs["telegram_id"], 7834118080)
        self.assertEqual(kwargs["external_payment_id"], "sub_test_1")
        self.assertEqual(kwargs["payment_customer_id"], "cus_test_1")
        self.assertEqual(kwargs["stripe_customer_id"], "cus_test_1")
        self.assertEqual(kwargs["amount"], 49.0)
        self.assertEqual(kwargs["subscription_end"], expected_end)
        self.assertIs(kwargs["gspread_client"], gspread_client)

    async def test_subscription_update_invoice_uses_initial_activation_path(self):
        invoice = {
            "id": "in_test_2",
            "customer": "cus_test_2",
            "subscription": "sub_test_2",
            "billing_reason": "subscription_update",
            "amount_paid": 13200,
            "lines": {"data": []},
        }
        subscription = {
            "id": "sub_test_2",
            "metadata": {"telegram_id": "555", "tariff": "3months"},
            "current_period_end": datetime(2026, 6, 7, 12, 22, 46),
        }
        expected_end = datetime(2026, 6, 7, 12, 0, 0)

        with (
            patch("web.stripe_webhook.get_user_by_stripe_customer_id", new=AsyncMock(return_value=None)),
            patch("web.stripe_webhook.init_stripe", return_value=object()),
            patch("web.stripe_webhook.get_subscription_by_id", new=AsyncMock(return_value=subscription)),
            patch("web.stripe_webhook.calculate_initial_subscription_end", return_value=expected_end),
            patch("web.stripe_webhook.activate_initial_subscription", new=AsyncMock()) as activate_initial,
            patch("web.stripe_webhook.activate_recurring_subscription", new=AsyncMock()) as activate_recurring,
        ):
            await handle_invoice_payment_succeeded(
                invoice,
                session=object(),
                bot=object(),
                config=object(),
            )

        activate_initial.assert_awaited_once()
        activate_recurring.assert_not_awaited()
        kwargs = activate_initial.await_args.kwargs
        self.assertEqual(kwargs["telegram_id"], 555)
        self.assertEqual(kwargs["external_payment_id"], "sub_test_2")
        self.assertEqual(kwargs["amount"], 132.0)
        self.assertEqual(kwargs["subscription_end"], expected_end)

    async def test_recurring_invoice_uses_recurring_activation_path(self):
        invoice = {
            "id": "in_test_3",
            "customer": "cus_test_3",
            "subscription": "sub_test_3",
            "billing_reason": "subscription_cycle",
            "amount_paid": 4900,
            "lines": {"data": [{"period": {"end": 1778166566}}]},
        }
        user = SimpleNamespace(telegram_id=101010, subscription_end_date=datetime(2026, 4, 7, 12, 22, 46))
        expected_end = datetime.utcfromtimestamp(1778166566)

        with (
            patch("web.stripe_webhook.get_user_by_stripe_customer_id", new=AsyncMock(return_value=user)),
            patch("web.stripe_webhook.activate_initial_subscription", new=AsyncMock()) as activate_initial,
            patch("web.stripe_webhook.activate_recurring_subscription", new=AsyncMock()) as activate_recurring,
        ):
            await handle_invoice_payment_succeeded(
                invoice,
                session=object(),
                bot=object(),
                config=object(),
            )

        activate_initial.assert_not_awaited()
        activate_recurring.assert_awaited_once()
        kwargs = activate_recurring.await_args.kwargs
        self.assertEqual(kwargs["telegram_id"], 101010)
        self.assertEqual(kwargs["external_payment_id"], "in_test_3")
        self.assertEqual(kwargs["amount"], 49.0)
        self.assertEqual(kwargs["subscription_end"], expected_end)


if __name__ == "__main__":
    unittest.main()
