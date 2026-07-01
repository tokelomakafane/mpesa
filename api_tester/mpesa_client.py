"""
M-Pesa OpenAPI client — mirrors the portalsdk pattern exactly.

Based on official Vodacom OpenAPI documentation.
The portalsdk is only available as a zip from openapiportal.m-pesa.com,
not on PyPI. This module replicates its behaviour using pycryptodome
and requests so no separate SDK download is needed.

Key facts from official docs:
  - Both sandbox and production use host: openapi.m-pesa.com
  - Sandbox path prefix:    /sandbox/ipg/v2/[market]/
  - Production path prefix: /openapi/ipg/v2/[market]/
  - Bearer token for getSession  = RSA-PKCS1v1.5-encrypt(api_key,    public_key) → base64
  - Bearer token for all others  = RSA-PKCS1v1.5-encrypt(session_id, public_key) → base64
"""

import base64
import uuid
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# -----------------------------------------------------------------------
# Official platform public key (same for sandbox and production)
# Source: openapiportal.m-pesa.com API documentation
# -----------------------------------------------------------------------
PLATFORM_PUBLIC_KEY = (
    "MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEArv9yxA69XQKBo24BaF/D"
    "+fvlqmGdYjqLQ5WtNBb5tquqGvAvG3WMFETVUSow/LizQalxj2ElMVrUmzu5mGGk"
    "xK08bWEXF7a1DEvtVJs6nppIlFJc2SnrU14AOrIrB28ogm58JjAl5BOQawOXD5df"
    "Sk7MaAA82pVHoIqEu0FxA8BOKU+RGTihRU+ptw1j4bsAJYiPbSX6i71gfPvwHPYa"
    "mM0bfI4CmlsUUR3KvCG24rB6FNPcRBhM3jDuv8ae2kC33w9hEq8qNB55uw51vK7h"
    "yXoAa+U7IqP1y6nBdlN25gkxEA8yrsl1678cspeXr+3ciRyqoRgj9RD/ONbJhhxF"
    "vt1cLBh+qwK2eqISfBb06eRnNeC71oBokDm3zyCnkOtMDGl7IvnMfZfEPFCfg5Qg"
    "JVk1msPpRvQxmEsrX9MQRyFVzgy2CWNIb7c+jPapyrNwoUbANlN8adU1m6yOuoX7"
    "F49x+OjiG2se0EJ6nafeKUXw/+hiJZvELUYgzKUtMAZVTNZfT8jjb58j8GVtuS+6"
    "TM2AutbejaCV84ZK58E2CRJqhmjQibEUO6KPdD7oTlEkFy52Y1uOOBXgYpqMzufNP"
    "mfdqqqSM4dU70PO8ogyKGiLAIxCetMjjm6FCMEA3Kc8K0Ig7/XtFm9By6VxTJK1M"
    "g36TlHaZKP6VzVLXMtesJECAwEAAQ=="
)

# -----------------------------------------------------------------------
# Official market table (from API docs)
# Description          | URL Context   | input_Country | input_Currency
# Vodafone Ghana       | vodafoneGHA   | GHA           | GHS
# Vodacom Tanzania     | vodacomTZN    | TZN           | TZS
# Vodacom Lesotho      | vodacomLES    | LES           | LSL
# Vodacom DR Congo     | vodacomDRC    | DRC           | USD
# Vodacom Mozambique   | vodacomMOZ    | MOZ           | MZN
# -----------------------------------------------------------------------
MARKET_CONFIG = {
    "LSO": {"path": "vodacomLES",  "currency": "LSL", "label": "Vodacom Lesotho", "country": "LES"},
    "LES": {"path": "vodacomLES",  "currency": "LSL", "label": "Vodacom Lesotho", "country": "LES"},
    "TZA": {"path": "vodacomTZN",  "currency": "TZS", "label": "Vodacom Tanzania", "country": "TZN"},
    "TZN": {"path": "vodacomTZN",  "currency": "TZS", "label": "Vodacom Tanzania", "country": "TZN"},
    "GHA": {"path": "vodafoneGHA", "currency": "GHS", "label": "Vodafone Ghana",    "country": "GHA"},
    "DRC": {"path": "vodacomDRC",  "currency": "USD", "label": "Vodacom DR Congo",  "country": "DRC"},
    "MOZ": {"path": "vodacomMOZ",  "currency": "MZN", "label": "Vodacom Mozambique", "country": "MOZ"},
}

# Both environments share the same host — only the path prefix differs
API_HOST = "openapi.m-pesa.com"
ENV_PREFIX = {
    "sandbox":    "sandbox",
    "production": "openapi",
    "openapi":    "openapi",   # alias
}


