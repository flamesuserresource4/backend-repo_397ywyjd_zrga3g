"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- Order -> "order" collection
- Customer -> "customer" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# -----------------------------
# Core Store Models
# -----------------------------

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Customer(BaseModel):
    """
    Customers collection schema
    Collection: "customer"
    """
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    segment: Optional[str] = Field(None, description="Customer segment like Retail/Wholesale/VIP")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")
    sku: Optional[str] = None

class OrderItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int = Field(..., ge=1)

class Order(BaseModel):
    """
    Orders collection schema
    Collection: "order"
    """
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    items: List[OrderItem]
    total_amount: float = Field(..., ge=0)
    status: str = Field("paid", description="paid, pending, refunded, cancelled")
    placed_at: Optional[datetime] = None

# Add your own schemas below if needed for extensions
