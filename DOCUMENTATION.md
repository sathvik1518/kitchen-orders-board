# Kitchen Orders Board: A FastAPI Server and a React Client That Fetches, Pages and Updates Safely

**Day 27 Mini Capstone, Data Fetching**  
**Project folder:** `kitchen-orders-board`

---

## 1. Goal

The Orders board of the Kitchen App, backed by its own FastAPI server, proved with numbers. The task (Day 27 Deep Dive, Mini Capstone) asked for:

1. **Server:** `GET /menu`, `GET /orders?limit=20&after=<id>` (cursor paging), `POST /orders` (returns 201, rejects bad input with 422), `POST /orders/{id}/ready`. Two origins allowed with `CORSMiddleware`. At least 45 orders seeded.
2. **API helper:** one `api` function that checks `res.ok`, throws one kind of error, and supports cancel through `signal`.
3. **Reading data:** the order list uses `useInfiniteQuery` with a "Load more" button. The menu uses `useQuery` with a `staleTime` you can explain. Clear loading, error and empty states.
4. **Writing data:** a "Mark ready" button with an optimistic update. If the server fails, the order goes back and the user sees a short message. After the write settles, the list is refreshed from the server.
5. **Safety:** validate every response with Zod. A malformed body shows a friendly message, not a blank page.
6. **Tests:** MSW tests for loading, success, a 500 and a malformed body.
7. **Proof, as numbers:** (1) how many `/menu` requests happen when you switch tabs and come back inside `staleTime`, and after it; (2) that the browser sent a preflight and the server answered it; (3) that a failed "Mark ready" rolls back.

Think of a restaurant with a waiter and a kitchen. The waiter (the React page) does not walk to the kitchen for every question. The menu board is written once and trusted for a while (`staleTime`). The order slips are fetched twenty at a time, with a bookmark ("continue after slip 1020") instead of a page number, so a new slip arriving does not shuffle the pile. When the waiter says "table 4 is ready" he writes it on the board at once, and if the kitchen says "no", he crosses it out and tells the guest. Then he checks the real list again.

The rules this project is built around:

- **`fetch` does not fail on a 404 or 500.** The helper checks `res.ok` itself and turns every failure into one error type.
- **A cancel is not a failure.** It passes through untouched, so the library can ignore it.
- **Never trust the server's shape.** Zod checks every answer. Wrong shape means a friendly message.
- **Optimistic does not mean trusting.** Show the change now, roll back if it fails, and always reload from the server afterwards.
- **Prove it with numbers, not with "it seems to work".**

---

## 2. Tools

| Tool | Role |
|---|---|
| FastAPI 0.162 + Uvicorn | The server: `/menu`, `/orders`, `/orders/{id}/ready`, CORS |
| Pydantic 2 (inside FastAPI) | Rejects bad input with 422 (`extra="forbid"`, `strict=True`) |
| Pytest + FastAPI TestClient | Server tests, including the CORS preflight |
| React 19 + Vite | The page |
| TanStack Query 5 | `useQuery` (menu), `useInfiniteQuery` (orders), `useMutation` (Mark ready) |
| Zod 4 | Checks every response |
| Vitest + jsdom + React Testing Library + MSW | Client tests with a fake server that can be held back, made to fail, or made to lie |
| Playwright (Chromium), optional | `web/scripts/check-browser.mjs`: measures the three proof numbers against the real server |

---

## 3. Project structure

```
kitchen-orders-board/
├── .gitignore
├── README.md
├── DOCUMENTATION.md
├── server/
│   ├── main.py               (the whole server, built by create_app)
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pytest.ini
│   └── tests/
│       └── test_server.py
└── web/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    ├── scripts/
    │   └── check-browser.mjs  (real-browser proof, optional)
    └── src/
        ├── config.js          (API_URL)
        ├── api.js             (ApiError and the one api() function)
        ├── schemas.js         (Zod schemas)
        ├── queryKeys.js       (every query key, in one small file)
        ├── queryClient.js     (retry rule)
        ├── hooks.js           (useMenu, useOrders, useMarkReady)
        ├── App.jsx, main.jsx, styles.css
        ├── api.test.js, queryClient.test.js, App.test.jsx
        └── test/
            ├── setup.js, server.js, render.jsx
```

---

## 4. Setup commands

```bash
# server
cd kitchen-orders-board/server
python -m venv venv
venv\Scripts\activate          # Windows.  Mac/Linux: source venv/bin/activate
pip install -r requirements-dev.txt

# web
cd ../web
npm install
```

**`package.json` scripts**

```json
"dev": "vite",
"build": "vite build",
"preview": "vite preview",
"test": "vitest run",
"proof": "node scripts/check-browser.mjs"
```

---

## 5. The idea: three kinds of fetching, each with its own rule

```
 React page                              FastAPI server
 ──────────                              ──────────────
 useQuery(["menu"])        staleTime 5 min   ── GET /menu
 useInfiniteQuery(["orders"])  staleTime 0   ── GET /orders?limit=20            (page 1)
        "Load more" ──▶ pageParam = last id  ── GET /orders?limit=20&after=1020 (page 2)
 useMutation  "Mark ready"                   ── OPTIONS /orders/1001/ready  (preflight, by the browser)
        onMutate   cancel reloads, remember old status, show "ready" now
                                             ── POST    /orders/1001/ready
        onError    put that one order back, show a short message
        onSettled  reload ["orders"] from the server
```

**Why two staleTimes.** The menu changes a few times a year, so it is trusted for 5 minutes: switching tabs inside that time makes no request. The orders board keeps the default of 0, because a kitchen needs the truth: every return to the tab reloads it.

**Why a cursor and not a page number.** `after=1020` means "everything after order 1020". If a new order arrives while you read page 1, page 2 still starts in the right place. With page numbers, a new order would push one order onto the next page and you would see it twice.

**How the cursor flows.** The server returns `{items, next_cursor}`. `getNextPageParam` hands `next_cursor` back to the next request, and returns `undefined` when it is `null`, which tells TanStack Query there are no more pages and removes the button.

**Why the rollback restores one order, not a snapshot of the list.** The usual recipe saves the whole list and puts it back on error. But if two orders are marked at once and one fails, restoring the whole list would also undo the one that worked. Here `onMutate` remembers only that order's old status and `onError` puts back only that.

**Why `onMutate` cancels running reloads.** A reload that started before the click carries the old picture. If it lands after the optimistic update, it would overwrite "Ready" with "Preparing" for a moment. `cancelQueries` stops that, and the API helper lets the cancel pass through untouched.

**Why `onSettled`, not `onSuccess`.** On success the reload confirms the change. On failure it confirms the rollback. Either way, the screen shows what the server holds. It is not returned, so the error message appears at once instead of after the reload.

**Why a POST triggers a preflight.** A POST that sends `Content-Type: application/json` is not a "simple" request. Before sending it, the browser asks the server with `OPTIONS` whether the page's origin may do that. The server answers with the allowed origin and methods. If it said no, the POST would never be sent.

**Why Zod.** TypeScript types do not exist at run time, so they cannot stop a wrong answer. Zod checks the real data. A wrong shape becomes one friendly error ("The server sent unexpected data.") that the screen already knows how to show.

---

## 6. The code

### `server/main.py` (the whole server)

```python
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
```

### `server/requirements.txt`

```text
fastapi==0.162.0
uvicorn==0.54.0
```

### `server/requirements-dev.txt`

```text
-r requirements.txt
pytest==9.1.1
httpx==0.28.1
```

### `server/pytest.ini`

```ini
[pytest]
pythonpath = .
testpaths = tests
```

### `web/src/config.js`

```js
// Where the FastAPI server lives. Override with VITE_API_URL when you build for another place.
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
```

### `web/src/api.js` (the one request function and its error)

```js
import { API_URL } from "./config";

/** The ONE kind of error the app throws. status 0 means "never got an answer" (offline, server down). */
export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const UNEXPECTED_DATA = "The server sent unexpected data.";

const isAbort = (err) => err?.name === "AbortError";

/**
 * One function for every request.
 *   path    "/menu"
 *   method  "GET" (default) or "POST"
 *   body    an object, sent as JSON
 *   signal  lets the caller cancel (TanStack Query passes one, so leaving a page cancels its request)
 *   schema  a Zod schema the answer must match
 * Throws ApiError for every failure. The ONE exception is a cancel, which is rethrown as it is,
 * because a cancel is not a failure and the caller must be able to tell.
 */
export async function api(path, { method = "GET", body, signal, schema } = {}) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      // A JSON content type on a POST is what makes the browser send a CORS preflight (OPTIONS) first.
      headers: method === "GET" ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (isAbort(err)) throw err;
    throw new ApiError("Could not reach the server.", 0);
  }

  // fetch does NOT throw on 404 or 500. That is why res.ok is checked by hand.
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      // the error body was not JSON: fall through to the generic message
    }
    throw new ApiError(typeof detail === "string" ? detail : `Request failed (${res.status}).`, res.status);
  }

  let data;
  try {
    data = await res.json();
  } catch (err) {
    if (isAbort(err)) throw err;
    throw new ApiError(UNEXPECTED_DATA, res.status);
  }

  if (schema) {
    const result = schema.safeParse(data);
    if (!result.success) throw new ApiError(UNEXPECTED_DATA, res.status);
    return result.data;
  }
  return data;
}
```

### `web/src/schemas.js` (Zod)

```js
import { z } from "zod";

// What the server PROMISES to send. If a response does not match, the app says so instead of showing garbage or crashing.
export const menuItemSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  price: z.number(),
});
export const menuSchema = z.array(menuItemSchema);

export const orderSchema = z.object({
  id: z.number().int(),
  table: z.number().int(),
  items: z.array(z.object({ dish: z.string(), qty: z.number().int() })),
  status: z.enum(["preparing", "ready"]),
});

export const ordersPageSchema = z.object({
  items: z.array(orderSchema),
  next_cursor: z.number().int().nullable(),
});
```

### `web/src/queryKeys.js` (every key in one place)

```js
// Every query key in the app, in one place. A typo in a key is a bug that hides: the cache just misses.
export const keys = {
  menu: ["menu"],
  orders: ["orders"],
};
```

### `web/src/queryClient.js` (retry rule)

