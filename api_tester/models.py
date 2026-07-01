from django.db import models
from django.db.models import Sum
import json


class MpesaSession(models.Model):
    api_key = models.CharField(max_length=500)
    public_key = models.TextField()
    market = models.CharField(max_length=10, default="LSO")
    environment = models.CharField(max_length=20, default="sandbox")
    session_id = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.market} | {self.environment} | {'Active' if self.is_active else 'Inactive'}"


class TransactionLog(models.Model):
    TX_TYPES = [
        ("b2b", "B2B Single Payment"),
        ("b2c", "B2C Single Payment"),
        ("c2b", "C2B Single Payment"),
        ("reversal", "Reversal"),
        ("tx_status", "TX Status Query"),
        ("direct_debit", "Direct Debit Create"),
        ("session", "Get Session"),
    ]

    tx_type = models.CharField(max_length=20, choices=TX_TYPES)
    request_payload = models.TextField(blank=True)
    response_payload = models.TextField(blank=True)
    response_code = models.CharField(max_length=20, blank=True)
    status_code = models.IntegerField(default=0)
    endpoint_url = models.CharField(max_length=300, blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def request_pretty(self):
        try:
            return json.dumps(json.loads(self.request_payload), indent=2)
        except Exception:
            return self.request_payload

    def response_pretty(self):
        try:
            return json.dumps(json.loads(self.response_payload), indent=2)
        except Exception:
            return self.response_payload

    def __str__(self):
        return f"{self.get_tx_type_display()} | {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class UserAccount(models.Model):
    msisdn = models.CharField(max_length=15, unique=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.msisdn} (Bal: {self.balance})"


class BettingTransaction(models.Model):
    account = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="transactions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=20, choices=[("deposit", "Deposit"), ("withdrawal", "Withdrawal")])
    mpesa_receipt = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def business_earnings(cls):
        # Example: Simple sum of all successful deposits minus withdrawals
        # In a real betting app, this would be based on "House Edge" or bet outcomes.
        deposits = cls.objects.filter(type="deposit", status="completed").aggregate(Sum('amount'))['amount__sum'] or 0
        withdrawals = cls.objects.filter(type="withdrawal", status="completed").aggregate(Sum('amount'))['amount__sum'] or 0
        return deposits - withdrawals
