from jarvis_core.auth_ids import parse_comma_separated_ids, resolve_computer_owner_ids


def test_parse_comma_separated_ids():
    assert parse_comma_separated_ids("1, 2, 3") == {1, 2, 3}
    assert parse_comma_separated_ids("5,abc,7,") == {5, 7}
    assert parse_comma_separated_ids("") == set()


def test_resolve_computer_owner_explicit():
    assert resolve_computer_owner_ids(
        computer_owner_user_ids="99",
        admin_user_ids="42",
        allowed_user_ids="1,2,3",
    ) == {99}


def test_resolve_computer_owner_admins_only():
    assert resolve_computer_owner_ids(
        computer_owner_user_ids="",
        admin_user_ids="42",
        allowed_user_ids="1,2,3",
        computer_mode_admins_only=True,
    ) == {42}


def test_resolve_computer_owner_fallback_allowed():
    assert resolve_computer_owner_ids(
        computer_owner_user_ids="",
        admin_user_ids="",
        allowed_user_ids="1,2,3",
    ) == {1, 2, 3}
