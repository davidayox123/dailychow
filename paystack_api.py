'''
Handles interactions with the Paystack API for payments and transfers.
'''
import requests
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file for API keys
load_dotenv()

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY") # May be needed for some client-side operations or specific SDKs
PAYSTACK_BASE_URL = "https://api.paystack.co"

if not PAYSTACK_SECRET_KEY:
    print("Warning: PAYSTACK_SECRET_KEY not found in environment variables. Paystack features will not work.")

HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type": "application/json"
}

def initialize_transaction(email: str, amount_kobo: int, reference: str, callback_url: str = None):
    """
    Initializes a Paystack transaction.

    Args:
        email: Customer's email.
        amount_kobo: Amount in Kobo (e.g., 1000 NGN = 100000 Kobo).
        reference: Unique transaction reference.
        callback_url: Optional URL to redirect to after payment.

    Returns:
        A dictionary containing the authorization URL and reference, or an error.
    """
    if not PAYSTACK_SECRET_KEY:
        return {"status": False, "message": "Paystack API key not configured."}

    url = f"{PAYSTACK_BASE_URL}/transaction/initialize"
    payload = {
        "email": email,
        "amount": str(amount_kobo), # Paystack API expects amount as string
        "reference": reference,
    }
    if callback_url:
        payload["callback_url"] = callback_url

    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()
        if data.get("status") is True:
            return {
                "status": True,
                "message": "Authorization URL created",
                "data": {
                    "authorization_url": data["data"]["authorization_url"],
                    "access_code": data["data"]["access_code"],
                    "reference": data["data"]["reference"]
                }
            }
        else:
            return {"status": False, "message": data.get("message", "Paystack initialization failed.")}
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if e.response is not None:
            try:
                error_details = e.response.json()
                error_message = f"{error_message} - {error_details.get('message')}"
            except json.JSONDecodeError:
                error_message = f"{error_message} - {e.response.text}"
        print(f"Error initializing Paystack transaction: {error_message}")
        return {"status": False, "message": f"Error initializing transaction: {error_message}"}

def verify_transaction(reference: str):
    """
    Verifies the status of a Paystack transaction.

    Args:
        reference: The transaction reference to verify.

    Returns:
        A dictionary with the transaction status and data, or an error.
    """
    if not PAYSTACK_SECRET_KEY:
        return {"status": False, "message": "Paystack API key not configured."}

    url = f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if data.get("status") is True:
            return {"status": True, "message": data.get("message"), "data": data.get("data")}
        else:
            return {"status": False, "message": data.get("message", "Paystack verification failed."), "data": data.get("data")}
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if e.response is not None:
            try:
                error_details = e.response.json()
                error_message = f"{error_message} - {error_details.get('message')}"
            except json.JSONDecodeError:
                error_message = f"{error_message} - {e.response.text}"
        print(f"Error verifying Paystack transaction: {error_message}")
        return {"status": False, "message": f"Error verifying transaction: {error_message}"}

def create_transfer_recipient(name: str, account_number: str, bank_code: str, currency: str = "NGN"):
    """
    Creates a transfer recipient on Paystack.

    Args:
        name: Name of the recipient.
        account_number: Account number.
        bank_code: Bank code (from Paystack's bank list).
        currency: Currency (defaults to NGN).

    Returns:
        A dictionary with recipient data or an error.
    """
    if not PAYSTACK_SECRET_KEY:
        return {"status": False, "message": "Paystack API key not configured."}

    url = f"{PAYSTACK_BASE_URL}/transferrecipient"
    payload = {
        "type": "nuban",
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": currency
    }
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("status") is True:
            return {"status": True, "message": data.get("message"), "data": data.get("data")}
        else:
            return {"status": False, "message": data.get("message", "Failed to create transfer recipient.")}
    except requests.exceptions.RequestException as e:
        # ... (error handling as above)
        print(f"Error creating transfer recipient: {e}")
        return {"status": False, "message": f"Error creating transfer recipient: {str(e)}"}

