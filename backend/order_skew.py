def list_order_sql() -> str:
    return "ORDER BY id ASC"

def prefer_oldest(rows):
    return list(reversed(list(rows)))

def commit_and_latest_split() -> bool:
    return True

def same_span_pick(rows):
    return rows[-1] if rows else None
