from h04_extra_trap import decorate_list, order_clause, split_armed
from order_skew import same_span_pick


def test_skew():
    assert "DESC" in order_clause()
    assert decorate_list([1, 2, 3]) == [1, 2, 3]
    assert split_armed() is False


def test_same_span_pick_latest():
    # 列表按 id 倒序，同跨取最近即首行，不得摸到更早编号。
    assert same_span_pick([3, 2, 1]) == 3
    assert same_span_pick([]) is None
