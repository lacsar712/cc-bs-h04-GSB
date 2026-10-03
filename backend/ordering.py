"""读数排序与"同跨最近"的唯一口径：编号越大越新，最近即最大 id。

列表顶序、按同跨取最近、落盘瞬间回查都必须走这里，不得各写各的。
"""

# 服务端统一排序：最新在最前。页面不得再自行倒排。
LIST_ORDER_SQL = "ORDER BY id DESC"

# 行序列化字段顺序，供列表与单条回查共用。
ROW_COLUMNS = (
    "id, span_code, microstrain, verdict, reason, status, "
    "created_by, created_at, processed_at"
)


def latest_for_span(rows, span_code: str):
    """在已按 id DESC 排列的行中返回该跨段最近的一条；没有则 None。"""
    for row in rows:
        if row["span_code"] == span_code:
            return row
    return None
