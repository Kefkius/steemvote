import pytest

from steemvote.config import Config, default_values, get_decimal
from steemvote.models import Priority

class TestDecimal(object):
    def test_float(self):
        for data, expected in [
            (0.5, 0.5),
        ]:
            assert expected == get_decimal(data)

    def test_string(self):
        for data, expected in [
            ('0.5', 0.5),
            ('50%', 0.5),
            ('100%', 1.0),
        ]:
            assert expected == get_decimal(data)

def test_defaults():
    """Test that default values are used."""
    c = Config(no_saving=True)
    for k, v in default_values:
        assert c.get(k) == v

@pytest.fixture
def old_keys_dict():
    return {
        'backup_authors': ['alice', 'bob',],
        'vote_delay': 120,
        'min_voting_power': 0.1,
        'max_voting_power': 0.5,
    }

def test_update_keys(old_keys_dict):
    """Test that old config keys get updated."""
    c = Config(no_saving=True)
    c.options = dict(old_keys_dict)
    c.options_loaded()

    assert c.get_seconds('min_post_age') == old_keys_dict['vote_delay']
    assert c.get_decimal('priority_low') == old_keys_dict['max_voting_power']
    assert c.get_decimal('priority_high') == old_keys_dict['min_voting_power']

    for name in ['alice', 'bob']:
        assert c.get_author(name).priority == Priority.low

    for old_option in old_keys_dict.keys():
        assert c.get(old_option) is None