```js
import { QueryClient } from "@tanstack/react-query";

// Retry once, and only when trying again could help: no answer at all (0) or a server fault (5xx).
// A 404, a 422 or a wrong-shape answer will fail the same way again, so retrying only makes the error appear later.
export const shouldRetry = (failureCount, error) => failureCount < 1 && (error?.status === 0 || error?.status >= 500);

export function createQueryClient(overrides = {}) {
  return new QueryClient({
    defaultOptions: { queries: { retry: shouldRetry, ...overrides } },
  });
}
```

### `web/src/hooks.js` (menu, infinite orders, optimistic Mark ready)

```js
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { keys } from "./queryKeys";
import { menuSchema, orderSchema, ordersPageSchema } from "./schemas";

export const PAGE_SIZE = 20;

/**
 * The menu changes a few times a year, so it is fresh for 5 minutes.
 * Inside that time, switching tabs and coming back makes NO request. After it, coming back refetches once.
 * (The orders board is the opposite: it keeps the default staleTime of 0, because a kitchen needs fresh data.)
 */
export const MENU_STALE_MS = 5 * 60 * 1000;

export function useMenu() {
  return useQuery({
    queryKey: keys.menu,
    queryFn: ({ signal }) => api("/menu", { signal, schema: menuSchema }),
    staleTime: MENU_STALE_MS,
  });
}

/** Orders, 20 at a time. `after` is the id of the last order we already have. */
export function useOrders() {
  return useInfiniteQuery({
    queryKey: keys.orders,
    queryFn: ({ pageParam, signal }) =>
      api(`/orders?limit=${PAGE_SIZE}${pageParam == null ? "" : `&after=${pageParam}`}`, { signal, schema: ordersPageSchema }),
    initialPageParam: null,
    // The server says where the next page starts, or null at the end. undefined tells TanStack Query "no more".
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

// ---- helpers for the cached list (a list of pages, each with items) ----
function mapOrders(data, fn) {
  if (!data) return data;
  return { ...data, pages: data.pages.map((page) => ({ ...page, items: page.items.map(fn) })) };
}
function findOrder(data, id) {
  return data?.pages.flatMap((p) => p.items).find((o) => o.id === id);
}
const setStatus = (queryClient, id, status) =>
  queryClient.setQueryData(keys.orders, (data) => mapOrders(data, (o) => (o.id === id ? { ...o, status } : o)));

/**
 * "Mark ready" with an optimistic update:
 *   onMutate   stop any running reload (it would overwrite us), remember the old status, show "ready" at once
 *   onError    put back ONLY this order's old status
 *   onSettled  whether it worked or not, reload from the server so the screen shows the truth
 * Rolling back one order (not the whole list) matters: if two orders are marked at once and one fails,
 * restoring a whole-list snapshot would also undo the one that worked.
 */
export function useMarkReady() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => api(`/orders/${id}/ready`, { method: "POST", schema: orderSchema }),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: keys.orders });
      const previous = findOrder(queryClient.getQueryData(keys.orders), id)?.status ?? "preparing";
      setStatus(queryClient, id, "ready");
      return { previous };
    },
    onError: (_error, id, context) => {
      setStatus(queryClient, id, context.previous);
    },
    // Not returned on purpose: the screen already shows the new state, so there is nothing to wait for.
    // Returning the promise would hold the error message back until the reload finished (a slow reload = a late message).
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: keys.orders });
    },
  });
}
```

### `web/src/App.jsx`

```jsx
import { useMenu, useMarkReady, useOrders } from "./hooks";

function Menu() {
  const { data, isPending, isError, isRefetchError, error, refetch, isFetching } = useMenu();

  let body;
  if (isPending) body = <p role="status">Loading menu…</p>;
  else if (isError && !data)
    body = (
      <div role="alert">
        <p>Could not load the menu: {error.message}</p>
        <button type="button" onClick={() => refetch()} disabled={isFetching}>
          Try again
        </button>
      </div>
    );
  else if (data.length === 0) body = <p>The menu is empty.</p>;
  else
    body = (
      <>
        {isRefetchError && (
          <p role="alert" className="error">
            Could not refresh the menu: {error.message} Showing the last menu we have.
          </p>
        )}
        <ul className="menu">
          {data.map((item) => (
            <li key={item.id}>
              {item.name} <span className="muted">₹{item.price}</span>
            </li>
          ))}
        </ul>
      </>
    );

  return (
    <section aria-labelledby="menu-title">
      <h2 id="menu-title">Menu</h2>
      {body}
    </section>
  );
}

function OrderRow({ order }) {
  const markReady = useMarkReady();
  const isReady = order.status === "ready";
  return (
    <li className="order" data-testid={`order-${order.id}`}>
      <div className="order__head">
        <strong>
          Table {order.table} · Order #{order.id}
        </strong>
        <span className={`badge badge--${order.status}`}>{isReady ? "Ready" : "Preparing"}</span>
      </div>
      <ul>
        {order.items.map((line) => (
          <li key={line.dish}>
            {line.qty} × {line.dish}
          </li>
        ))}
      </ul>
      {!isReady && (
        <button type="button" onClick={() => markReady.mutate(order.id)} aria-label={`Mark order ${order.id} ready`}>
          Mark ready
        </button>
      )}
      {markReady.isError && (
        <p role="alert" className="error">
          Could not mark order #{order.id} ready, so it was put back. {markReady.error.message}
        </p>
      )}
    </li>
  );
}

function Orders() {
  const { data, isPending, isError, isRefetchError, error, refetch, isFetching, fetchNextPage, hasNextPage, isFetchingNextPage, isFetchNextPageError } =
    useOrders();

  if (isPending)
    return (
      <section aria-labelledby="orders-title">
        <h2 id="orders-title">Orders</h2>
        <p role="status">Loading orders…</p>
      </section>
    );

  if (isError && !data)
    return (
      <section aria-labelledby="orders-title">
        <h2 id="orders-title">Orders</h2>
        <div role="alert">
          <p>Could not load orders: {error.message}</p>
          <button type="button" onClick={() => refetch()} disabled={isFetching}>
            Try again
          </button>
        </div>
      </section>
    );

  const orders = data.pages.flatMap((page) => page.items);

  return (
    <section aria-labelledby="orders-title">
      <h2 id="orders-title">Orders</h2>
      {isRefetchError && <p role="alert" className="error">Could not refresh the orders: {error.message} Showing the last list we have.</p>}
      {orders.length === 0 ? (
        <p>No orders yet.</p>
      ) : (
        <>
          <p role="status">Showing {orders.length} orders</p>
          <ul className="orders">
            {orders.map((order) => (
              <OrderRow key={order.id} order={order} />
            ))}
          </ul>
        </>
      )}
      {isFetchNextPageError && <p role="alert" className="error">Could not load more orders: {error.message}</p>}
      {hasNextPage ? (
        <button type="button" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? "Loading more…" : "Load more"}
        </button>
      ) : (
        orders.length > 0 && <p className="muted">That is every order.</p>
      )}
    </section>
  );
}

export default function App() {
  return (
    <main>
      <h1>Kitchen orders board</h1>
      <Menu />
      <Orders />
    </main>
  );
}
```

### `web/src/main.jsx`

