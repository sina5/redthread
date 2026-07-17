from redthread.ids import get_node_id, new_ulid


def test_new_ulid_sortable_and_unique():
    a = new_ulid()
    b = new_ulid()
    assert a != b
    assert len(a) == 26
    assert sorted([b, a]) == [a, b]


def test_node_id_is_stable_and_not_hostname_derived(tmp_path):
    import socket

    first = get_node_id(tmp_path)
    second = get_node_id(tmp_path)
    assert first == second
    assert socket.gethostname().lower() not in first.lower()


def test_node_id_persists_across_instances(tmp_path):
    first = get_node_id(tmp_path)
    (tmp_path / "node_id").read_text(encoding="utf-8")  # file exists
    second = get_node_id(tmp_path)
    assert first == second
