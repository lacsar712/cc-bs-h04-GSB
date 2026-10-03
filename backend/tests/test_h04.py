"""H04：列表顶序、同跨最近、落盘瞬间回查必须是同一套口径。

- 服务端统一 ORDER BY id DESC，最新读数在顶；
- 同跨取最近取最大编号，不得摸到更早编号；
- 落盘提交的响应里 latest_same_span 必须就是刚入队那条，与列表顶序一致；
- 种子样 跨中S1=150 合格、支座S2=40 越界 不得漂；
- 页面顺序由服务端决定（前端只渲染，不自行倒排）。
"""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest

from api import app as app_module
from ordering import LIST_ORDER_SQL, latest_for_span
from rules import judge_microstrain


def token_for(username: str, role: str) -> str:
    return jwt.encode(
        {
            "sub": username,
            "role": role,
            "exp": datetime.now(timezone.utc).timestamp() + 3600,
        },
        app_module.SECRET,
        algorithm="HS256",
    )


# ---------- 纯口径测试（不依赖服务进程） ----------

def test_list_order_is_descending():
    assert LIST_ORDER_SQL == "ORDER BY id DESC"


def test_latest_for_span_picks_largest_id_not_list_tail():
    rows = [
        {"id": 9, "span_code": "跨中S1"},
        {"id": 5, "span_code": "跨中S1"},
        {"id": 8, "span_code": "支座S2"},
    ]
    # DESC 排列下同跨最近必须是最大编号 9，而不是 ASC 时代的"最后一条"。
    assert latest_for_span(rows, "跨中S1")["id"] == 9
    assert latest_for_span(rows, "支座S2")["id"] == 8
    assert latest_for_span(rows, "不存在的跨") is None


def test_seed_sample_verdicts_do_not_drift():
    assert judge_microstrain(150.0) == (
        "合格",
        "微应变处于 80～220 με 设计允许范围内",
    )
    verdict, reason = judge_microstrain(40.0)
    assert verdict == "越界"
    assert "下限" in reason


# ---------- 接口级测试：用内存假库走真实处理器 ----------

class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._one = None
        self._all = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        norm = " ".join(sql.split())
        if norm.startswith("INSERT INTO strain_readings"):
            span_code, microstrain, created_by = params
            new_id = max(self.db, default=0) + 1
            row = {
                "id": new_id,
                "span_code": span_code,
                "microstrain": float(microstrain),
                "verdict": None,
                "reason": None,
                "status": "pending",
                "created_by": created_by,
                "created_at": datetime(2026, 10, 3, tzinfo=timezone.utc),
                "processed_at": None,
            }
            self.db[new_id] = row
            self._one = row
            self._all = None
        elif "WHERE span_code = %s" in norm and "LIMIT 1" in norm:
            same = [r for r in self.db.values() if r["span_code"] == params[0]]
            self._one = max(same, key=lambda r: r["id"], default=None)
            self._all = None
        else:
            self._one = None
            self._all = sorted(self.db.values(), key=lambda r: -r["id"])

    async def fetchone(self):
        return self._one

    async def fetchall(self):
        return self._all


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.commits = 0

    def cursor(self):
        return FakeCursor(self.db)

    async def commit(self):
        self.commits += 1


class FakePool:
    def __init__(self, db):
        self.db = db

    def connection(self):
        return _PoolConn(self.db)


class _PoolConn:
    def __init__(self, db):
        self._conn = FakeConn(db)

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def make_request(db, token=None, body=None, args=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return SimpleNamespace(
        app=SimpleNamespace(ctx=SimpleNamespace(pool=FakePool(db))),
        headers=headers,
        json=body or {},
        args=args or {},
    )


def call(coro):
    return asyncio.run(coro)


def body_of(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.fixture
def db():
    return {
        1: {
            "id": 1,
            "span_code": "跨中S1",
            "microstrain": 150.0,
            "verdict": "合格",
            "reason": "微应变处于 80～220 με 设计允许范围内",
            "status": "done",
            "created_by": "surveyor",
            "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "processed_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        },
        2: {
            "id": 2,
            "span_code": "支座S2",
            "microstrain": 40.0,
            "verdict": "越界",
            "reason": "微应变低于 80 με 设计下限",
            "status": "done",
            "created_by": "surveyor",
            "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "processed_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        },
    }


WRITER = token_for("surveyor", "writer")
READER = token_for("reviewer", "reader")


def test_list_is_newest_first_and_seed_rows_do_not_drift(db):
    resp = call(app_module.list_readings(make_request(db, token=WRITER)))
    assert resp.status == 200
    rows = body_of(resp)
    assert [r["id"] for r in rows] == [2, 1]
    first = {(r["span_code"], r["verdict"]) for r in rows}
    assert ("跨中S1", "合格") in first
    assert ("支座S2", "越界") in first


def test_list_requires_auth(db):
    resp = call(app_module.list_readings(make_request(db)))
    assert resp.status == 401


def test_latest_same_span_never_returns_older_id(db):
    # 同跨已有更早编号 1，再插一条 3，最近必须是 3。
    db[3] = {
        "id": 3,
        "span_code": "跨中S1",
        "microstrain": 160.0,
        "verdict": "合格",
        "reason": "微应变处于 80～220 με 设计允许范围内",
        "status": "done",
        "created_by": "surveyor",
        "created_at": datetime(2026, 10, 2, tzinfo=timezone.utc),
        "processed_at": datetime(2026, 10, 2, tzinfo=timezone.utc),
    }
    resp = call(
        app_module.latest_reading(
            make_request(db, token=WRITER, args={"span_code": "跨中S1"})
        )
    )
    assert resp.status == 200
    assert body_of(resp)["id"] == 3


def test_create_commits_then_same_span_latest_matches_list_top(db):
    resp = call(
        app_module.create_reading(
            make_request(
                db,
                token=WRITER,
                body={"span_code": "跨中S1", "microstrain": 155.0},
            )
        )
    )
    assert resp.status == 201
    payload = body_of(resp)
    new_id = payload["id"]
    assert new_id == 3
    # 落盘瞬间：同跨最近必须是刚入队的新号，不得仍摸回更早的编号 1。
    assert payload["latest_same_span"]["id"] == new_id

    # 同一口径下列表顶序也必须是这条，两边不得各说各话。
    listing = body_of(call(app_module.list_readings(make_request(db, token=WRITER))))
    assert listing[0]["id"] == new_id
    assert listing[0]["span_code"] == "跨中S1"


def test_reader_cannot_submit(db):
    resp = call(
        app_module.create_reading(
            make_request(
                db,
                token=READER,
                body={"span_code": "跨中S3", "microstrain": 120.0},
            )
        )
    )
    assert resp.status == 403
    assert set(db) == {1, 2}
