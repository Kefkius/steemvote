import json
import os

import humanfriendly

from steemvote.models import Author


class ConfigError(Exception):
    """Exception raised when not enough configuration is invalid."""
    pass

class Config(object):
    def __init__(self):
        self.filepath = ''
        self.options = {}

    def get(self, key, value=None):
        return self.options.get(key, value)

    def get_seconds(self, key, value=None):
        """Get a value that represents a number of seconds."""
        val = self.get(key, value)
        if isinstance(val, str):
            val = int(humanfriendly.parse_timespan(val))
        return val

    def set(self, key, value):
        self.options[key] = value

    def require(self, key):
        """Raise if a key is not present."""
        if not self.get(key):
            raise ConfigError('Configuration value for "%s" is required' % key)

    def save(self):
        s = json.dumps(self.options, indent=4, sort_keys=True)
        with open(self.filepath, 'w') as f:
            f.write(s)

    def load(self, filepath=''):
        if not filepath:
            filepath = 'steemvote-config.json'
        if not os.path.exists(filepath):
            return
        with open(filepath) as f:
            options = json.load(f)
        self.options = options
        self.filepath = filepath

        self.load_authors()

    def load_authors(self):
        """Load authors from config."""
        authors = self.get('authors', [])
        self.authors = [Author.from_dict(i) for i in authors]

    def get_author(self, name):
        """Get an author by name."""
        for author in self.authors:
            if author.name == name:
                return author

    def set_authors(self, authors):
        """Set authors and save."""
        if not all(isinstance(i, Author) for i in authors):
            raise TypeError('A list of authors is required')
        self.authors = authors
        self.save()