class MpesaClient:
    """
    Equivalent of the portalsdk APIContext + APIRequest pattern.
    """

    def __init__(self, api_key, public_key=None, market="LSO", environment="sandbox"):
        self.api_key = api_key
        self.public_key = public_key or PLATFORM_PUBLIC_KEY
        self.market = market.upper()
        self.environment = environment.lower()

        cfg = MARKET_CONFIG.get(self.market)
        if not cfg:
            raise ValueError(f"Unknown market '{market}'. Valid: {list(MARKET_CONFIG)}")

        self.market_path = cfg["path"]
        self.default_currency = cfg["currency"]
        self.country_code = cfg.get("country", self.market)
        self._session_id = None

    # -------------------------------------------------------------------
    # RSA encryption
    # -------------------------------------------------------------------
    def _wrap_pem(self, key_b64):
        key_b64 = key_b64.strip()
        if key_b64.startswith("-----"):
            return key_b64
        return f"-----BEGIN PUBLIC KEY-----\n{key_b64}\n-----END PUBLIC KEY-----"

    def _rsa_encrypt(self, plaintext: str) -> str:
        pem = self._wrap_pem(self.public_key)
        pub_key = RSA.import_key(pem)
        cipher = PKCS1_v1_5.new(pub_key)
        encrypted = cipher.encrypt(plaintext.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def create_bearer_token(self):
        return self._rsa_encrypt(self.api_key)

    def _session_bearer(self):
        if not self._session_id:
            raise ValueError("No session ID. Call get_session() first.")
        return self._rsa_encrypt(self._session_id)

    # -------------------------------------------------------------------
    # URL builder
    # -------------------------------------------------------------------
    def _build_url(self, endpoint):
        prefix = ENV_PREFIX.get(self.environment, "sandbox")
        # Documentation shows trailing slashes are used
        return f"https://{API_HOST}/{prefix}/ipg/v2/{self.market_path}/{endpoint}/"

    # -------------------------------------------------------------------
    # HTTP helpers
    # -------------------------------------------------------------------
    def _get_headers(self, bearer):
        return {
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "*",
        }

    def _get(self, endpoint, bearer):
        url = self._build_url(endpoint)
        try:
            resp = requests.get(url, headers=self._get_headers(bearer), timeout=30)
            try:
                data = resp.json()
            except ValueError:
                data = {"error": "Invalid JSON response from API", "raw": resp.text[:500]}
            return {"status_code": resp.status_code, "data": data, "url": url}
        except Exception as e:
            return {"status_code": 500, "data": {"error": str(e)}, "url": url}

    def _post(self, endpoint, payload):
        url = self._build_url(endpoint)
        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(self._session_bearer()), timeout=30)
            try:
                data = resp.json()
            except ValueError:
                data = {"error": "Invalid JSON response from API", "raw": resp.text[:500]}
            return {"status_code": resp.status_code, "data": data, "url": url}
        except Exception as e:
            return {"status_code": 500, "data": {"error": str(e)}, "url": url}

    # -------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------
    def get_session(self):
        """
        GET /[env]/ipg/v2/[market]/getSession/
        Returns output_SessionID on success (INS-0).
        """
        result = self._get("getSession", self.create_bearer_token())
        session_id = result["data"].get("output_SessionID", "")
        if session_id:
            self._session_id = session_id
        return result

    # -------------------------------------------------------------------
    # Payment APIs
    # -------------------------------------------------------------------
    def b2b_payment(self, amount, receiver_code, primary_code, reference, description, currency=None):
        return self._post("b2bPayment", {
            "input_Amount": str(amount),
            "input_Country": self.country_code,
            "input_Currency": currency or self.default_currency,
            "input_ReceiverPartyCode": receiver_code,
            "input_PrimaryPartyCode": primary_code,
            "input_ThirdPartyConversationID": uuid.uuid4().hex,
            "input_TransactionReference": reference,
            "input_PurchasedItemsDesc": description,
        })

    def b2c_payment(self, amount, msisdn, service_provider_code, reference, description, currency=None):
        return self._post("b2cPayment", {
            "input_Amount": str(amount),
            "input_Country": self.country_code,
            "input_Currency": currency or self.default_currency,
            "input_CustomerMSISDN": msisdn,
            "input_ServiceProviderCode": service_provider_code,
            "input_ThirdPartyConversationID": uuid.uuid4().hex,
            "input_TransactionReference": reference,
            "input_PaymentItemsDesc": description,
        })

    def c2b_payment(self, amount, msisdn, service_provider_code, reference, description, currency=None):
        # Documentation explicitly requires /singleStage/ for C2B
        return self._post("c2bPayment/singleStage", {
            "input_Amount": str(amount),
            "input_Country": self.country_code,
            "input_Currency": currency or self.default_currency,
            "input_CustomerMSISDN": msisdn,
            "input_ServiceProviderCode": service_provider_code,
            "input_ThirdPartyConversationID": uuid.uuid4().hex,
            "input_TransactionReference": reference,
            "input_PurchasedItemsDesc": description,
        })

    def reversal(self, transaction_id, amount, service_provider_code, description, currency=None):
        return self._post("reversal", {
            "input_ReversalAmount": str(amount),
            "input_Country": self.country_code,
            "input_Currency": currency or self.default_currency,
            "input_ServiceProviderCode": service_provider_code,
            "input_ThirdPartyConversationID": uuid.uuid4().hex,
            "input_TransactionID": transaction_id,
            "input_PurchaseItemsReversal": description,
        })

    def query_transaction_status(self, transaction_id, service_provider_code, currency=None):
        return self._post("queryTransactionStatus", {
            "input_QueryReference": transaction_id,
            "input_ServiceProviderCode": service_provider_code,
            "input_ThirdPartyConversationID": uuid.uuid4().hex,
            "input_Country": self.country_code,
        })
