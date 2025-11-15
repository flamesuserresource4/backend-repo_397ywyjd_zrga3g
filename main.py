import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Product, Order, OrderItem, Customer

app = FastAPI(title="Store SaaS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Store SaaS Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


# -----------------------------
# Store: Customers
# -----------------------------

@app.post("/api/customers")
def create_customer(customer: Customer):
    customer_dict = customer.model_dump()
    customer_id = create_document("customer", customer_dict)
    return {"id": customer_id, **customer_dict}


@app.get("/api/customers")
def list_customers(limit: Optional[int] = 50):
    docs = get_documents("customer", {}, limit)
    # Convert ObjectId to string
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -----------------------------
# Store: Products
# -----------------------------

@app.post("/api/products")
def create_product(product: Product):
    product_dict = product.model_dump()
    product_id = create_document("product", product_dict)
    return {"id": product_id, **product_dict}


@app.get("/api/products")
def list_products(limit: Optional[int] = 50):
    docs = get_documents("product", {}, limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -----------------------------
# Store: Orders
# -----------------------------

class CreateOrderPayload(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    items: List[OrderItem]
    status: Optional[str] = "paid"


@app.post("/api/orders")
def create_order(payload: CreateOrderPayload):
    total_amount = sum(item.price * item.quantity for item in payload.items)
    order = Order(
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        items=payload.items,
        total_amount=total_amount,
        status=payload.status or "paid",
        placed_at=datetime.now(timezone.utc),
    )
    order_dict = order.model_dump()
    order_id = create_document("order", order_dict)
    return {"id": order_id, **order_dict}


@app.get("/api/orders")
def list_orders(limit: Optional[int] = 50):
    docs = get_documents("order", {}, limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -----------------------------
# Analytics
# -----------------------------

@app.get("/api/analytics/overview")
def analytics_overview():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    now = datetime.now(timezone.utc)
    start_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    start_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # Sales today
    pipeline_today = [
        {"$match": {"placed_at": {"$gte": start_today}}},
        {"$group": {"_id": None, "revenue": {"$sum": "$total_amount"}, "orders": {"$count": {}}}},
    ]

    # Sales month-to-date
    pipeline_mtd = [
        {"$match": {"placed_at": {"$gte": start_month}}},
        {"$group": {"_id": None, "revenue": {"$sum": "$total_amount"}, "orders": {"$count": {}}}},
    ]

    today = next(iter(db.order.aggregate(pipeline_today)), None) or {"revenue": 0, "orders": 0}
    mtd = next(iter(db.order.aggregate(pipeline_mtd)), None) or {"revenue": 0, "orders": 0}

    # Average order value MTD
    avg_order_value = 0
    if mtd.get("orders", 0):
        avg_order_value = round(mtd["revenue"] / mtd["orders"], 2)

    # Top products last 30 days
    last_30 = now - timedelta(days=30)
    pipeline_top_products = [
        {"$match": {"placed_at": {"$gte": last_30}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"product_id": "$items.product_id", "title": "$items.title"},
            "quantity": {"$sum": "$items.quantity"},
            "revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": 5}
    ]
    top_products = [
        {
            "product_id": str(p["_id"].get("product_id")),
            "title": p["_id"].get("title"),
            "quantity": p.get("quantity", 0),
            "revenue": round(p.get("revenue", 0), 2),
        }
        for p in db.order.aggregate(pipeline_top_products)
    ]

    # Orders by day (last 14 days)
    start_14 = now - timedelta(days=13)
    pipeline_timeseries = [
        {"$match": {"placed_at": {"$gte": start_14}}},
        {"$project": {
            "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$placed_at"}},
            "total_amount": 1
        }},
        {"$group": {"_id": "$day", "revenue": {"$sum": "$total_amount"}, "orders": {"$count": {}}}},
        {"$sort": {"_id": 1}}
    ]
    series = list(db.order.aggregate(pipeline_timeseries))
    # Ensure all days present
    by_day = {d["_id"]: d for d in series}
    days = [(start_14 + timedelta(days=i)).date().isoformat() for i in range(14)]
    timeseries = [{"day": d, "revenue": float(by_day.get(d, {}).get("revenue", 0)), "orders": int(by_day.get(d, {}).get("orders", 0))} for d in days]

    # Customer segments (by segment field)
    pipeline_segments = [
        {"$group": {"_id": "$segment", "count": {"$count": {}}}},
        {"$sort": {"count": -1}}
    ]
    segments = [
        {"segment": s["_id"] or "Uncategorized", "count": s["count"]}
        for s in db.customer.aggregate(pipeline_segments)
    ]

    return {
        "today_revenue": round(float(today.get("revenue", 0)), 2),
        "today_orders": int(today.get("orders", 0)),
        "mtd_revenue": round(float(mtd.get("revenue", 0)), 2),
        "mtd_orders": int(mtd.get("orders", 0)),
        "avg_order_value": avg_order_value,
        "top_products": top_products,
        "timeseries": timeseries,
        "segments": segments,
    }


# -----------------------------
# Seed demo data
# -----------------------------

@app.post("/api/seed")
def seed_demo_data():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    import random

    # Basic catalogs
    products = [
        {"title": "Wireless Earbuds", "price": 59.99, "category": "Audio", "in_stock": True},
        {"title": "Smartwatch Pro", "price": 129.0, "category": "Wearables", "in_stock": True},
        {"title": "4K Monitor", "price": 279.0, "category": "Displays", "in_stock": True},
        {"title": "Mechanical Keyboard", "price": 89.0, "category": "Peripherals", "in_stock": True},
        {"title": "Gaming Mouse", "price": 49.0, "category": "Peripherals", "in_stock": True},
    ]

    customers = [
        {"name": "Alice Johnson", "email": "alice@example.com", "segment": "Retail"},
        {"name": "Bob Smith", "email": "bob@example.com", "segment": "Wholesale"},
        {"name": "Cara Lee", "email": "cara@example.com", "segment": "VIP"},
        {"name": "Dan Brown", "email": "dan@example.com", "segment": "Retail"},
    ]

    # Insert catalogs if empty
    if db.product.count_documents({}) == 0:
        for p in products:
            create_document("product", p)

    if db.customer.count_documents({}) == 0:
        for c in customers:
            create_document("customer", c)

    # Create random orders last 30 days
    product_docs = list(db.product.find({}))
    customer_docs = list(db.customer.find({}))

    for _ in range(40):
        prod = random.sample(product_docs, k=random.randint(1, 3))
        items = []
        for pr in prod:
            qty = random.randint(1, 3)
            items.append({
                "product_id": str(pr.get("_id")),
                "title": pr.get("title"),
                "price": float(pr.get("price", 0)),
                "quantity": qty,
            })
        total = sum(i["price"] * i["quantity"] for i in items)
        cust = random.choice(customer_docs) if customer_docs else None
        placed_at = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 29))
        order_doc = {
            "customer_id": str(cust.get("_id")) if cust else None,
            "customer_name": cust.get("name") if cust else None,
            "items": items,
            "total_amount": round(total, 2),
            "status": "paid",
            "placed_at": placed_at,
        }
        create_document("order", order_doc)

    return {"status": "ok", "message": "Seeded demo data"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
