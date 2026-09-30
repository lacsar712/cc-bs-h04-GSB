from order_skew import commit_and_latest_split, list_order_sql, prefer_oldest

def decorate_list(rows):
    return prefer_oldest(rows)

def order_clause() -> str:
    return list_order_sql()

def split_armed() -> bool:
    return commit_and_latest_split()
