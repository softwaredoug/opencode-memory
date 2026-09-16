from know_history.parse_telemetry import _get_nested


def test_get_nested():
    nested_dict = {"foo": {"bar": {"baz": 42}}}
    assert _get_nested(nested_dict, ("foo", "bar", "baz")) == 42


def test_get_nested_no_good_path():
    nested_dict = {"foo": {"bar": {"biz": 42}}}
    assert _get_nested(nested_dict, ("foo", "bar", "baz")) is None


def test_get_nested_with_list_index():
    nested_dict = {"foo": {"bar": [42]}}
    assert _get_nested(nested_dict, ("foo", "bar", 0)) == 42


def test_out_of_bounds_list_index():
    nested_dict = {"foo": {"bar": [42]}}
    assert _get_nested(nested_dict, ("foo", "bar", 1)) is None


def test_int_used_where_dict_key_expected():
    nested_dict = {"foo": {"bar": {"baz": 42}}}
    assert _get_nested(nested_dict, ("foo", "bar", 0)) is None
