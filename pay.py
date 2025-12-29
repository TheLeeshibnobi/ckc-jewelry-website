import requests
from typing import Optional

from supabase import create_client, Client
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BUSINESS_ID = os.getenv("BUSINESS_ID")
USER_ID = os.getenv("USER_ID")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Supabase environment variables not set")

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

PAYMENT_BASE_URL = "https://paymentbackend.inxource.com/api/payment"

class Pay:
    def __init__(self):
        self.supabase = supabase
        self.business_id = BUSINESS_ID
    """
        def get_payment_token(self, description, amount):
        url = f"{PAYMENT_BASE_URL}/getToken"
        payload = {
            "description": description,
            "amount": amount
        }

        response = requests.post(url, json=payload, timeout=30)

        if response.status_code != 200:
            raise Exception(f"Failed to get token: {response.text}")

        return response.json()
    """

    def get_payment_token(self, description, amount):
        url = f"{PAYMENT_BASE_URL}/getToken"
        payload = {
            "description": description,
            "amount": amount
        }

        response = requests.post(url, json=payload, timeout=30)

        print("GET TOKEN STATUS:", response.status_code)
        print("GET TOKEN RESPONSE:", response.text)  # 👈 IMPORTANT

        if response.status_code != 200:
            raise Exception(f"Failed to get token: {response.text}")

        return response.json()

    def initiate_payment(self, token, phone_number, order_id):
        url = f"{PAYMENT_BASE_URL}/initiatePayment"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "phoneNumber": phone_number,
            "order_id": order_id
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code != 200:
            raise Exception(f"Payment initiation failed: {response.text}")

        return response.json()



    def check_payment_status(self, order_token):
        url = f"{PAYMENT_BASE_URL}/checkPayment"

        payload = {
            "ordertoken": order_token
        }

        response = requests.post(url, json=payload, timeout=30)

        if response.status_code != 200:
            raise Exception(f"Status check failed: {response.text}")

        return response.json()

    def process_payment(self, order_id, phone, amount):
        token_data = self.get_payment_token(
            description=f"Payment for order {order_id}",
            amount=amount
        )

        data = token_data.get("data", {})
        token = data.get("token")
        payment_link = data.get("paymentLink")

        if not token or not payment_link:
            raise Exception(f"Invalid token response: {token_data}")

        # OPTIONAL: initiate mobile money (only if you want STK push)
        # self.initiate_payment(token, phone, order_id)

        return {
            "token": token,
            "payment_link": payment_link
        }

    def get_order_amount(self, order_id):
        """
        Get the payable amount for an order.
        """
        try:
            response = (
                self.supabase
                .table("orders")
                .select("total_amount")
                .eq("id", order_id)
                .single()
                .execute()
            )

            if not response.data or response.data.get("total_amount") is None:
                raise Exception("Order amount not found")

            return float(response.data["total_amount"])

        except Exception as e:
            print("Error fetching order amount:", e)
            return None


