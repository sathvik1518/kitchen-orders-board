# kitchen-orders-board

The Orders board of the Kitchen App: a FastAPI server (menu, cursor-paged orders, create, mark ready, CORS) and a React client using TanStack Query (`useQuery`, `useInfiniteQuery`, an optimistic "Mark ready" with rollback) with every response checked by Zod.

```bash
# server
cd server && pip install -r requirements-dev.txt && python -m pytest
python -m uvicorn main:app --reload --port 8000

# web (second terminal)
cd web && npm install && npm test && npm run dev
```

See `DOCUMENTATION.md` for the full write-up.
