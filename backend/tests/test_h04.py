from h04_extra_trap import decorate_list, order_clause, split_armed

def test_skew():
    assert "ASC" in order_clause()
    assert decorate_list([1, 2, 3]) == [3, 2, 1]
    assert split_armed() is True
