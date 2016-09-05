import json
import logging
import os

import yaml
import humanfriendly

from steemvote.models import Author, Priority

default_values = (
    # Default minimum age of posts to vote on.
    ('min_post_age', 60), # 1 minute.
    # Default maximum age of posts to vote on.
    ('max_post_age', 2 * 24 * 60 * 60), # 2 days.

    # Default high priority voting power.
    ('priority_high', 0.8), # 80%
    # Default normal priority voting power.
    ('priority_normal', 0.9), # 90%
    # Default low priority voting power.
    ('priority_low', 0.95), # 95%

    # Default categories to ignore.
    ('blacklist_categories', ['spam']),
)

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
    def __init__(self, no_saving=False):
        # True if unit tests are being run.
        self.no_saving = no_saving
        self.logger = logging.getLogger(__name__)
        self.filepath = ''
        self.config_format = 'json'
        self.options = {}
        self.defaults = {k: v for (k, v) in default_values}

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

    def require_class(self, key, cls):
        """Raise if the value of key is not an instance of cls."""
        value = self.get(key)
        if not isinstance(value, cls):
            raise ConfigError('Configuration value for "%s" must be a %s, not %s' % (key, cls.__name__, type(value).__name__))

    def update_old_keys(self):
        """Update old keys for backwards compatibility."""
        updated = False
        # Change "vote_delay" to "min_post_age".
        if self.get('vote_delay') is not None and self.get('min_post_age', -1) == -1:
            self.set('min_post_age', self.get('vote_delay'))
            self.logger.info('Updated old value "vote_delay" to "min_post_age"')
            del self.options['vote_delay']
            updated = True

        # 0.2 used "backup authors" - Convert those to low-priority authors.
        backup_authors = [Author.from_config(i) for i in self.get('backup_authors', [])]
        if backup_authors:
            for author in backup_authors:
                # Add the backup author as a low priority author
                # if it isn't in the main authors list.
                if not self.get_author(author.name):
                    author.priority = Priority.low
                    self.authors.append(author)
            self.logger.info('Updated old value "backup_authors" to low-priority authors')
            del self.options['backup_authors']
            updated = True
        # Change "min_voting_power" to "priority_high".
        if self.get('min_voting_power') is not None and self.get('priority_high', -1) == -1:
            self.set('priority_high', self.get('min_voting_power'))
            self.logger.info('Updated old value "min_voting_power" to "priority_high"')
            del self.options['min_voting_power']
            updated = True
        # Change "max_voting_power" to "priority_low".
        if self.get('max_voting_power') is not None and self.get('priority_low', -1) == -1:
            self.set('priority_low', self.get('max_voting_power'))
            self.logger.info('Updated old value "max_voting_power" to "priority_low"')
            del self.options['max_voting_power']
            updated = True

        if updated:
            self.save()

    def save(self):
        # Return if unit tests are being run.
        if self.no_saving:
            return
        options = dict(self.options)
        options['authors'] = [i.to_dict() for i in self.authors]

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
        self.options_loaded()

    def options_loaded(self):
        self.load_authors()
        self.update_old_keys()

    def load_authors(self):
        """Load authors from config."""
        authors = self.get('authors', [])
        self.authors = [Author.from_config(i) for i in authors]

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
