import datetime
import struct
import time

from piston.steem import Post


class Author(object):
    """An author."""
    def __init__(self, name, vote_replies=False, weight=100.0):
        self.name = name
        self.vote_replies = vote_replies
        self.weight = weight

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
        return cls(name, vote_replies=vote_replies, weight=weight)

    def to_dict(self):
        return {
            'name': self.name,
            'vote_replies': self.vote_replies,
            'weight': self.weight,
        }

class Comment(Post):
    """A comment."""
    def __init__(self, steem, post):
        if isinstance(post, str):
            super(Comment, self).__init__(steem, post)
        else:
            attrs = [attr for attr in dir(post) if not attr.startswith('_')]
            d = {attr: getattr(post, attr) for attr in attrs}
            if not d.get('author'):
                raise ValueError('An author is required')
            super(Comment, self).__init__(steem, d)
        self.timestamp = int(self.created_parsed.replace(tzinfo=datetime.timezone.utc).timestamp())

    @classmethod
    def deserialize_key(cls, key, steem):
        # Remove "post-" prefix.
        identifier = str(key[5:], 'utf-8')
        return cls(steem, identifier)

    def serialize_key(self):
        return b'post-' + bytes(self.identifier, 'utf-8')

    def is_reply(self):
        return True if self.parent_author else False
