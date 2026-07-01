import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .mpesa_client import MpesaClient
from .models import MpesaSession, TransactionLog, UserAccount, BettingTransaction


def _get_active_session_obj():
    return MpesaSession.objects.filter(is_active=True).first()


def _get_client_from_session(session_obj):
    client = MpesaClient(
        api_key=session_obj.api_key,
        public_key=session_obj.public_key,
        market=session_obj.market,
        environment=session_obj.environment,
    )
    client._session_id = session_obj.session_id
    return client


def _log(tx_type, request_data, result):
    response_data = result.get("data", {})
    response_code = response_data.get("output_ResponseCode", "")
    success = result.get("status_code") in [200, 201] and response_code == "INS-0"
    TransactionLog.objects.create(
        tx_type=tx_type,
        request_payload=json.dumps(request_data),
        response_payload=json.dumps(response_data),
        response_code=response_code,
        status_code=result.get("status_code", 0),
        endpoint_url=result.get("url", ""),
        success=success,
    )
    return success


def index(request):
    active_session = _get_active_session_obj()
    recent_logs = TransactionLog.objects.all()[:20]
    markets = [
        ("LSO", "Vodacom Lesotho"),
        ("TZN", "Vodacom Tanzania"),
        ("GHA", "Vodafone Ghana"),
        ("DRC", "Vodacom DR Congo"),
        ("MOZ", "Vodacom Mozambique"),
    ]

    # Betting-specific data
    accounts = UserAccount.objects.all()
    business_made = BettingTransaction.business_earnings()

    context = {
        "active_session": active_session,
        "recent_logs": recent_logs,
        "markets": markets,
        "accounts": accounts,
        "business_made": business_made,
    }
    return render(request, "api_tester/index.html", context)


@require_POST
def get_session(request):
    api_key = request.POST.get("api_key", "").strip()
    public_key = request.POST.get("public_key", "").strip()
    market = request.POST.get("market", "LSO")
    environment = request.POST.get("environment", "sandbox")

    if not api_key or not public_key:
        return JsonResponse({"error": "API Key and Public Key are required."}, status=400)

    client = MpesaClient(api_key=api_key, public_key=public_key, market=market, environment=environment)
    try:
        result = client.get_session()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    session_id = result["data"].get("output_SessionID", "")
    success = result["status_code"] == 200 and session_id

    # Deactivate all old sessions
    MpesaSession.objects.all().update(is_active=False)

    session_obj = MpesaSession.objects.create(
        api_key=api_key,
        public_key=public_key,
        market=market,
        environment=environment,
        session_id=session_id,
        is_active=bool(success),
    )

    _log("session", {"market": market, "environment": environment}, result)

    return JsonResponse({
        "success": bool(success),
        "session_id": session_id[:20] + "..." if session_id else "",
        "response": result["data"],
        "status_code": result["status_code"],
    })

# -------------------------------------------------------------------
# Betting Platform Logic
# -------------------------------------------------------------------

@require_POST
def betting_deposit(request):
    """
    Automates: Customer MSISDN -> C2B Payment -> Increase User Balance
    """
    msisdn = request.POST.get("msisdn")
    amount = request.POST.get("amount")

    session_obj = _get_active_session_obj()
    if not session_obj:
        return JsonResponse({"error": "No active session"}, status=400)

    client = _get_client_from_session(session_obj)

    # 1. Trigger C2B
    result = client.c2b_payment(
        amount=amount,
        msisdn=msisdn,
        service_provider_code="000000",
        reference="DEPOSIT",
        description="Betting App Deposit"
    )

    success = _log("c2b", {"msisdn": msisdn, "amount": amount}, result)

    if success:
        acc, _ = UserAccount.objects.get_or_create(msisdn=msisdn)
        amt_dec = Decimal(amount)
        acc.balance += amt_dec
        acc.save()

        BettingTransaction.objects.create(
            account=acc,
            amount=amt_dec,
            type="deposit",
            status="completed",
            mpesa_receipt=result["data"].get("output_TransactionID", "")
        )
        return JsonResponse({"success": True, "balance": str(acc.balance)})

    return JsonResponse({"success": False, "response": result["data"]}, status=400)


