"""Schémas HTTP du dashboard backoffice."""

from datetime import datetime

from pydantic import BaseModel


class OrdersKpi(BaseModel):
    total: int
    today: int
    open: int  # ni livrées ni annulées


class RevenueKpi(BaseModel):
    total: int  # encaissé (commandes payées non annulées), en ariary
    this_month: int
    last_month: int


class CustomersKpi(BaseModel):
    total: int
    new_this_month: int


class ProductsKpi(BaseModel):
    active: int
    out_of_stock: int
    low_stock: int


class RecentOrder(BaseModel):
    id: str
    reference: str
    customer_name: str
    total_amount: int
    status: str
    payment_status: str | None
    created_at: datetime
    image_url: str | None
    item_count: int


class MonthlyRevenue(BaseModel):
    month: str  # AAAA-MM
    revenue: int
    orders: int


class BestSeller(BaseModel):
    product_id: str | None
    name: str
    image_url: str | None
    category: str | None
    quantity: int
    revenue: int
    share: float  # part des articles vendus, en %


class ActivityItem(BaseModel):
    order_id: str
    reference: str
    kind: str  # new | paid | confirmed | processing | shipped | completed | cancelled
    customer_name: str
    amount: int
    at: datetime


class BenchmarkAxis(BaseModel):
    """Un axe du radar « ce mois vs mois dernier » (valeurs brutes, normalisées côté graphique)."""

    key: str
    label: str
    unit: str  # ariary | count | percent
    current: float
    previous: float


class DashboardOut(BaseModel):
    orders: OrdersKpi
    revenue: RevenueKpi
    customers: CustomersKpi
    products: ProductsKpi
    recent_orders: list[RecentOrder]
    monthly_revenue: list[MonthlyRevenue]
    best_sellers: list[BestSeller]
    activity: list[ActivityItem]
    benchmark: list[BenchmarkAxis]