def initiate_transfer(amount_kobo: int, recipient_code: str, reason: str, reference: str):
    """
    Initiates a transfer to a Paystack recipient.

    Args:
        amount_kobo: Amount in Kobo.
        recipient_code: The recipient code obtained from create_transfer_recipient.
        reason: Reason for the transfer.
        reference: Unique transfer reference.

    Returns:
        A dictionary with transfer data or an error.
    """
    if not PAYSTACK_SECRET_KEY:
        return {"status": False, "message": "Paystack API key not configured."}

    url = f"{PAYSTACK_BASE_URL}/transfer"
    payload = {
        "source": "balance", # Transfer from your Paystack balance
        "amount": str(amount_kobo),
        "recipient": recipient_code,
        "reason": reason,
        "reference": reference
    }
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("status") is True:
            return {"status": True, "message": data.get("message"), "data": data.get("data")}
        else:
            # Paystack might return true for status but have an error message in data for transfers
            # if data.get("data") and data["data"].get("status") == "otp": # Example: OTP required
            #     return {"status": True, "message": "OTP required for transfer", "data": data.get("data")}
            return {"status": False, "message": data.get("message", "Failed to initiate transfer."), "data": data.get("data")}
    except requests.exceptions.RequestException as e:
        # ... (error handling as above)
        print(f"Error initiating transfer: {e}")
        return {"status": False, "message": f"Error initiating transfer: {str(e)}"}

# You might need a function to list banks if you want users to select them by name
def list_banks(currency: str = "NGN"):
    """
    Lists banks supported by Paystack for a given currency.
    """
    if not PAYSTACK_SECRET_KEY:
        return {"status": False, "message": "Paystack API key not configured."}
    
    url = f"{PAYSTACK_BASE_URL}/bank?currency={currency}"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if data.get("status") is True:
            return {"status": True, "message": data.get("message"), "data": data.get("data")}
        else:
            return {"status": False, "message": data.get("message", "Failed to list banks.")}
    except requests.exceptions.RequestException as e:
        print(f"Error listing banks: {e}")
        return {"status": False, "message": f"Error listing banks: {str(e)}"}

if __name__ == "__main__":
    # Test functions (requires PAYSTACK_SECRET_KEY to be set in .env)
    # Remember to create a .env file with your Paystack test keys:
    # PAYSTACK_SECRET_KEY=sk_test_your_secret_key
    # PAYSTACK_PUBLIC_KEY=pk_test_your_public_key

    if PAYSTACK_SECRET_KEY:
        print("Paystack API Key found. Running example tests (no actual calls made without action)...")

        # Example: Initialize transaction
        # print("\n--- Initialize Transaction Example ---")
        # init_ref = f"budgetbot_test_{int(datetime.now().timestamp())}"
        # init_response = initialize_transaction("testuser@example.com", 500000, init_ref) # 5000 NGN
        # if init_response["status"]:
        #     print(f"Initialization successful: {init_response['data']['authorization_url']}")
        #     # Example: Verify transaction (use the reference from a completed test payment)
        #     # print("\n--- Verify Transaction Example ---")
        #     # verify_response = verify_transaction(init_ref) # Replace with a real reference after payment
        #     # print(f"Verification response: {verify_response}")
        # else:
        #     print(f"Initialization failed: {init_response['message']}")

        # Example: List banks
        # print("\n--- List Banks Example ---")
        # banks_response = list_banks()
        # if banks_response["status"] and banks_response["data"]:
        #     print(f"Found {len(banks_response['data'])} banks. First few:")
        #     for bank in banks_response["data"][:3]:
        #         print(f"- {bank['name']} (Code: {bank['code']})")
        # else:
        #     print(f"Failed to list banks: {banks_response['message']}")

        # Example: Create Transfer Recipient (replace with actual test bank details)
        # print("\n--- Create Transfer Recipient Example ---")
        # recipient_response = create_transfer_recipient("Test User", "0123456789", "058") # 058 is GTBank example
        # if recipient_response["status"]:
        #     recipient_code = recipient_response["data"]["recipient_code"]
        #     print(f"Recipient created: {recipient_code}")
            
        #     # Example: Initiate Transfer (use the recipient_code from above)
        #     # print("\n--- Initiate Transfer Example ---")
        #     # transfer_ref = f"budgetbot_xfer_{int(datetime.now().timestamp())}"
        #     # transfer_response = initiate_transfer(100000, recipient_code, "Daily allowance test", transfer_ref) # 1000 NGN
        #     # print(f"Transfer response: {transfer_response}")
        # else:
        #     print(f"Failed to create recipient: {recipient_response['message']}")
        pass
    else:
        print("Skipping Paystack API tests as PAYSTACK_SECRET_KEY is not set.")
