import datetime
import struct

class Author(object):
    """An author."""
    def __init__(self, name, vote_replies=False, weight=100.0):
        self.name = name
        self.vote_replies = vote_replies
        self.weight = weight

    @classmethod
    def from_dict(cls, d):
        name = bytes(d.get('name', ''), 'utf-8')
        if not name:
            raise ValueError('No name was specified')
        vote_replies = d.get('vote_replies', False)
        weight = d.get('weight', 100.0)
        if not isinstance(weight, float):
            raise TypeError('A float is required for weight')
        return cls(name, vote_replies=vote_replies, weight=weight)

class Comment(object):
    """A comment."""
    def __init__(self, author='', identifier='', timestamp=0, is_reply=False):
        self.author = author
        self.identifier = identifier
        self.timestamp = timestamp
        self.is_reply = is_reply

    @classmethod
    def from_dict(cls, d):
        """Initialize from a dict."""
        author = bytes(d['author'], 'utf-8')
        identifier = bytes(d['identifier'], 'utf-8')
        timestamp = int(d['created_parsed'].replace(tzinfo=datetime.timezone.utc).timestamp())
        is_reply = True if d['parent_author'] else False

        return cls(author=author, identifier=identifier, timestamp=timestamp,
                is_reply=is_reply)

    @classmethod
    def deserialize(cls, key, value):
        """Deserialize from database key and value."""
        # Remove "post-" prefix.
        identifier = key[5:]
        timestamp = struct.unpack(b'<I', value[0:4])[0]
        is_reply = struct.unpack(b'?', value[4:5])[0]
        author = value[5:]
        return cls(author=author, identifier=identifier, timestamp=timestamp,
                is_reply=is_reply)

    def serialize_key(self):
        """Serialize database key."""
        return b'post-' + self.identifier

    def serialize_value(self):
        """Serialize database value."""
        timestamp = struct.pack(b'<I', self.timestamp)
        is_reply = struct.pack(b'?', self.is_reply)
        value = b''.join([timestamp, is_reply, self.author])
        return value

    def serialize(self):
        """Serialize for storage in the database."""
        key = self.serialize_key()
        value = self.serialize_value()
        return (key, value)
