from dotenv import load_dotenv
load_dotenv()
import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_compress import Compress

from cart import Cart
from products import Products
from checkout import Checkout

cart = Cart()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
Compress(app)
email_user = os.getenv('EMAIL_USER')
email_password = os.getenv('EMAIL_KEY')



@app.context_processor
def inject_cart():
    return {
        "number_of_items": len(cart.items),
        "accumulated_total": cart.accumulated_total
    }


@app.route('/')
def home():
    products_service = Products()
    products = products_service.get_products()

    return render_template(
        'index.html',
        products=products
    )

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    data = request.json

    result = cart.add_to_cart(
        product_id=data["id"],
        name=data["name"],
        price=data["price"],
        image=data["image"]
    )

    return jsonify(result)


@app.route("/checkout")
def checkout():
    return render_template(
        "checkout.html",
        cart=cart.items,
        cart_count=len(cart.items),
        cart_total=cart.accumulated_total
    )


@app.route("/update-quantity", methods=["POST"])
def update_quantity():
    data = request.json

    result = cart.update_quantity(
        product_id=data["product_id"],
        quantity=data["quantity"]
    )

    return jsonify(result)


@app.route("/remove-from-cart", methods=["POST"])
def remove_from_cart():
    data = request.json or {}
    product_id = data.get("product_id")

    result = cart.remove_from_cart(product_id)
    return jsonify(result)




@app.route("/customer", methods=["GET", "POST"])
def customer():
    checkout = Checkout()

    # SHOW FORM
    if request.method == "GET":
        # If no phone in session, user should not be here
        if not session.get("checkout_phone"):
            return redirect(url_for("checkout"))

        return render_template("customer.html")

    # HANDLE FORM SUBMISSION
    if request.method == "POST":
        try:
            phone = session.get("checkout_phone")
            if not phone:
                return redirect(url_for("checkout"))

            name = request.form.get("name")
            email = request.form.get("email")
            location = request.form.get("location")
            gender = request.form.get("gender")

            customer = checkout.create_customer(
                name=name,
                email=email,
                phone=phone,
                location=location,
                gender=gender
            )

            if not customer:
                # Later we can show an error message
                return redirect(url_for("customer"))

            # Store customer_id for order creation
            session["customer_id"] = customer["id"]

            return redirect(url_for("payout"))

        except Exception as e:
            print("Customer route error:", e)
            return redirect(url_for("customer"))


@app.route("/pay-now", methods=["POST"])
def pay_now():
    checkout = Checkout()

    try:
        phone = request.form.get("phone")

        if not phone:
            return redirect(url_for("checkout"))

        # Check customer
        result = checkout.check_customer(phone)

        # Store normalized phone for later steps
        session["checkout_phone"] = checkout.clean_phone(phone)

        if result["exists"]:
            # Existing customer
            session["customer_id"] = result["customer"]["id"]
            return redirect(url_for("payout"))

        # New customer
        session.pop("customer_id", None)
        return redirect(url_for("customer"))

    except Exception as e:
        print("Pay now error:", e)
        return redirect(url_for("checkout"))





@app.route("/payout")
def payout():
    # -------------------------------
    # BASIC GUARDS
    # -------------------------------
    if not session.get("customer_id"):
        return redirect(url_for("checkout"))

    checkout = Checkout()

    # -------------------------------
    # ORDER CREATION GUARD (refresh-safe)
    # -------------------------------
    if session.get("order_id"):
        order_id = session["order_id"]

        try:
            # pull order from DB so totals stay correct even if cart is cleared
            resp = (
                checkout.supabase
                .table("orders")
                .select("id,total_amount,products,delivery_location,order_status,order_payment_status")
                .eq("id", order_id)
                .limit(1)
                .execute()
            )

            order = resp.data[0] if resp.data else None
            if not order:
                # if order missing, reset session and restart flow
                session.pop("order_id", None)
                return redirect(url_for("checkout"))

            products = order.get("products") or []
            number_of_items = sum((p.get("quantity") or 0) for p in products) if products else 0

            return render_template(
                "payout.html",
                accumulated_total=order.get("total_amount", 0),
                number_of_items=number_of_items
            )

        except Exception as e:
            print("Payout guard fetch error:", e)
            return redirect(url_for("checkout"))

    # If we're here, no existing order yet — we must have cart items to create one
    if not cart.items:
        return redirect(url_for("checkout"))

    try:
        customer_id = session.get("customer_id")
        delivery_location = session.get("delivery_location", "")
        total_amount = cart.accumulated_total

        # -------------------------------
        # PREPARE CART ITEMS FOR ORDER
        # -------------------------------
        cart_items = []
        for item in cart.items:
            cart_items.append({
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "instruction": item.get("instruction"),
                "local_image_path": item.get("local_image_path")
            })

        # -------------------------------
        # CREATE ORDER (DB ONLY)
        # -------------------------------
        order = checkout.create_order(
            customer_id=customer_id,
            delivery_location=delivery_location,
            total_amount=total_amount
        )

        if not order:
            return redirect(url_for("checkout"))

        order_id = order["id"]

        # -------------------------------
        # UPLOAD IMAGES + BUILD PRODUCTS JSON
        # -------------------------------
        products_json = checkout.upload_order_images(
            order_id=order_id,
            cart_items=cart_items
        )

        # -------------------------------
        # ATTACH PRODUCTS TO ORDER
        # -------------------------------
        checkout.attach_products_to_order(
            order_id=order_id,
            products_json=products_json
        )

        # -------------------------------
        # CLEAN UP TEMP FILES
        # -------------------------------
        for item in cart_items:
            local_path = item.get("local_image_path")
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception as e:
                    print("Temp file cleanup error:", e)

        # -------------------------------
        # SAVE ORDER ID (GUARD) BEFORE clearing cart
        # -------------------------------
        session["order_id"] = order_id

        # -------------------------------
        # CLEAR CART (IMPORTANT)
        # -------------------------------
        cart.items = []
        cart.accumulated_total = 0

        # calculate number of items (sum quantities)
        number_of_items = sum((p.get("quantity") or 0) for p in products_json) if products_json else 0

        return render_template(
            "payout.html",
            accumulated_total=total_amount,
            number_of_items=number_of_items
        )

    except Exception as e:
        print("Payout route error:", e)
        return redirect(url_for("checkout"))





@app.route('/paid')
def paid():
    return render_template('paid.html')


@app.route('/reviews')
def reviews():
    return render_template('index.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')



if __name__ == '__main__':
    app.run(debug=True)