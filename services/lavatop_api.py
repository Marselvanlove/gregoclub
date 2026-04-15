from dataclasses import dataclass
from typing import Any, Optional

import httpx

from utils.config import Config


@dataclass
class LavaTopInvoice:
    id: str
    status: str
    amount: float
    currency: str
    payment_url: Optional[str]
    invoice_type: str = ""
    parent_invoice_id: Optional[str] = None
    buyer_email: Optional[str] = None


class LavaTopClient:
    def __init__(self, api_key: str, base_url: str = "https://gate.lava.top") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Authorization": f"ApiKey {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_invoice(
        self,
        email: str,
        offer_id: str,
        periodicity: str,
        currency: str,
        payment_provider: Optional[str] = None,
        payment_method: Optional[str] = None,
        buyer_language: Optional[str] = None,
    ) -> LavaTopInvoice:
        payload: dict[str, Any] = {
            "email": email,
            "offerId": offer_id,
            "periodicity": periodicity,
            "currency": currency,
        }
        if payment_provider:
            payload["paymentProvider"] = payment_provider
        if payment_method:
            payload["paymentMethod"] = payment_method
        if buyer_language:
            payload["buyerLanguage"] = buyer_language

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v3/invoice",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_invoice(data)

    async def get_invoice(self, invoice_id: str) -> LavaTopInvoice:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v2/invoices/{invoice_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_invoice(data)

    async def cancel_subscription(self, contract_id: str, email: str) -> None:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.delete(
                f"{self.base_url}/api/v1/subscriptions",
                params={"contractId": contract_id, "email": email},
                headers=self.headers,
            )
            response.raise_for_status()

    def _parse_invoice(self, data: dict[str, Any]) -> LavaTopInvoice:
        amount_total = data.get("amountTotal") or {}
        receipt = data.get("receipt") or {}
        parent_invoice = data.get("parentInvoice") or {}
        buyer = data.get("buyer") or {}
        return LavaTopInvoice(
            id=str(data.get("id") or data.get("invoiceId") or ""),
            status=str(data.get("status") or ""),
            amount=float(amount_total.get("amount") or receipt.get("amount") or data.get("totalAmount") or data.get("amount") or 0),
            currency=str(amount_total.get("currency") or receipt.get("currency") or data.get("currency") or "EUR"),
            payment_url=data.get("paymentUrl") or data.get("paymentURL") or data.get("url"),
            invoice_type=str(data.get("type") or data.get("paymentType") or ""),
            parent_invoice_id=str(parent_invoice.get("id") or data.get("parentInvoiceId") or "") or None,
            buyer_email=str(buyer.get("email") or data.get("email") or "") or None,
        )


def init_lavatop(config: Config) -> Optional[LavaTopClient]:
    if not config.lavatop_api_key:
        return None
    return LavaTopClient(api_key=config.lavatop_api_key)


def get_lavatop_offer_id(config: Config, tariff: str) -> str:
    if tariff == "1month":
        return config.lavatop_offer_1_month
    if tariff == "3months":
        return config.lavatop_offer_3_months
    return config.lavatop_offer_6_months


def get_lavatop_periodicity(tariff: str) -> str:
    if tariff == "1month":
        return "MONTHLY"
    if tariff == "3months":
        return "PERIOD_90_DAYS"
    return "PERIOD_180_DAYS"