@require_POST
def betting_withdraw(request):
    """
    Automates: Press Withdraw -> Check Balance -> B2C Payment -> Decrease Balance
    """
    msisdn = request.POST.get("msisdn")
    amount = request.POST.get("amount")

    try:
        amt_dec = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"error": "Invalid amount"}, status=400)

    acc = UserAccount.objects.filter(msisdn=msisdn).first()
    if not acc or acc.balance < amt_dec:
        return JsonResponse({"error": f"Insufficient balance. Your current balance is {acc.balance if acc else 0} LSL."}, status=400)

    session_obj = _get_active_session_obj()
    if not session_obj:
        return JsonResponse({"error": "No active session"}, status=400)

    client = _get_client_from_session(session_obj)

    # 1. Trigger B2C (Business to Customer)
    result = client.b2c_payment(
        amount=amount,
        msisdn=msisdn,
        service_provider_code="000000",
        reference="WITHDRAW",
        description="Betting App Withdrawal"
    )

    success = _log("b2c", {"msisdn": msisdn, "amount": amount}, result)

    if success:
        amt_dec = Decimal(amount)
        acc.balance -= amt_dec
        acc.save()

        BettingTransaction.objects.create(
            account=acc,
            amount=amt_dec,
            type="withdrawal",
            status="completed",
            mpesa_receipt=result["data"].get("output_TransactionID", "")
        )
        return JsonResponse({"success": True, "balance": str(acc.balance)})

    return JsonResponse({"success": False, "response": result["data"]}, status=400)

# -------------------------------------------------------------------
# Raw API Tester (Existing logic)
# -------------------------------------------------------------------

@require_POST
def b2b_payment(request):
    session_obj = _get_active_session_obj()
    if not session_obj: return JsonResponse({"error": "No session"}, status=400)
    client = _get_client_from_session(session_obj)
    payload = {
        "amount": request.POST.get("amount"),
        "receiver_code": request.POST.get("receiver_code"),
        "primary_code": request.POST.get("primary_code"),
        "reference": request.POST.get("reference"),
        "description": request.POST.get("description"),
    }
    result = client.b2b_payment(**payload)
    _log("b2b", payload, result)
    return JsonResponse({"success": result["status_code"] in [200, 201], "response": result["data"]})

@require_POST
def b2c_payment(request):
    session_obj = _get_active_session_obj()
    if not session_obj: return JsonResponse({"error": "No session"}, status=400)
    client = _get_client_from_session(session_obj)
    payload = {
        "amount": request.POST.get("amount"),
        "msisdn": request.POST.get("msisdn"),
        "service_provider_code": request.POST.get("service_provider_code"),
        "reference": request.POST.get("reference"),
        "description": request.POST.get("description"),
    }
    result = client.b2c_payment(**payload)
    _log("b2c", payload, result)
    return JsonResponse({"success": result["status_code"] in [200, 201], "response": result["data"]})

@require_POST
def c2b_payment(request):
    session_obj = _get_active_session_obj()
    if not session_obj: return JsonResponse({"error": "No session"}, status=400)
    client = _get_client_from_session(session_obj)
    payload = {
        "amount": request.POST.get("amount"),
        "msisdn": request.POST.get("msisdn"),
        "service_provider_code": request.POST.get("service_provider_code"),
        "reference": request.POST.get("reference"),
        "description": request.POST.get("description"),
    }
    result = client.c2b_payment(**payload)
    _log("c2b", payload, result)
    return JsonResponse({"success": result["status_code"] in [200, 201], "response": result["data"]})


@require_POST
def reversal(request):
    session_obj = _get_active_session_obj()
    if not session_obj: return JsonResponse({"error": "No active session"}, status=400)
    client = _get_client_from_session(session_obj)
    payload = {
        "transaction_id": request.POST.get("transaction_id"),
        "amount": request.POST.get("amount"),
        "service_provider_code": request.POST.get("service_provider_code"),
        "description": request.POST.get("description"),
    }
    result = client.reversal(**payload)
    _log("reversal", payload, result)
    return JsonResponse({"success": result["status_code"] in [200, 201], "response": result["data"]})


@require_POST
def query_status(request):
    session_obj = _get_active_session_obj()
    if not session_obj: return JsonResponse({"error": "No active session"}, status=400)
    client = _get_client_from_session(session_obj)
    payload = {
        "transaction_id": request.POST.get("transaction_id"),
        "service_provider_code": request.POST.get("service_provider_code"),
    }
    result = client.query_transaction_status(**payload)
    _log("tx_status", payload, result)
    return JsonResponse({"success": result["status_code"] in [200, 201], "response": result["data"]})


def clear_logs(request):
    TransactionLog.objects.all().delete()
    return redirect("index")

def clear_session(request):
    MpesaSession.objects.all().update(is_active=False)
    return redirect("index")
