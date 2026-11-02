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
