from app_settings import validate_cue_list_player, validate_ip_address


def test_cue_list_player_under():
    for i in range(-1, 0):
        assert not validate_cue_list_player(i)
        assert not validate_cue_list_player(str(i))


def test_cue_list_player_valid():
    for i in range(1, 127):
        assert validate_cue_list_player(i)
        assert validate_cue_list_player(str(i))


def test_cue_list_player_over():
    for i in range(128, 129):
        assert not validate_cue_list_player(i)
        assert not validate_cue_list_player(str(i))


def test_ipv4_valid():
    assert validate_ip_address("0.0.0.0")
    assert validate_ip_address("127.0.0.1")
    assert validate_ip_address("10.0.0.86")
    assert validate_ip_address("192.168.2.1")
    assert validate_ip_address("192.168.2.1 ")


def test_ipv4_invalid():
    assert not validate_ip_address("192")
    assert not validate_ip_address("192.")
    assert not validate_ip_address("10.0.0.256")
    assert not validate_ip_address("10.0.0.8a")
    assert not validate_ip_address("10.0.0.b")
    assert not validate_ip_address("10.0.0.c ")
