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



class Checkout:
    def __init__(self):
        self.supabase = supabase
        self.business_id = BUSINESS_ID

    def check_customer(self, phone):
        """
        Checks if a customer exists for this business using phone number.
        Returns:
            {
                "exists": bool,
                "customer": dict | None
            }
        """
        # clean phone
        phone = self.clean_phone(phone)

        try:
            response = (
                self.supabase
                .table("customers")
                .select("*")
                .eq("business_id", self.business_id)
                .eq("phone", phone)
                .limit(1)
                .execute()
            )

            customer = response.data[0] if response.data else None

            return {
                "exists": customer is not None,
                "customer": customer
            }

        except Exception as e:
            print("Error checking customer:", e)

            return {
                "exists": False,
                "customer": None,
                "error": "Failed to check customer"
            }

    def clean_phone(self, phone: str) -> str:
        """
        Cleans and normalizes a Zambian phone number.

        Accepts:
            +260979991334
            0979 991 334
            0979991334
            260979991334

        Returns:
            0979991334
        """
        if not phone:
            return ""

        # Remove spaces, dashes, and plus signs
        phone = (
            phone.replace(" ", "")
            .replace("-", "")
            .replace("+", "")
        )

        # If number starts with country code 260, convert to 0XXXXXXXXX
        if phone.startswith("260") and len(phone) == 12:
            phone = "0" + phone[3:]

        # Basic validation (Zambia numbers are 10 digits starting with 0)
        if not phone.startswith("0") or len(phone) != 10:
            raise ValueError("Invalid Zambian phone number")

        return phone

    def get_customer(self, phone):
        """
        Fetch a customer by phone number for this business.

        Returns:
            dict | None
        """
        try:
            # Normalize phone number first
            phone = self.clean_phone(phone)

            response = (
                self.supabase
                .table("customers")
                .select("*")
                .eq("business_id", self.business_id)
                .eq("phone", phone)
                .limit(1)
                .execute()
            )

            return response.data[0] if response.data else None

        except ValueError as ve:
            # Phone number validation failed
            print(f"Invalid phone number: {ve}")
            return None

        except Exception as e:
            # Database or unexpected error
            print(f"Error fetching customer: {e}")
            return None

    def create_order(self, customer_id, delivery_location, total_amount):
        """
        Creates an order and returns the created order record.
        Supabase auto-generates the primary key (UUID).
        """
        try:
            payload = {
                "business_id": self.business_id,
                "customer_id": customer_id,
                "total_amount": total_amount,
                "order_status": "pending",
                "order_payment_status": "pending",
                "delivery_location": delivery_location,
                "products": []  # attached later
            }

            response = (
                self.supabase
                .table("orders")
                .insert(payload)
                .execute()
            )

            if not response.data:
                raise Exception("Order insert failed")

            return response.data[0]  # contains auto-generated id

        except Exception as e:
            print("Error creating order:", e)
            return None

    def upload_order_images(self, order_id, cart_items):
        """
        Upload product images to:
        uploaded-files/orders/{order_id}/
        """
        products_json = []

        for item in cart_items:
            image_url = None
            local_path = item.get("local_image_path")

            if local_path:
                filename = os.path.basename(local_path)
                storage_path = f"orders/{order_id}/{filename}"

                with open(local_path, "rb") as f:
                    self.supabase.storage \
                        .from_("uploaded-files") \
                        .upload(storage_path, f.read())

                image_url = (
                    f"{SUPABASE_URL}/storage/v1/object/public/"
                    f"uploaded-files/{storage_path}"
                )

            products_json.append({
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "instruction": item.get("instruction"),
                "image_url": image_url
            })

        return products_json

    def attach_products_to_order(self, order_id, products_json):
        try:
            self.supabase \
                .table("orders") \
                .update({"products": products_json}) \
                .eq("id", order_id) \
                .execute()
        except Exception as e:
            print("Error attaching products:", e)


    def create_customer(self, name, email, phone, location, gender):
        """
        Creates a new customer for this business and returns the customer record.
        """
        try:
            # Normalize phone number
            phone = self.clean_phone(phone)

            payload = {
                "business_id": self.business_id,
                "name": name,
                "email": email,
                "phone": phone,
                "location": location,
                "gender": gender
            }

            response = (
                self.supabase
                .table("customers")
                .insert(payload)
                .execute()
            )

            if not response.data:
                raise Exception("Customer creation failed")

            return response.data[0]

        except ValueError as ve:
            print(f"Customer phone validation failed: {ve}")
            return None

        except Exception as e:
            print(f"Error creating customer: {e}")
            return None


