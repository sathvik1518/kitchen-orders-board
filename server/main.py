"""
The Kitchen App server: a menu, an orders board with cursor paging, creating an order, and marking one ready.

Run:   python -m uvicorn main:app --reload --port 8000
Docs:  http://localhost:8000/docs
Rollback test: set FAIL_RATE=0.3 (30% of "ready" calls fail with a 500). Leave it unset for normal use.
"""
import os
import random

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

# The two places the web page may be served from. Anything else is refused by the browser.
ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

MENU = [
    {"id": 1, "name": "Idli", "price": 40},
    {"id": 2, "name": "Masala Dosa", "price": 80},
    {"id": 3, "name": "Pongal", "price": 60},
    {"id": 4, "name": "Medu Vada", "price": 50},
    {"id": 5, "name": "Rava Upma", "price": 45},
    {"id": 6, "name": "Filter Coffee", "price": 25},
    {"id": 7, "name": "Poori Masala", "price": 70},
    {"id": 8, "name": "Mysore Pak", "price": 55},
]
DISHES = {item["name"] for item in MENU}

FIRST_ORDER_ID = 1001
SEED_COUNT = 50  # more than two pages of 20, so paging is real
MAX_LIMIT = 100


# ---------- what a request must look like (Pydantic rejects anything else with 422) ----------
class OrderLine(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)  # strict: "2" is not a number, True is not a number
    dish: str
    qty: int = Field(ge=1, le=20)


class NewOrder(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    table: int = Field(ge=1, le=40)
    items: list[OrderLine] = Field(min_length=1, max_length=10)


def seed_orders(count: int) -> list[dict]:
    """Predictable fake orders (same every start), mostly 'preparing' and a few 'ready'."""
    orders = []
    for i in range(count):
        first = MENU[i % len(MENU)]["name"]
        second = MENU[(i * 3 + 1) % len(MENU)]["name"]
        items = [{"dish": first, "qty": i % 3 + 1}]
        if i % 2 == 0 and second != first:
            items.append({"dish": second, "qty": 1})
        orders.append(
            {
                "id": FIRST_ORDER_ID + i,
                "table": i % 12 + 1,
                "items": items,
                "status": "ready" if i % 7 == 6 else "preparing",
            }
        )
    return orders


def create_app(seed_count: int = SEED_COUNT, fail_rate: float | None = None, rng: random.Random | None = None) -> FastAPI:
    """
    Builds a server with its own data (so tests never share state).
    fail_rate: chance (0 to 1) that 'mark ready' fails with a 500. None means read FAIL_RATE from the environment.
    """
    if fail_rate is None:
        fail_rate = float(os.environ.get("FAIL_RATE", "0") or 0)
    rng = rng or random.Random()
    orders = seed_orders(seed_count)
    state = {"next_id": FIRST_ORDER_ID + seed_count}

    app = FastAPI(title="Kitchen App")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/menu")
    def get_menu():
        return MENU

    @app.get("/orders")
    def list_orders(limit: int = Query(20, ge=1, le=MAX_LIMIT), after: int | None = Query(None, ge=0)):
        """
        Cursor paging. `after` is the id of the last order you already have.
        Orders are in id order, so 'everything after id X' never skips or repeats, even if new orders arrive.
        `next_cursor` is the id to send next time, or null when there is nothing more.
        """
        remaining = [o for o in orders if after is None or o["id"] > after]
        page = remaining[:limit]
        more = len(remaining) > limit
        return {"items": page, "next_cursor": page[-1]["id"] if more else None}

    @app.post("/orders", status_code=201)
    def create_order(body: NewOrder):
        for line in body.items:
            if line.dish not in DISHES:
                raise HTTPException(status_code=422, detail=f"'{line.dish}' is not on the menu.")
        order = {"id": state["next_id"], "table": body.table, "items": [l.model_dump() for l in body.items], "status": "preparing"}
        state["next_id"] += 1
        orders.append(order)
        return order

    @app.post("/orders/{order_id}/ready")
    def mark_ready(order_id: int):
        if fail_rate and rng.random() < fail_rate:
            raise HTTPException(status_code=500, detail="The ticket printer is jammed.")
        order = next((o for o in orders if o["id"] == order_id), None)
        if order is None:
            raise HTTPException(status_code=404, detail="No such order.")
        if order["status"] == "ready":
            raise HTTPException(status_code=409, detail="That order is already ready.")
        order["status"] = "ready"
        return order

    return app


app = create_app()