```jsx
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { createQueryClient } from "./queryClient";
import "./styles.css";

const queryClient = createQueryClient();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

### `web/src/styles.css`

```css
body { font-family: system-ui, sans-serif; margin: 0; background: #faf7f2; color: #1c1917; }
main { max-width: 760px; margin: 0 auto; padding: 16px; }
h1 { font-size: 1.75rem; }
.muted { color: #57534e; }
.error { color: #b91c1c; }
.menu { display: flex; flex-wrap: wrap; gap: 8px 20px; padding: 0; list-style: none; }
.orders { padding: 0; list-style: none; display: grid; gap: 12px; }
.order { background: #fff; border: 1px solid #78716c; border-radius: 10px; padding: 12px 16px; }
.order__head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.order ul { margin: 8px 0; padding-left: 20px; }
.badge { border: 1px solid currentColor; border-radius: 999px; padding: 2px 10px; font-size: 0.8rem; font-weight: 600; }
.badge--preparing { background: #fef3c7; color: #78350f; }
.badge--ready { background: #dcfce7; color: #14532d; }
button { min-height: 44px; min-width: 44px; padding: 0 16px; border-radius: 8px; border: 1px solid #78716c; background: #fff; font: inherit; font-weight: 600; cursor: pointer; }
button:disabled { opacity: 0.6; cursor: not-allowed; }
```

### `web/vite.config.js` (ports and test setup)

```js
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The server only allows the page from port 5173 (CORS), so the page must always be there.
  server: { port: 5173, strictPort: true },
  preview: { port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    include: ["src/**/*.test.{js,jsx}"],
  },
});
```

### `web/scripts/check-browser.mjs` (real-browser proof)

```js
// Real-browser proof (Chromium) against the REAL FastAPI server and the real Vite dev server.
// It measures the three numbers the capstone asks for, and a few more:
//   1. /menu requests when you switch tabs and come back, inside staleTime and after it
//   2. the CORS preflight (OPTIONS) for "Mark ready" (read from the server's own log)
//   3. a failed "Mark ready" rolls back (with the server failing 100% of the time, then ~30%)
// Run (server dependencies installed, `npm install` done):   node scripts/check-browser.mjs
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

// The numbers are measured on the PRODUCTION build (vite preview). In `npm run dev`, React's StrictMode mounts every
// component twice on purpose, which cancels and repeats the first request and would add one to every count.
const WEB = "http://localhost:5173";
const API = "http://localhost:8000";
let passed = 0, failed = 0;
const check = (name, ok, detail = "") => {
  ok ? passed++ : failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : "  -> " + detail}`);
};
const info = (text) => console.log(`      ${text}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const procs = [];
const stop = () => procs.splice(0).forEach((p) => p.kill());

async function waitFor(url) {
  for (let i = 0; i < 80; i++) {
    try { if ((await fetch(url)).status < 500) return; } catch {}
    await sleep(250);
  }
  throw new Error(`${url} did not start`);
}
function startApi(failRate) {
  const log = [];
  const p = spawn("python3", ["-m", "uvicorn", "main:app", "--port", "8000"], { cwd: new URL("../../server", import.meta.url).pathname, env: { ...process.env, FAIL_RATE: String(failRate) } });
  p.stdout.on("data", (d) => log.push(...d.toString().split("\n")));
  p.stderr.on("data", (d) => log.push(...d.toString().split("\n")));
  procs.push(p);
  return { log, stop: () => { p.kill(); procs.splice(procs.indexOf(p), 1); } };
}
const hidden = (page, hide) => page.evaluate((h) => {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (h ? "hidden" : "visible") });
  document.dispatchEvent(new Event("visibilitychange"));
  window.dispatchEvent(new Event("visibilitychange"));
}, hide);
const switchTabs = async (page) => { await hidden(page, true); await hidden(page, false); await sleep(600); };
const rowStatus = (page, id) => page.$eval(`[data-testid="order-${id}"] .badge`, (el) => el.textContent);

try {
  mkdirSync("check-output", { recursive: true });
  const webDir = new URL("..", import.meta.url).pathname;
  execFileSync("npx", ["vite", "build"], { cwd: webDir, stdio: "ignore" });
  const web = spawn("npx", ["vite", "preview", "--port", "5173", "--strictPort"], { cwd: webDir, stdio: "ignore" });
  procs.push(web);
  const browser = await chromium.launch();

  // ================= Part A: normal server =================
  let api = startApi(0);
  await waitFor(`${API}/menu`); await waitFor(WEB);
  let ctx = await browser.newContext({ viewport: { width: 900, height: 1000 } });
  let page = await ctx.newPage();
  const seen = [];
  page.on("request", (r) => r.url().startsWith(API) && seen.push(`${r.method()} ${r.url().replace(API, "")}`));
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const count = (prefix) => seen.filter((s) => s.startsWith(prefix)).length;

  await page.goto(WEB);
  await page.waitForSelector("text=Showing 20 orders");
  check("menu: 1 request on first load", count("GET /menu") === 1, String(count("GET /menu")));
  check("the server has at least 45 orders: first page shows 20", (await page.$$("[data-testid^=order-]")).length === 20);

  const ordersBefore = count("GET /orders");
  await switchTabs(page); await switchTabs(page);
  const menuInside = count("GET /menu");
  info(`NUMBER 1a: /menu requests after switching tabs twice INSIDE staleTime = ${menuInside - 1} new (total ${menuInside})`);
  check("menu: switching tabs inside staleTime makes 0 new requests", menuInside === 1, String(menuInside));
  check("orders (staleTime 0) DO reload when you come back", count("GET /orders") > ordersBefore);

  await page.evaluate(() => { const real = Date.now; Date.now = () => real() + 6 * 60 * 1000; }); // 6 minutes later
  await switchTabs(page);
  const menuAfter = count("GET /menu");
  info(`NUMBER 1b: /menu requests after coming back AFTER staleTime (5 min) = ${menuAfter - menuInside} new (total ${menuAfter})`);
  check("menu: coming back after staleTime makes exactly 1 new request", menuAfter === 2, String(menuAfter));

  // paging
  await page.getByRole("button", { name: "Load more" }).click();
  await page.waitForSelector("text=Showing 40 orders");
  await page.getByRole("button", { name: "Load more" }).click();
  await page.waitForSelector("text=Showing 50 orders");
  check("paging: 20, then 40, then 50, and the button is gone", (await page.getByRole("button", { name: "Load more" }).count()) === 0);
  check("paging: the cursor was sent (after=1020 and after=1040)", seen.includes("GET /orders?limit=20&after=1020") && seen.includes("GET /orders?limit=20&after=1040"), seen.filter((s) => s.includes("after")).join(", "));
  check("no order is shown twice", new Set(await page.$$eval("[data-testid^=order-]", (els) => els.map((e) => e.dataset.testid))).size === 50);

  // preflight
  const target = 1001;
  await page.getByRole("button", { name: `Mark order ${target} ready` }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="order-1001"] .badge')?.textContent === "Ready");
  await sleep(500);
  const optionsLine = api.log.find((l) => l.includes(`OPTIONS /orders/${target}/ready`));
  const postLine = api.log.find((l) => l.includes(`POST /orders/${target}/ready`));
  info(`NUMBER 2: server log shows  ${optionsLine?.trim()}`);
  info(`                          and  ${postLine?.trim()}`);
  check("the server answered the preflight (OPTIONS) with 200", !!optionsLine && optionsLine.includes("200"), String(optionsLine));
  check("the POST came after the preflight and succeeded (200)", !!postLine && postLine.includes("200") && api.log.indexOf(postLine) > api.log.indexOf(optionsLine));
  check("the preflight came from localhost:5173 (the browser allowed the call)", (await rowStatus(page, target)) === "Ready");
  const preflight = (origin) => execFileSync("curl", ["-si", "-X", "OPTIONS", `${API}/orders/1002/ready`, "-H", `Origin: ${origin}`, "-H", "Access-Control-Request-Method: POST", "-H", "Access-Control-Request-Headers: content-type"]).toString();
  const good = preflight("http://localhost:5173");
  check("the preflight answer carries Access-Control-Allow-Origin: http://localhost:5173", /access-control-allow-origin: http:\/\/localhost:5173/i.test(good), good.split("\n").slice(0, 6).join(" | "));
  check("...and allows POST", /access-control-allow-methods:.*POST/i.test(good));
  check("the second allowed origin (127.0.0.1:5173) works too", /access-control-allow-origin: http:\/\/127.0.0.1:5173/i.test(preflight("http://127.0.0.1:5173")));
  const bad = preflight("http://evil.example");
  check("a preflight from another origin is refused (400, no allow header)", /^HTTP\/1.1 400/.test(bad) && !/access-control-allow-origin/i.test(bad), bad.split("\n")[0]);
  await page.screenshot({ path: "check-output/dashboard.png" });

  // friendly messages for bad answers
  await page.route(`${API}/menu`, (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ not: "a menu" }) }));
  await page.evaluate(() => { const real = Date.now; Date.now = () => real() + 20 * 60 * 1000; });
  await switchTabs(page);
  await page.waitForSelector("text=/The server sent unexpected data/");
  check("a malformed /menu shows the friendly message", true);
  check("...and the page is not blank (heading and orders are still there)", (await page.getByRole("heading", { name: "Kitchen orders board" }).count()) === 1 && (await page.$$("[data-testid^=order-]")).length > 0);
  await page.screenshot({ path: "check-output/malformed.png" });
  check("no console errors from the app in part A (malformed menu aside)", errors.filter((e) => !/Failed to load resource/.test(e)).length === 0, errors.join(" | "));
  await ctx.close(); api.stop(); await sleep(600);

  // ================= Part B: the server always fails "Mark ready" =================
  api = startApi(1);
  await waitFor(`${API}/menu`);
  ctx = await browser.newContext({ viewport: { width: 900, height: 1000 } });
  page = await ctx.newPage();
  await page.route(`${API}/orders/*/ready`, async (route) => { await sleep(1200); await route.continue(); }); // slow, so the instant update can be seen
  await page.goto(WEB);
  await page.waitForSelector("text=Showing 20 orders");
  await page.evaluate(() => {
    window.__seq = [];
    const badge = document.querySelector('[data-testid="order-1001"] .badge');
    new MutationObserver(() => window.__seq.push(badge.textContent)).observe(badge, { childList: true, characterData: true, subtree: true });
  });
  const t0 = Date.now();
  await page.getByRole("button", { name: "Mark order 1001 ready" }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="order-1001"] .badge')?.textContent === "Ready");
  const instantMs = Date.now() - t0;
  await page.screenshot({ path: "check-output/optimistic.png" });
  check("Mark ready shows Ready right away (the server is still thinking: it was held 1.2 s)", instantMs < 600, `${instantMs} ms`);
  await page.waitForSelector("text=/put back/");
  await sleep(300);
  const seq = await page.evaluate(() => window.__seq);
  info(`NUMBER 3: the order's badge went through: Preparing -> ${seq.join(" -> ")}`);
  check("the badge went Ready, then back to Preparing", seq[0] === "Ready" && seq.at(-1) === "Preparing", seq.join(","));
  check("a short message explains it", (await page.locator('[data-testid="order-1001"]').innerText()).includes("Could not mark order #1001 ready, so it was put back."));
  check("the Mark ready button is back so it can be tried again", (await page.getByRole("button", { name: "Mark order 1001 ready" }).count()) === 1);
  check("the server really did NOT change it (a reload shows Preparing)", (await (await fetch(`${API}/orders?limit=1`)).json()).items[0].status === "preparing");
  await page.screenshot({ path: "check-output/rollback.png" });
  await ctx.close(); api.stop(); await sleep(600);

  // ================= Part C: about 30% of "Mark ready" calls fail =================
  api = startApi(0.3);
  await waitFor(`${API}/menu`);
  ctx = await browser.newContext({ viewport: { width: 900, height: 1000 } });
  page = await ctx.newPage();
  await page.goto(WEB);
  await page.waitForSelector("text=Showing 20 orders");
  let fails = 0, oks = 0, wrong = 0;
  const ids = [1001, 1002, 1003, 1004, 1005, 1006, 1008, 1009, 1010, 1011, 1012, 1013, 1015, 1016, 1017, 1018, 1019, 1020];
  for (const id of ids) {
    await page.getByRole("button", { name: `Mark order ${id} ready` }).click();
    await page.waitForFunction((i) => !document.querySelector(`[data-testid="order-${i}"]`).innerText.includes("Mark ready") || document.querySelector(`[data-testid="order-${i}"]`).innerText.includes("put back"), id);
    await sleep(900);
    const text = await page.locator(`[data-testid="order-${id}"]`).innerText();
    const status = await rowStatus(page, id);
    const server = (await (await fetch(`${API}/orders?limit=20`)).json()).items.find((o) => o.id === id).status;
    if (text.includes("put back")) { fails++; if (status !== "Preparing" || server !== "preparing") wrong++; }
    else { oks++; if (status !== "Ready" || server !== "ready") wrong++; }
  }
  info(`NUMBER 3b: with the server failing about 30% of the time: ${fails} of ${ids.length} failed and rolled back, ${oks} worked`);
  check("every failure rolled back and every success stayed (screen and server agree)", wrong === 0, `${wrong} mismatches`);
  check("some failed and some worked (so both paths were really used)", fails > 0 && oks > 0, `${fails}/${oks}`);
  await ctx.close(); api.stop();
  await browser.close();
} catch (err) {
  failed++;
  console.log("FAIL  the script crashed:", err.message);
} finally {
  stop();
}
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
```

### Design decisions

| Decision | Reason |
|---|---|
| `create_app()` builds the server with its own data | Each test gets a fresh server, so tests never share state. `app = create_app()` is what Uvicorn runs. |
| Seed: 50 orders with ids 1001 to 1050, every 7th already ready | More than two pages of 20, with both statuses, and the same every start. |
| Cursor = the id of the last order you have (`after`) | Orders are in id order, so "after 1020" never skips or repeats, even when new orders arrive. |
| `next_cursor` is `null` when nothing is left, including when the last page is exactly full | The button must not promise a page that is empty. A test pins the exactly-40-orders case. |
| `limit` is 1 to 100, `after` is 0 or more | A request for a million rows, or a negative cursor, is a 422 instead of a slow or odd answer. |
| `POST /orders` returns 201, and 422 for bad input | 201 means "created". 422 means "I understood the request but the content is wrong". |
| `extra="forbid"` and `strict=True` on the order models | A stray field (`status: ready`) or `"3"` for a number is refused instead of quietly accepted. |
| A dish that is not on the menu is a 422 that names the dish | The person sees which dish is wrong. |
| Mark ready: 404 for an unknown order, 409 for an already ready one | Each failure has its own meaning, and the client shows the server's reason. |
| `FAIL_RATE` makes "Mark ready" fail a chosen share of the time | This is the rollback test from the task. It is off by default and only affects that one route. |
| CORS lists two origins: `localhost:5173` and `127.0.0.1:5173` | Both are the same page to a person, but different origins to a browser. |
| CORS allows only GET and POST and the `Content-Type` header | Least permission needed. A DELETE or a custom header is refused at the preflight. |
| The page always runs on port 5173 (`strictPort`) | The server only allows that origin. A silent move to port 5174 would break every request. |
| `api()` has one error type, `ApiError`, with a `status` | The screen needs one `catch`. Status 0 means "no answer" (offline), and the number says why otherwise. |
| A cancel is rethrown as it is, not wrapped | A cancel is not a failure. TanStack Query must be able to tell, and the screen must not show an error for it. |
| `api()` reads the server's `detail` only when it is a string | FastAPI's own 422 has a list. A list in an error message would be unreadable, so a plain message is used. |
| An error body that is not JSON (a 502 page) still gives a clean message | A proxy error page must not crash the error handling. |
| A POST always sends `Content-Type: application/json`; a GET sends no content type | This is what makes the browser send the preflight for the POST, and keeps GETs free of it. |
| Zod objects are not strict (extra fields are ignored) | The server may add fields later without breaking the page. Missing or wrong-typed fields are caught. |
| `next_cursor` must be present (a number or `null`) | A missing field would look like "no more pages" and quietly hide the rest of the orders. |
| Menu `staleTime` is 5 minutes, in one named constant | The number is easy to find, explain and test. |
| Orders keep `staleTime` 0 | The board must be fresh. Every return to the tab reloads it. |
| Retry once, and only for status 0 or 5xx | A 404, 422 or wrong-shape answer will fail the same way, so retrying only delays the message. |
| All query keys are in `queryKeys.js` | A typo in a key does not error. The cache just misses, and the bug hides. |
| Rollback restores one order, not the whole list | Two orders at once, one failing, must not undo the one that worked. A test pins it. |
| `onMutate` cancels running reloads first | An older reload landing late would overwrite the optimistic change. |
| `onSettled` reloads after success and after failure | The screen always ends up showing what the server holds. |
| `onSettled` does not return the reload | The error message appears at once. Returning it would hold the message back until the reload ended. |
| Each order row has its own mutation | A failure message belongs to the order that failed, and one failure does not block the others. |
| `Load more` is disabled and says "Loading more…" while fetching | A double click cannot ask for the same page twice. |
| A failed "Load more" keeps the orders, shows why, and the button works again | One bad request must not throw away the 20 orders already on screen. |
| A failed reload with data on screen shows a message and keeps the old list (menu and orders) | Blank screens and silent stale data are both bad. The person is told the list may be old. |
| The first-load error is a full message with Try again, but the page heading stays | "No blank page" is a stated requirement. |
| Numbers are measured on the production build | In `npm run dev`, React's StrictMode mounts everything twice on purpose, which cancels and repeats the first request and adds one to every count. |

---

## 7. Tests (131 tests)

Server tests run the real FastAPI app through its `TestClient`. Client tests run the whole page against **MSW**, a fake server that answers the real `fetch` calls. A test can hold an answer back (to look at the screen while the server is "thinking"), make it fail, or make it lie (a malformed body). A held answer falls through to the normal handler afterwards, so the server's data really changes. `src/test/setup.js` fails any test that causes a `console.error`. Held tests wait until the save and reload finish, so nothing leaks into the next test.

| # | Test | What it proves |
|---|---|---|
| server (62) | Menu shape; seed of at least 45 with unique ids and both statuses; paging (20, 20, 10; no repeats or gaps; last page has no cursor; an exactly full last page has no cursor; a past-the-end cursor; a new order does not shift pages; 6 bad paging inputs; limit 100 allowed); create (201 and body; id counting up; 18 kinds of bad input are 422; unknown dish names the dish; a refused order is not stored; not JSON); ready (200; stays ready in the list; 404; 409; non-number id); `FAIL_RATE` (1 always fails and changes nothing; 0 never fails; about 30% at 0.3; only that route fails; read from the environment); CORS (two origins; a preflight succeeds for each; another origin refused; the allow header on a normal response; none for another origin; an unlisted header or method refused) | Server |
| api.test.js (21) | Success body; no content type on a GET; JSON on a POST; the content type on a bodiless POST (this is what triggers the preflight); every non-OK status throws `ApiError` and keeps the status; the server's reason is used when it is a string; a list reason gets a plain message; a non-JSON error body; a network failure is status 0; a 200 that is not JSON; a wrong shape; a wrong type inside; a matching body is parsed; a cancel is not an `ApiError`; an already cancelled signal | API helper |
| queryClient.test.js (8) | Retry once for no answer or 5xx; never for 404, 409, 422 or a wrong-shape answer; the client can be told not to retry; keys are distinct arrays; menu `staleTime` is 5 minutes; pages are 20 | Settings |
| App.test.jsx: menu (8) | Loading then dishes and prices; failure with the reason and Try again; empty; malformed body shows a friendly message and the page is not blank; wrong price type; not JSON; no answer; a later failed reload keeps the old menu and says so | Menu |
| App.test.jsx: staleTime (4) | One request on load; tab switches inside `staleTime` make none; coming back after it makes exactly one; the orders board reloads every time | The proof numbers |
| App.test.jsx: orders (15) | Loading then 20; contents of a card; the first request has no cursor; Load more sends the last id; the last page shows 10, removes the button and says that is every order; no order appears twice; Loading more is disabled; a failed Load more keeps the list; a failed first load and Try again; malformed body; an unknown status; a missing cursor; no orders; a failed reload keeps the old list | Orders |
| App.test.jsx: Mark ready (14) | Ready shows before the server answers; only that order changes; success sends one request and reloads; failure rolls back with a message; Ready first, then back; a reload after a failure; try again after a failure; a 404; two orders at once with one failing; other orders keep their state; works on page 2 and keeps both pages; page 2 rolls back; a reload already running does not overwrite the change; the rollback works before the reload answers | Optimistic update |

### `server/tests/test_server.py`

```python
import random

