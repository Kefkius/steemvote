import datetime
import enum
import struct
import time

from piston.steem import Post


class Priority(enum.Enum):
    """Constants for author priority values."""
    low = 'low'
    normal = 'normal'
    high = 'high'
    @classmethod
    def get_index(cls, priority):
        """Get the numeric index of priority."""
        for i, level in enumerate(cls.__members__.values()):
            if level is priority:
                return i

class Author(object):
    """An author."""
    def __init__(self, name, vote_replies=False, weight=100.0, priority=Priority.normal):
        self.name = name
        self.vote_replies = vote_replies
        self.weight = weight
        self.priority = priority

    @classmethod
    def from_config(cls, value):
        """Instantiate from config value."""
        if isinstance(value, dict):
            return cls.from_dict(value)
        elif isinstance(value, str):
            return cls(name=value)
        elif isinstance(value, bytes):
            return cls(name=str(value, 'utf-8'))
        else:
            raise TypeError('A string or dict is required')

    @classmethod
    def from_dict(cls, d):
        name = d.get('name')
        if not name:
            raise ValueError('No name was specified')
        vote_replies = d.get('vote_replies', False)
        weight = d.get('weight', 100.0)
        if not isinstance(weight, float):
            raise TypeError('A float is required for weight')
        priority = Priority(d.get('priority', 'normal'))
        return cls(name, vote_replies=vote_replies, weight=weight, priority=priority)

    def to_dict(self):
        return {
            'name': self.name,
            'vote_replies': self.vote_replies,
            'weight': self.weight,
            'priority': self.priority.value,
        }

class Comment(Post):
    """A comment."""
    def __init__(self, steem, post):
        super(Comment, self).__init__(steem, post)
        self.timestamp = int(self.created_parsed.replace(tzinfo=datetime.timezone.utc).timestamp())

    @staticmethod
    def serialize_key_from_identifier(identifier):
        if isinstance(identifier, str):
            identifier = bytes(identifier, 'utf-8')
        return b'post-' + identifier

    @classmethod
    def deserialize_key(cls, key, steem):
        # Remove "post-" prefix.
        identifier = str(key[5:], 'utf-8')
        return cls(steem, identifier)

    def serialize_key(self):
        return Comment.serialize_key_from_identifier(self.identifier)

    def is_reply(self):
        return True if self.parent_author else False

    def get_url(self, domain='https://steemit.com'):
        """Get the URL for this comment at domain."""
        domain = domain.rstrip('/')
        return domain + self.url
