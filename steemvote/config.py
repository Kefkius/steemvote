import json
import os

import yaml
import humanfriendly

from steemvote.models import Author

# Default maximum remaining voting power.
DEFAULT_MAX_VOTING_POWER = 0.95 # 95%
# Default minimum remaining voting power.
DEFAULT_MIN_VOTING_POWER = 0.90 # 90%
# Default minimum age of posts to vote on.
DEFAULT_MIN_POST_AGE = 60 # 1 minute.
# Default maximum age of posts to vote on.
DEFAULT_MAX_POST_AGE = 2 * 24 * 60 * 60 # 2 days.

def get_decimal(data):
    """Parse data into a decimal."""
    if isinstance(data, float):
        return data
    elif data.endswith('%'):
        return float(data.strip('%')) / 100
    # Try to parse a float string (e.g. "0.5").
    if '.' in data:
        return float(data)
    raise ValueError('A percentage or decimal fraction is required')

class ConfigError(Exception):
    """Exception raised when configuration is invalid."""
    pass

class Config(object):
    def __init__(self):
        self.filepath = ''
        self.config_format = 'json'
        self.options = {}
        self.defaults = {
            'min_post_age': DEFAULT_MIN_POST_AGE,
            'max_post_age': DEFAULT_MAX_POST_AGE,
            'min_voting_power': DEFAULT_MIN_VOTING_POWER,
            'max_voting_power': DEFAULT_MAX_VOTING_POWER,
        }

    def get(self, key, value=None):
        """Get a value.

        If no default is specified, the default in self.defaults will
        be used if no value is found.
        """
        result = self.options.get(key, value)
        if result is None and value is None:
            return self.defaults.get(key)
        return result

    def get_decimal(self, key, value=None):
        """Get a value that represents a percentage."""
        val = self.get(key, value)
        try:
            return get_decimal(val)
        except Exception as e:
            raise ConfigError('Invalid config value "%s" for key "%s" (Error: %s)' % (val, key, str(e)))

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

    def update_old_keys(self):
        """Update old keys for backwards compatibility."""
        # Change "vote_delay" to "min_post_age".
        if self.get('vote_delay') is not None and self.get('min_post_age') is None:
            self.set('min_post_age', self.get('vote_delay'))

    def save(self):
        options = dict(self.options)
        options['authors'] = [i.to_dict() for i in self.authors]
        options['backup_authors'] = [i.to_dict() for i in self.backup_authors]

        if self.config_format == 'json':
            s = json.dumps(options, indent=4, sort_keys=True)
        elif self.config_format == 'yaml':
            s = yaml.dump(options, indent=4)
        with open(self.filepath, 'w') as f:
            f.write(s)

    def _load_json(self, filepath):
        """Load JSON config."""
        options = {}
        try:
            with open(filepath) as f:
                options = json.load(f)
            self.config_format = 'json'
        except Exception:
            pass
        return options

    def _load_yaml(self, filepath):
        """Load YAML config."""
        options = {}
        try:
            with open(filepath) as f:
                options = yaml.load(f)
            self.config_format = 'yaml'
        except Exception:
            pass
        return options

    def load(self, filepath=''):
        if not filepath:
            filepath = 'steemvote-config.json'
        if not os.path.exists(filepath):
            filepath = 'steemvote-config.yaml'
            if not os.path.exists(filepath):
                return

        if filepath.endswith('.json'):
            options = self._load_json(filepath)
        elif filepath.endswith('.yaml'):
            options = self._load_yaml(filepath)
        self.options = options
        self.filepath = filepath

        self.update_old_keys()
        self.load_authors()

    def load_authors(self):
        """Load authors from config."""
        authors = self.get('authors', [])
        self.authors = [Author.from_config(i) for i in authors]

        backup_authors = self.get('backup_authors', [])
        self.backup_authors = [Author.from_config(i) for i in backup_authors]

    def get_author(self, name, include_backup_authors=False):
        """Get an author by name."""
        for author in self.authors:
            if author.name == name:
                return author
        if not include_backup_authors:
            return
        # Search for the author in the backup authors list.
        for author in self.backup_authors:
            if author.name == name:
                return author

    def set_authors(self, authors):
        """Set authors and save."""
        if not all(isinstance(i, Author) for i in authors):
            raise TypeError('A list of authors is required')
        self.authors = authors
        self.save()

    def set_backup_authors(self, backup_authors):
        """Set backup authors and save."""
        if not all(isinstance(i, Author) for i in backup_authors):
            raise TypeError('A list of authors is required')
        self.backup_authors = backup_authors
        self.save()