import pytest
from fastapi.testclient import TestClient

from main import ALLOWED_ORIGINS, MENU, create_app


@pytest.fixture()
def client():
    return TestClient(create_app(fail_rate=0))


def all_pages(client, limit=20):
    """Follows next_cursor to the end. Returns the list of pages."""
    pages, after = [], None
    while True:
        params = {"limit": limit} | ({"after": after} if after is not None else {})
        page = client.get("/orders", params=params).json()
        pages.append(page)
        after = page["next_cursor"]
        if after is None:
            return pages


GOOD = {"table": 3, "items": [{"dish": "Idli", "qty": 2}]}


class TestMenu:
    def test_returns_the_menu(self, client):
        res = client.get("/menu")
        assert res.status_code == 200
        assert res.json() == MENU

    def test_each_dish_has_id_name_and_price(self, client):
        for item in client.get("/menu").json():
            assert set(item) == {"id", "name", "price"}


class TestSeed:
    def test_at_least_45_orders(self, client):
        assert sum(len(p["items"]) for p in all_pages(client, 100)) >= 45

    def test_ids_are_unique(self, client):
        ids = [o["id"] for p in all_pages(client) for o in p["items"]]
        assert len(ids) == len(set(ids))

    def test_has_both_statuses(self, client):
        statuses = {o["status"] for p in all_pages(client) for o in p["items"]}
        assert statuses == {"preparing", "ready"}


class TestPaging:
    def test_first_page_has_20_and_a_cursor(self, client):
        page = client.get("/orders?limit=20").json()
        assert len(page["items"]) == 20
        assert page["next_cursor"] == page["items"][-1]["id"]

    def test_default_limit_is_20(self, client):
        assert len(client.get("/orders").json()["items"]) == 20

    def test_pages_are_20_20_10(self, client):
        assert [len(p["items"]) for p in all_pages(client)] == [20, 20, 10]

    def test_no_order_repeats_or_goes_missing(self, client):
        ids = [o["id"] for p in all_pages(client) for o in p["items"]]
        assert ids == sorted(set(ids))
        assert ids == list(range(1001, 1001 + 50))

    def test_last_page_has_no_cursor(self, client):
        assert all_pages(client)[-1]["next_cursor"] is None

    def test_exactly_full_last_page_has_no_cursor(self):
        # 40 orders at 20 per page: the second page is full AND last. It must not promise a third.
        pages = all_pages(TestClient(create_app(seed_count=40, fail_rate=0)))
        assert [len(p["items"]) for p in pages] == [20, 20]
        assert pages[-1]["next_cursor"] is None

    def test_after_past_the_end_is_an_empty_page(self, client):
        assert client.get("/orders?after=999999").json() == {"items": [], "next_cursor": None}

    def test_a_new_order_does_not_shift_pages(self, client):
        first = client.get("/orders?limit=20").json()
        client.post("/orders", json=GOOD)
        second = client.get(f"/orders?limit=20&after={first['next_cursor']}").json()
        assert second["items"][0]["id"] == first["items"][-1]["id"] + 1

    @pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-1", "limit=abc", "after=abc", "after=-5"])
    def test_bad_paging_input_is_422(self, client, query):
        assert client.get(f"/orders?{query}").status_code == 422

    def test_limit_100_is_allowed(self, client):
        assert client.get("/orders?limit=100").status_code == 200


