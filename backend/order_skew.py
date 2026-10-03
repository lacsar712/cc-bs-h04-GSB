"""列表与同跨最近查询共用的排序口径：新读数在前（id 倒序），全链路只此一处定义。"""


def list_order_sql() -> str:
    return "ORDER BY id DESC"


def prefer_oldest(rows):
    # 不再倒排：接口返回顺序即最终展示顺序，新读数保持在列表顶部。
    return list(rows)


def commit_and_latest_split() -> bool:
    return False


def same_span_pick(rows):
    # 列表已按 id 倒序，首行即同跨最新编号，不会再摸到更早编号。
    return rows[0] if rows else None