class TestCreate:
    def test_returns_201_and_the_order(self, client):
        res = client.post("/orders", json=GOOD)
        assert res.status_code == 201
        body = res.json()
        assert body["status"] == "preparing"
        assert body["table"] == 3
        assert body["items"] == [{"dish": "Idli", "qty": 2}]

    def test_the_new_order_shows_up_at_the_end(self, client):
        new_id = client.post("/orders", json=GOOD).json()["id"]
        assert new_id == 1051
        assert all_pages(client)[-1]["items"][-1]["id"] == new_id

    def test_ids_keep_counting_up(self, client):
        a = client.post("/orders", json=GOOD).json()["id"]
        b = client.post("/orders", json=GOOD).json()["id"]
        assert b == a + 1

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"table": 3},
            {"items": [{"dish": "Idli", "qty": 1}]},
            {"table": 3, "items": []},
            {"table": 0, "items": [{"dish": "Idli", "qty": 1}]},
            {"table": 41, "items": [{"dish": "Idli", "qty": 1}]},
            {"table": "3", "items": [{"dish": "Idli", "qty": 1}]},
            {"table": True, "items": [{"dish": "Idli", "qty": 1}]},
            {"table": 3.5, "items": [{"dish": "Idli", "qty": 1}]},
            {"table": 3, "items": [{"dish": "Idli", "qty": 0}]},
            {"table": 3, "items": [{"dish": "Idli", "qty": 21}]},
            {"table": 3, "items": [{"dish": "Idli", "qty": "2"}]},
            {"table": 3, "items": [{"dish": "Idli"}]},
            {"table": 3, "items": [{"qty": 1}]},
            {"table": 3, "items": [{"dish": 5, "qty": 1}]},
            {"table": 3, "items": [{"dish": "Idli", "qty": 1}] * 11},
            {"table": 3, "items": [{"dish": "Idli", "qty": 1}], "status": "ready"},
            {"table": 3, "items": [{"dish": "Idli", "qty": 1, "price": 1}]},
        ],
    )
    def test_bad_input_is_422(self, client, body):
        assert client.post("/orders", json=body).status_code == 422

    def test_a_dish_not_on_the_menu_is_422_and_says_which(self, client):
        res = client.post("/orders", json={"table": 3, "items": [{"dish": "Pizza", "qty": 1}]})
        assert res.status_code == 422
        assert "Pizza" in res.json()["detail"]

    def test_a_refused_order_is_not_stored(self, client):
        client.post("/orders", json={"table": 3, "items": [{"dish": "Pizza", "qty": 1}]})
        assert sum(len(p["items"]) for p in all_pages(client, 100)) == 50

    def test_not_json_at_all_is_422(self, client):
        assert client.post("/orders", content="hello", headers={"Content-Type": "application/json"}).status_code == 422


class TestReady:
    def first_preparing(self, client):
        return next(o for p in all_pages(client) for o in p["items"] if o["status"] == "preparing")

    def test_marks_it_ready_and_returns_it(self, client):
        order = self.first_preparing(client)
        res = client.post(f"/orders/{order['id']}/ready")
        assert res.status_code == 200
        assert res.json()["status"] == "ready"

    def test_it_stays_ready_in_the_list(self, client):
        order = self.first_preparing(client)
        client.post(f"/orders/{order['id']}/ready")
        listed = next(o for p in all_pages(client) for o in p["items"] if o["id"] == order["id"])
        assert listed["status"] == "ready"

    def test_unknown_order_is_404(self, client):
        assert client.post("/orders/424242/ready").status_code == 404

    def test_already_ready_is_409(self, client):
        order = self.first_preparing(client)
        client.post(f"/orders/{order['id']}/ready")
        assert client.post(f"/orders/{order['id']}/ready").status_code == 409

    def test_a_non_number_id_is_422(self, client):
        assert client.post("/orders/abc/ready").status_code == 422


class TestFailureForTesting:
    def test_fail_rate_1_always_fails_and_changes_nothing(self):
        client = TestClient(create_app(fail_rate=1))
        res = client.post("/orders/1001/ready")
        assert res.status_code == 500
        assert "jammed" in res.json()["detail"]
        assert client.get("/orders").json()["items"][0]["status"] == "preparing"

    def test_fail_rate_0_never_fails(self):
        client = TestClient(create_app(fail_rate=0))
        codes = {client.post(f"/orders/{1001 + i}/ready").status_code for i in range(0, 6)}
        assert 500 not in codes

    def test_fail_rate_30_percent_is_about_30_percent(self):
        client = TestClient(create_app(seed_count=400, fail_rate=0.3, rng=random.Random(7)))
        fails = sum(client.post(f"/orders/{1001 + i}/ready").status_code == 500 for i in range(0, 300, 1) if i % 7 != 6)
        total = sum(1 for i in range(300) if i % 7 != 6)
        assert 0.22 < fails / total < 0.38

    def test_only_ready_can_fail(self):
        client = TestClient(create_app(fail_rate=1))
        assert client.get("/menu").status_code == 200
        assert client.get("/orders").status_code == 200
        assert client.post("/orders", json=GOOD).status_code == 201

    def test_reads_FAIL_RATE_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("FAIL_RATE", "1")
        assert TestClient(create_app()).post("/orders/1001/ready").status_code == 500
        monkeypatch.setenv("FAIL_RATE", "0")
        assert TestClient(create_app()).post("/orders/1001/ready").status_code == 200


class TestCORS:
    ORIGIN = "http://localhost:5173"

    def preflight(self, client, origin, method="POST", headers="content-type", path="/orders/1001/ready"):
        return client.options(
            path,
            headers={"Origin": origin, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": headers},
        )

    def test_there_are_two_allowed_origins(self):
        assert len(ALLOWED_ORIGINS) == 2

    @pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
    def test_preflight_succeeds_for_each_allowed_origin(self, client, origin):
        res = self.preflight(client, origin)
        assert res.status_code == 200
        assert res.headers["access-control-allow-origin"] == origin
        assert "POST" in res.headers["access-control-allow-methods"]
        assert "content-type" in res.headers["access-control-allow-headers"].lower()

    def test_preflight_is_refused_for_another_origin(self, client):
        res = self.preflight(client, "http://evil.example")
        assert res.status_code == 400
        assert "access-control-allow-origin" not in res.headers

    def test_a_normal_response_carries_the_allow_header(self, client):
        res = client.get("/menu", headers={"Origin": self.ORIGIN})
        assert res.headers["access-control-allow-origin"] == self.ORIGIN

    def test_a_normal_response_to_another_origin_has_no_allow_header(self, client):
        res = client.get("/menu", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in res.headers

    def test_an_unlisted_header_is_refused(self, client):
        assert self.preflight(client, self.ORIGIN, headers="x-secret").status_code == 400

    def test_an_unlisted_method_is_refused(self, client):
        assert self.preflight(client, self.ORIGIN, method="DELETE").status_code == 400
```

### `web/src/test/setup.js`

```js
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, vi } from "vitest";
import { resetServerState, server } from "./server";

// React reports mistakes (a missing key, a bad update) with console.error.
// Any console.error fails the test, so mistakes cannot hide in the output.
let errorSpy;
beforeEach(() => {
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  const calls = errorSpy.mock.calls.map((c) => c.join(" "));
  errorSpy.mockRestore();
  expect(calls, "console.error was called during the test").toEqual([]);
});

// The fake server answers the real fetch calls. A call nobody planned for fails the test.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  resetServerState();
});
afterAll(() => server.close());
```

### `web/src/test/server.js`

```js
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { API_URL } from "../config";

export const MENU = [
  { id: 1, name: "Idli", price: 40 },
  { id: 2, name: "Masala Dosa", price: 80 },
  { id: 3, name: "Pongal", price: 60 },
];

// A small copy of the real server's rules: ids 1001 to 1050, every 7th one already ready.
export const makeOrders = (count = 50) =>
  Array.from({ length: count }, (_, i) => ({
    id: 1001 + i,
    table: (i % 12) + 1,
    items: [{ dish: MENU[i % 3].name, qty: (i % 3) + 1 }],
    status: i % 7 === 6 ? "ready" : "preparing",
  }));

export let orders = makeOrders();
export const requests = []; // every call made, e.g. "GET /menu" or "GET /orders?limit=20&after=1020"
export const resetServerState = (count = 50) => {
  orders = makeOrders(count);
  requests.length = 0;
};
export const countOf = (prefix) => requests.filter((r) => r.startsWith(prefix)).length;

/** Holds an answer back until open() is called, so a test can look at the screen "while the server is thinking". */
export function gate() {
  let open;
  const promise = new Promise((resolve) => (open = resolve));
  return { promise, open };
}

const url = (path) => `${API_URL}${path}`;

export const handlers = [
  http.get(url("/menu"), () => {
    requests.push("GET /menu");
    return HttpResponse.json(MENU);
  }),
  http.get(url("/orders"), ({ request }) => {
    const u = new URL(request.url);
    requests.push(`GET /orders${u.search}`);
    const limit = Number(u.searchParams.get("limit") ?? 20);
    const after = u.searchParams.get("after");
    const remaining = orders.filter((o) => after === null || o.id > Number(after));
    const items = remaining.slice(0, limit);
    return HttpResponse.json({ items, next_cursor: remaining.length > limit ? items.at(-1).id : null });
  }),
  http.post(url("/orders/:id/ready"), ({ params }) => {
    requests.push(`POST /orders/${params.id}/ready`);
    const order = orders.find((o) => o.id === Number(params.id));
    if (!order) return HttpResponse.json({ detail: "No such order." }, { status: 404 });
    order.status = "ready";
    return HttpResponse.json(order);
  }),
];

export const server = setupServer(...handlers);
export { http, HttpResponse };
```

### `web/src/test/render.jsx`

```jsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import App from "../App";
import { createQueryClient } from "../queryClient";

/** Renders the whole app with a fresh cache and no retries, so a failing test fails fast. */
export function renderApp(overrides = { retry: false }) {
  const queryClient = createQueryClient(overrides);
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
  return { queryClient, ...utils };
}
```

### `web/src/api.test.js`

```js
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { api, ApiError, UNEXPECTED_DATA } from "./api";
import { API_URL } from "./config";
import { http, HttpResponse, server } from "./test/server";

const at = (path) => `${API_URL}${path}`;
const fails = async (promise) => {
  try {
    await promise;
  } catch (err) {
    return err;
  }
  throw new Error("expected the call to fail");
};

describe("api: success", () => {
  it("returns the parsed body", async () => {
    server.use(http.get(at("/thing"), () => HttpResponse.json({ a: 1 })));
    expect(await api("/thing")).toEqual({ a: 1 });
  });
  it("sends no content type on a GET (so a GET never needs a preflight)", async () => {
    let seen;
    server.use(http.get(at("/thing"), ({ request }) => ((seen = request.headers.get("content-type")), HttpResponse.json({}))));
    await api("/thing");
    expect(seen).toBeNull();
  });
  it("sends JSON with a content type on a POST", async () => {
    let seen;
    server.use(
      http.post(at("/thing"), async ({ request }) => {
        seen = { type: request.headers.get("content-type"), body: await request.json() };
        return HttpResponse.json({});
      }),
    );
    await api("/thing", { method: "POST", body: { x: 1 } });
    expect(seen).toEqual({ type: "application/json", body: { x: 1 } });
  });
  it("a POST with no body still has the JSON content type (this is what triggers the CORS preflight)", async () => {
    let seen;
    server.use(http.post(at("/thing"), ({ request }) => ((seen = request.headers.get("content-type")), HttpResponse.json({}))));
    await api("/thing", { method: "POST" });
    expect(seen).toBe("application/json");
  });
});

describe("api: failures are all ApiError", () => {
  it.each([404, 409, 422, 500, 503])("res.ok false (%s) throws, and keeps the status", async (status) => {
    server.use(http.get(at("/thing"), () => HttpResponse.json({ detail: "nope" }, { status })));
    const err = await fails(api("/thing"));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(status);
  });
  it("uses the server's reason when it gives a string", async () => {
    server.use(http.get(at("/thing"), () => HttpResponse.json({ detail: "The ticket printer is jammed." }, { status: 500 })));
    expect((await fails(api("/thing"))).message).toBe("The ticket printer is jammed.");
  });
  it("uses a plain message when the reason is a list (FastAPI's own 422 shape)", async () => {
    server.use(http.get(at("/thing"), () => HttpResponse.json({ detail: [{ loc: ["body"], msg: "bad" }] }, { status: 422 })));
    expect((await fails(api("/thing"))).message).toBe("Request failed (422).");
  });
  it("uses a plain message when the error body is not JSON", async () => {
    server.use(http.get(at("/thing"), () => new HttpResponse("<html>Bad gateway</html>", { status: 502 })));
    const err = await fails(api("/thing"));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("Request failed (502).");
  });
  it("a network failure is an ApiError with status 0", async () => {
    server.use(http.get(at("/thing"), () => HttpResponse.error()));
    const err = await fails(api("/thing"));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toBe("Could not reach the server.");
  });
  it("a 200 whose body is not JSON says the data was unexpected", async () => {
    server.use(http.get(at("/thing"), () => new HttpResponse("not json at all", { status: 200 })));
    const err = await fails(api("/thing"));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(UNEXPECTED_DATA);
  });
  it("a 200 with the wrong shape says the data was unexpected", async () => {
    server.use(http.get(at("/thing"), () => HttpResponse.json({ oops: true })));
    const err = await fails(api("/thing", { schema: z.object({ a: z.number() }) }));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(UNEXPECTED_DATA);
  });
  it("a right-looking body with a wrong TYPE inside is caught too", async () => {
    server.use(http.get(at("/thing"), () => HttpResponse.json({ a: "1" })));
    expect((await fails(api("/thing", { schema: z.object({ a: z.number() }) }))).message).toBe(UNEXPECTED_DATA);
  });
  it("a matching body passes the schema, and the result is the parsed data", async () => {
    server.use(http.get(at("/thing"), () => HttpResponse.json({ a: 1, extra: 2 })));
    expect(await api("/thing", { schema: z.object({ a: z.number() }) })).toEqual({ a: 1 });
  });
});

describe("api: cancel", () => {
  it("passes the signal on, and a cancel is NOT turned into an ApiError", async () => {
    server.use(http.get(at("/slow"), async () => new Promise(() => {}))); // never answers
    const controller = new AbortController();
    const pending = fails(api("/slow", { signal: controller.signal }));
    controller.abort();
    const err = await pending;
    expect(err.name).toBe("AbortError");
    expect(err).not.toBeInstanceOf(ApiError);
  });
  it("a signal that was already cancelled stops the call straight away", async () => {
    const controller = new AbortController();
    controller.abort();
    const err = await fails(api("/menu", { signal: controller.signal }));
    expect(err.name).toBe("AbortError");
  });
});
```

### `web/src/queryClient.test.js`

```js
import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { createQueryClient, shouldRetry } from "./queryClient";
import { keys } from "./queryKeys";
import { MENU_STALE_MS, PAGE_SIZE } from "./hooks";

describe("shouldRetry", () => {
  it("retries once when there was no answer", () => {
    expect(shouldRetry(0, new ApiError("x", 0))).toBe(true);
    expect(shouldRetry(1, new ApiError("x", 0))).toBe(false);
  });
  it("retries once on a server fault", () => {
    expect(shouldRetry(0, new ApiError("x", 500))).toBe(true);
    expect(shouldRetry(0, new ApiError("x", 503))).toBe(true);
    expect(shouldRetry(1, new ApiError("x", 500))).toBe(false);
  });
  it.each([404, 409, 422])("never retries a %s (it would fail the same way)", (status) => {
    expect(shouldRetry(0, new ApiError("x", status))).toBe(false);
  });
  it("never retries a wrong-shape answer (status 200)", () => {
    expect(shouldRetry(0, new ApiError("The server sent unexpected data.", 200))).toBe(false);
  });
});

describe("createQueryClient", () => {
  it("can be told not to retry (tests do this)", () => {
    expect(createQueryClient({ retry: false }).getDefaultOptions().queries.retry).toBe(false);
  });
});

describe("keys and settings", () => {
  it("every key is a different array", () => {
    expect(Object.values(keys).every(Array.isArray)).toBe(true);
    expect(new Set(Object.values(keys).map((k) => k.join("/"))).size).toBe(Object.keys(keys).length);
  });
  it("the menu stays fresh for 5 minutes", () => {
    expect(MENU_STALE_MS).toBe(300000);
  });
  it("pages are 20 orders", () => {
    expect(PAGE_SIZE).toBe(20);
  });
});
```

### `web/src/App.test.jsx`

```jsx
import { act, screen, waitFor, within } from "@testing-library/react";
import { focusManager } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API_URL } from "./config";
import { MENU_STALE_MS } from "./hooks";
import { renderApp } from "./test/render";
import { countOf, gate, http, HttpResponse, orders, requests, server } from "./test/server";

const at = (path) => `${API_URL}${path}`;
const row = (id) => screen.getByTestId(`order-${id}`);
const rows = () => screen.queryAllByTestId(/^order-/);
const loaded = async () => screen.findByText("Showing 20 orders");

/** Lets a held-back answer go and waits until the whole save-and-reload is over, so nothing leaks into the next test. */
const finish = async (hold) => {
  const before = countOf("GET /orders");
  hold.open();
  await waitFor(() => expect(countOf("GET /orders")).toBeGreaterThan(before));
};

/** Pretend the person switched to another tab and came back. */
const switchTabsAndBack = async () => {
  await act(async () => {
    focusManager.setFocused(false);
    focusManager.setFocused(true);
  });
};

describe("menu", () => {
  it("shows a loading message, then the dishes with prices", async () => {
    renderApp();
    expect(screen.getByText("Loading menu…")).toBeInTheDocument();
    expect(await screen.findByText("₹80")).toBeInTheDocument();
    expect(screen.getByText("₹80")).toBeInTheDocument();
    expect(screen.queryByText("Loading menu…")).not.toBeInTheDocument();
  });

  it("a failed load shows the reason and Try again recovers", async () => {
    server.use(http.get(at("/menu"), () => HttpResponse.json({ detail: "The kitchen is closed." }, { status: 500 }), { once: true }));
    renderApp();
    expect(await screen.findByText(/The kitchen is closed\./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("₹80")).toBeInTheDocument();
    expect(screen.queryByText(/kitchen is closed/)).not.toBeInTheDocument();
  });

  it("an empty menu says so", async () => {
    server.use(http.get(at("/menu"), () => HttpResponse.json([])));
    renderApp();
    expect(await screen.findByText("The menu is empty.")).toBeInTheDocument();
  });

  it("a malformed body shows a friendly message, and the rest of the page is still there (no blank page)", async () => {
    server.use(http.get(at("/menu"), () => HttpResponse.json({ surprise: "not a list" })));
    renderApp();
    expect(await screen.findByText(/The server sent unexpected data\./)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kitchen orders board" })).toBeInTheDocument();
    expect(await loaded()).toBeInTheDocument(); // the orders still work
  });

  it("a dish with a price that is not a number is caught", async () => {
    server.use(http.get(at("/menu"), () => HttpResponse.json([{ id: 1, name: "Idli", price: "cheap" }])));
    renderApp();
    expect(await screen.findByText(/The server sent unexpected data\./)).toBeInTheDocument();
  });

  it("when a later reload of the menu fails or comes back malformed, the old menu stays and a message explains", async () => {
    renderApp();
    await screen.findByText("₹80");
    server.use(http.get(at("/menu"), () => HttpResponse.json({ not: "a menu" })));
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(Date.now() + MENU_STALE_MS + 1000);
      await switchTabsAndBack();
    } finally {
      vi.useRealTimers();
    }
    expect(await screen.findByText(/Could not refresh the menu: The server sent unexpected data\./)).toBeInTheDocument();
    expect(screen.getByText("₹80")).toBeInTheDocument();
  });

  it("not JSON at all is also friendly", async () => {
    server.use(http.get(at("/menu"), () => new HttpResponse("<html>oops</html>", { status: 200 })));
    renderApp();
    expect(await screen.findByText(/The server sent unexpected data\./)).toBeInTheDocument();
  });

  it("no answer at all says the server cannot be reached", async () => {
    server.use(http.get(at("/menu"), () => HttpResponse.error()));
    renderApp();
    expect(await screen.findByText(/Could not reach the server\./)).toBeInTheDocument();
  });
});

describe("menu: staleTime (the numbers for the proof)", () => {
  it("one request on load", async () => {
    renderApp();
    await screen.findByText("₹80");
    expect(countOf("GET /menu")).toBe(1);
  });

  it("switching tabs and coming back INSIDE staleTime makes no new menu request", async () => {
    renderApp();
    await screen.findByText("₹80");
    await loaded();
    await switchTabsAndBack();
    await switchTabsAndBack();
    expect(countOf("GET /menu")).toBe(1);
  });

  it("coming back AFTER staleTime makes exactly one new menu request", async () => {
    renderApp();
    await screen.findByText("₹80");
    await loaded();
    vi.useFakeTimers({ toFake: ["Date"] }); // only the clock moves, nothing else is slowed
    try {
      vi.setSystemTime(Date.now() + MENU_STALE_MS + 1000);
      await switchTabsAndBack();
    } finally {
      vi.useRealTimers();
    }
    await waitFor(() => expect(countOf("GET /menu")).toBe(2));
  });

  it("the orders board is NOT cached this way: coming back reloads it", async () => {
    renderApp();
    await loaded();
    const before = countOf("GET /orders");
    await switchTabsAndBack();
    await waitFor(() => expect(countOf("GET /orders")).toBeGreaterThan(before));
  });
});

describe("orders: loading and paging", () => {
  afterEach(() => vi.useRealTimers());

  it("shows a loading message, then 20 orders", async () => {
    renderApp();
    expect(screen.getByText("Loading orders…")).toBeInTheDocument();
    expect(await loaded()).toBeInTheDocument();
    expect(rows()).toHaveLength(20);
  });

  it("each order shows its table, number, dishes and status", async () => {
    renderApp();
    await loaded();
    const first = within(row(1001));
    expect(first.getByText("Table 1 · Order #1001")).toBeInTheDocument();
    expect(first.getByText("Preparing")).toBeInTheDocument();
    expect(first.getByText(/× Idli/)).toBeInTheDocument();
    expect(within(row(1007)).getByText("Ready")).toBeInTheDocument();
  });

  it("the first request asks for 20 and has no cursor", async () => {
    renderApp();
    await loaded();
    expect(requests).toContain("GET /orders?limit=20");
  });

  it("Load more adds the next 20 and asks with the cursor of the last order", async () => {
    renderApp();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Showing 40 orders")).toBeInTheDocument();
    expect(requests).toContain("GET /orders?limit=20&after=1020");
    expect(rows()).toHaveLength(40);
  });

  it("the last page shows 10, removes the button, and says that is every order", async () => {
    renderApp();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Showing 40 orders");
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Showing 50 orders")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
    expect(screen.getByText("That is every order.")).toBeInTheDocument();
  });

  it("no order appears twice after paging through everything", async () => {
    renderApp();
    await loaded();
    for (const shown of ["Showing 40 orders", "Showing 50 orders"]) {
      await userEvent.click(screen.getByRole("button", { name: "Load more" }));
      await screen.findByText(shown);
    }
    const ids = rows().map((el) => el.dataset.testid);
    expect(new Set(ids).size).toBe(50);
  });

  it("while loading more, the button says so and cannot be pressed again", async () => {
    renderApp();
    await loaded();
    const hold = gate();
    server.use(http.get(at("/orders"), async () => (await hold.promise, undefined)));
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    const busy = await screen.findByRole("button", { name: "Loading more…" });
    expect(busy).toBeDisabled();
    hold.open();
    expect(await screen.findByText("Showing 40 orders")).toBeInTheDocument();
  });

  it("a failed Load more keeps the orders, says why, and the button works again", async () => {
    renderApp();
    await loaded();
    server.use(http.get(at("/orders"), () => HttpResponse.json({ detail: "Too busy." }, { status: 500 }), { once: true }));
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText(/Could not load more orders: Too busy\./)).toBeInTheDocument();
    expect(rows()).toHaveLength(20);
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Showing 40 orders")).toBeInTheDocument();
    expect(screen.queryByText(/Could not load more/)).not.toBeInTheDocument();
  });

  it("a failed first load shows the reason and Try again recovers", async () => {
    server.use(http.get(at("/orders"), () => HttpResponse.json({ detail: "The kitchen is closed." }, { status: 500 }), { once: true }));
    renderApp();
    expect(await screen.findByText(/Could not load orders: The kitchen is closed\./)).toBeInTheDocument();
    const retry = screen.getAllByRole("button", { name: "Try again" }).at(-1);
    await userEvent.click(retry);
    expect(await loaded()).toBeInTheDocument();
  });

  it("a malformed orders body shows a friendly message and not a blank page", async () => {
    server.use(http.get(at("/orders"), () => HttpResponse.json({ items: "nope" })));
    renderApp();
    expect(await screen.findByText(/Could not load orders: The server sent unexpected data\./)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kitchen orders board" })).toBeInTheDocument();
  });

  it("an order with an unknown status is caught as unexpected data", async () => {
    server.use(http.get(at("/orders"), () => HttpResponse.json({ items: [{ id: 1, table: 1, items: [], status: "burnt" }], next_cursor: null })));
    renderApp();
    expect(await screen.findByText(/The server sent unexpected data\./)).toBeInTheDocument();
  });

  it("a missing cursor field is caught (it would otherwise look like 'no more pages')", async () => {
    server.use(http.get(at("/orders"), () => HttpResponse.json({ items: [] })));
    renderApp();
    expect(await screen.findByText(/The server sent unexpected data\./)).toBeInTheDocument();
  });

  it("no orders says so, with no Load more button", async () => {
    server.use(http.get(at("/orders"), () => HttpResponse.json({ items: [], next_cursor: null })));
    renderApp();
    expect(await screen.findByText("No orders yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("when a reload fails, the old list stays and a message explains", async () => {
    renderApp();
    await loaded();
    server.use(http.get(at("/orders"), () => HttpResponse.json({ detail: "Down." }, { status: 503 })));
    await switchTabsAndBack();
    expect(await screen.findByText(/Could not refresh the orders: Down\./)).toBeInTheDocument();
    expect(rows()).toHaveLength(20);
  });
});

describe("mark ready (optimistic)", () => {
  it("shows Ready at once, BEFORE the server has answered", async () => {
    renderApp();
    await loaded();
    const hold = gate();
    server.use(http.post(at("/orders/:id/ready"), async () => (await hold.promise, undefined)));
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    expect(await within(row(1001)).findByText("Ready")).toBeInTheDocument();
    expect(within(row(1001)).queryByRole("button")).not.toBeInTheDocument();
    await finish(hold);
  });

  it("only the pressed order changes", async () => {
    renderApp();
    await loaded();
    const hold = gate();
    server.use(http.post(at("/orders/:id/ready"), async () => (await hold.promise, undefined)));
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await within(row(1001)).findByText("Ready");
    expect(within(row(1002)).getByText("Preparing")).toBeInTheDocument();
    await finish(hold);
  });

  it("on success it sends one request, then reloads the list from the server, and the order stays Ready", async () => {
    renderApp();
    await loaded();
    const before = countOf("GET /orders");
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await waitFor(() => expect(countOf("GET /orders")).toBeGreaterThan(before));
    expect(requests.filter((r) => r === "POST /orders/1001/ready")).toHaveLength(1);
    expect(within(row(1001)).getByText("Ready")).toBeInTheDocument();
    expect(screen.queryByText(/put back/)).not.toBeInTheDocument();
  });

  it("on failure the order goes back to Preparing and a short message appears", async () => {
    renderApp();
    await loaded();
    server.use(http.post(at("/orders/:id/ready"), () => HttpResponse.json({ detail: "The ticket printer is jammed." }, { status: 500 })));
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    expect(await within(row(1001)).findByText(/Could not mark order #1001 ready, so it was put back\. The ticket printer is jammed\./)).toBeInTheDocument();
    expect(within(row(1001)).getByText("Preparing")).toBeInTheDocument();
    expect(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" })).toBeInTheDocument();
  });

  it("it shows Ready first and rolls back after (the person sees both)", async () => {
    renderApp();
    await loaded();
    const hold = gate();
    server.use(
      http.post(at("/orders/:id/ready"), async () => {
        await hold.promise;
        return HttpResponse.json({ detail: "Nope." }, { status: 500 });
      }),
    );
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await within(row(1001)).findByText("Ready");
    hold.open();
    await within(row(1001)).findByText("Preparing");
  });

  it("after a failure the list is reloaded from the server (onSettled runs on errors too)", async () => {
    renderApp();
    await loaded();
    const before = countOf("GET /orders");
    server.use(http.post(at("/orders/:id/ready"), () => HttpResponse.json({ detail: "Nope." }, { status: 500 })));
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await waitFor(() => expect(countOf("GET /orders")).toBeGreaterThan(before));
  });

  it("a failure can be tried again, and then it works", async () => {
    renderApp();
    await loaded();
    server.use(http.post(at("/orders/:id/ready"), () => HttpResponse.json({ detail: "Nope." }, { status: 500 }), { once: true }));
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await within(row(1001)).findByText(/put back/);
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await waitFor(() => expect(within(row(1001)).getByText("Ready")).toBeInTheDocument());
    await waitFor(() => expect(screen.queryByText(/put back/)).not.toBeInTheDocument());
  });

  it("a 404 (the order is gone) also rolls back with the reason", async () => {
    renderApp();
    await loaded();
    server.use(http.post(at("/orders/:id/ready"), () => HttpResponse.json({ detail: "No such order." }, { status: 404 })));
    await userEvent.click(within(row(1002)).getByRole("button", { name: "Mark order 1002 ready" }));
    expect(await within(row(1002)).findByText(/No such order\./)).toBeInTheDocument();
    expect(within(row(1002)).getByText("Preparing")).toBeInTheDocument();
  });

  it("two orders at once, one fails: ONLY the failed one rolls back", async () => {
    renderApp();
    await loaded();
    server.use(http.post(at("/orders/1001/ready"), () => HttpResponse.json({ detail: "Jammed." }, { status: 500 })));
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await userEvent.click(within(row(1002)).getByRole("button", { name: "Mark order 1002 ready" }));
    await within(row(1001)).findByText(/put back/);
    expect(within(row(1001)).getByText("Preparing")).toBeInTheDocument();
    await waitFor(() => expect(within(row(1002)).getByText("Ready")).toBeInTheDocument());
  });

  it("the other orders keep their state during a rollback", async () => {
    renderApp();
    await loaded();
    server.use(http.post(at("/orders/1001/ready"), () => HttpResponse.json({ detail: "Jammed." }, { status: 500 })));
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await within(row(1001)).findByText(/put back/);
    expect(within(row(1007)).getByText("Ready")).toBeInTheDocument();
    expect(within(row(1003)).getByText("Preparing")).toBeInTheDocument();
  });

  it("works for an order on the second page, and keeps both pages after the reload", async () => {
    renderApp();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Showing 40 orders");
    await userEvent.click(within(row(1030)).getByRole("button", { name: "Mark order 1030 ready" }));
    await waitFor(() => expect(within(row(1030)).getByText("Ready")).toBeInTheDocument());
    await waitFor(() => expect(requests.filter((r) => r.startsWith("GET /orders")).length).toBeGreaterThan(3));
    expect(rows()).toHaveLength(40);
  });

  it("a second-page order rolls back too", async () => {
    renderApp();
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Showing 40 orders");
    server.use(http.post(at("/orders/:id/ready"), () => HttpResponse.json({ detail: "Nope." }, { status: 500 })));
    await userEvent.click(within(row(1030)).getByRole("button", { name: "Mark order 1030 ready" }));
    await within(row(1030)).findByText(/put back/);
    expect(within(row(1030)).getByText("Preparing")).toBeInTheDocument();
  });

  it("a reload that is already running when you press the button does not overwrite the change", async () => {
    renderApp();
    await loaded();
    // A slow reload starts. It takes its picture of the orders NOW (before the change), and answers late.
    const slowReload = gate();
    const savingStarts = gate();
    server.use(
      http.get(
        at("/orders"),
        async () => {
          const oldPicture = orders.slice(0, 20).map((o) => ({ ...o }));
          await slowReload.promise;
          return HttpResponse.json({ items: oldPicture, next_cursor: 1020 });
        },
        { once: true },
      ),
      http.post(at("/orders/:id/ready"), async () => (await savingStarts.promise, undefined)),
    );
    await switchTabsAndBack();
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    slowReload.open(); // the old, out-of-date answer arrives while the save is still running
    await new Promise((r) => setTimeout(r, 50));
    expect(within(row(1001)).getByText("Ready")).toBeInTheDocument();
    await finish(savingStarts);
  });

  it("the rollback itself puts it back, even before the server is asked again (the reload is held)", async () => {
    renderApp();
    await loaded();
    const reload = gate();
    server.use(
      http.post(at("/orders/:id/ready"), () => HttpResponse.json({ detail: "Nope." }, { status: 500 })),
      http.get(at("/orders"), async () => (await reload.promise, undefined)),
    );
    await userEvent.click(within(row(1001)).getByRole("button", { name: "Mark order 1001 ready" }));
    await within(row(1001)).findByText(/put back/);
    expect(within(row(1001)).getByText("Preparing")).toBeInTheDocument(); // the reload has NOT answered yet
    await finish(reload);
  });
});
```

---

## 8. Results

| Check | Command | Result |
|---|---|---|
| Server tests | `cd server && python -m pytest` | **62 passed** |
| Client tests | `cd web && npm test` | **69 passed** (3 files), run 3 times in a row with the same result |
| Build | `npm run build` | Built successfully |
| Real-browser proof | `cd web && node scripts/check-browser.mjs` (Chromium, the production build, the real FastAPI server) | **25 of 25 passed** (details below) |
| Proof number 1: `/menu` requests | tab switches in the browser | **0 new requests** after switching tabs twice inside `staleTime` (total stays 1). **1 new request** after coming back past the 5 minutes (total 2). The orders list reloaded on every return. |
| Proof number 2: the preflight | the server's own log | `OPTIONS /orders/1001/ready` **200 OK**, then `POST /orders/1001/ready` **200 OK**, from `localhost:5173`. The answer carried `Access-Control-Allow-Origin: http://localhost:5173` and allowed POST. `127.0.0.1:5173` works too. A preflight from `http://evil.example` got 400 and no allow header. |
| Proof number 3: the rollback | server failing every "Mark ready"; the answer held 1.2 s | The badge went **Preparing, Ready, Preparing**. Ready appeared in under 600 ms, while the server was still thinking. A short message appeared and the button came back. A reload confirmed the server never changed it. With the server failing about 30% of the time, **6 of 18** attempts failed in this run (this number changes from run to run). Every failure rolled back, every success stayed, and the screen agreed with the server each time. |
| Other browser checks | same run | Paging showed 20, 40, 50 and the button disappeared; the cursors `after=1020` and `after=1040` were sent; no order appeared twice; a malformed `/menu` showed the friendly message with the heading and orders still on screen; no console errors. |
| Break-it checks | 41 changes, such as: the helper ignoring `res.ok`; no Zod check; a cancel turned into an `ApiError`; no JSON content type; the cursor not sent or always offering a next page; no `staleTime`; no `cancelQueries`; no rollback; no reload after settle; reload only on success; only the first page updated; the wrong order changed; no failure message; a Load more button that is never disabled; retries always on; looser schemas; a server cursor with `>=`; a cursor that is never `null`; CORS open to every origin or to one only; extra fields allowed; non-strict input; no 409; `FAIL_RATE` ignored; dish not checked; no maximum limit; create returning 200; a seed that is too small; reused ids; an unknown order marked ready | **40 of 41 were caught.** The one that survives is removing `allow_headers=["Content-Type"]`: it is an equivalent change, because Starlette always allows `Content-Type` in a preflight. The line stays because it says what the page needs. Two tests were too weak at first (no `cancelQueries`, no rollback survived), and were rewritten until those changes were caught. |
| Restored original | both test suites | **62 passed** and **69 passed** |

---

## 9. Problems avoided

| Problem | Cause | Fix |
|---|---|---|
| The first request counts were off by one in the browser | `npm run dev` uses React StrictMode, which mounts the page twice on purpose. The first `/menu` request is cancelled and sent again, so every count had one extra | Numbers are measured on the production build (`vite build` and `vite preview`). In the dev server the Network panel shows the first `/menu` twice, the first one cancelled. That is normal |
| The rollback tests passed even with the rollback removed | The reload after the failure brought the true status back, so the tests could not tell the rollback from the reload | A test that holds the reload back and checks the screen before it answers |
| The test for "a running reload must not overwrite the change" passed without `cancelQueries` | The held reload read the server's data after the save, so it was not out of date | The reload now takes its picture of the orders before waiting, and the save is held too, so the old picture really is old |
| A test failed only in the full run | A held "Mark ready" was released at the end of its test, and the late request changed the next test's data | Held tests wait until the save and reload end (`finish`) |
| The error message came late | `onSettled` returned the reload, so the mutation stayed pending until the reload ended | `onSettled` does not return it. The message appears at once |
| A failed reload of the menu showed nothing | With data already on screen, the error was not displayed | A message above the old menu says it could not refresh |
| The browser check could not read the CORS headers from the page | A page cannot send an `OPTIONS` request with those headers, because they are forbidden to scripts and OPTIONS needs its own preflight | The headers are read with `curl`, and the real preflight is read from the server's log |
| A break-it check wrongly said "caught" | The check looked for the word `failed`, and a build error printed no such word | A run with an error, or with no `passed` line, also counts as caught, and the result is read by hand |
| `StrictMode` and the cancel | A cancel must not become a red error on screen | The helper rethrows a cancel untouched and a test pins it |

---

## 10. What was practiced

- Writing a small API with cursor paging, input validation (422) and CORS, and testing the preflight.
- One request helper that checks `res.ok`, throws one error type, and supports cancel.
- `useQuery` with a `staleTime` that can be explained and measured.
- `useInfiniteQuery` with `initialPageParam` and `getNextPageParam`.
- An optimistic update with `onMutate`, `onError` and `onSettled`, and why the rollback restores one order.
- Checking every response with Zod and showing a friendly message.
- Testing with a fake server that can be held back, made to fail and made to lie.
- Measuring requests and the preflight in a real browser, and breaking the code on purpose to prove the tests.

---

## 11. Known limit

The orders live in the server's memory, so they reset when the server restarts, and there is no login. The page has no form for creating an order (`POST /orders` is tested on the server and can be tried in `/docs`). `FAIL_RATE` is for testing and is off by default. The numbers in the proof were measured on the production build; the dev server shows the first `/menu` request twice because of StrictMode. The 30% run is random, so "6 of 18" will differ each time. I did not take the four proof screenshots for you; the steps are below, and the script saves its own screenshots in `web/check-output/`.

---

## 12. How to run it

```bash
# 1. server (one terminal)
cd kitchen-orders-board/server
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                  # 62 tests
python -m uvicorn main:app --reload --port 8000
# open http://localhost:8000/docs to try the API

# 2. web (a second terminal)
cd kitchen-orders-board/web
npm install
npm test                          # 69 tests
npm run dev                       # open http://localhost:5173

# 3. the rollback test: stop the server and start it failing 30% of "Mark ready"
#    Windows PowerShell:   $env:FAIL_RATE="0.3"; python -m uvicorn main:app --port 8000
#    Mac/Linux:            FAIL_RATE=0.3 python -m uvicorn main:app --port 8000
```

**Take the proof yourself (Chrome or Edge, DevTools, Network tab).**

1. **Numbers for `staleTime`.** Run `npm run build`, then `npm run preview` (the production build, port 5173). Open DevTools, Network, type `menu` in the filter. Reload once: you see 1 `/menu` request. Switch to another tab and come back (twice): still 1. For the "after" case, change `MENU_STALE_MS` in `src/hooks.js` to `5000` (5 seconds), rebuild, wait 6 seconds, switch tabs and come back: a second request appears. Put it back to `5 * 60 * 1000`. *In `npm run dev` you will see two `/menu` rows on load, the first cancelled. That is StrictMode, not a bug.*
2. **The preflight.** Network tab, tick **Fetch/XHR**, press Mark ready. You will see two rows named `ready`: the first with method **OPTIONS** (the preflight, status 200), then **POST** (200). Click the OPTIONS row and open Response Headers: `Access-Control-Allow-Origin: http://localhost:5173`.
3. **The rollback.** Start the server with `FAIL_RATE=1` (always fails), press Mark ready: the badge shows Ready, then goes back to Preparing with a red message. For about 30%, use `FAIL_RATE=0.3` and press it on several orders. Tip: in the Network tab, set throttling to "Slow 4G" so the Ready moment lasts longer.
4. **Remove the failure afterwards:** start the server normally (no `FAIL_RATE`).

The automatic version of all this is `node scripts/check-browser.mjs` (needs `npm install -D playwright` and `npx playwright install chromium`). It saves screenshots in `web/check-output/`.
