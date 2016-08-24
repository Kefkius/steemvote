import logging
import struct
import threading
import time

import plyvel

from steemvote.models import Comment

class DBVersionError(Exception):
    """Exception raised when an incompatible database version is encountered."""
    pass

class DB(object):
    """Database for storing post data."""
    # Current database version.
    db_version = '0.1.0'

    @staticmethod
    def voted_key(identifier):
        """Get the key for a voted post with identifier."""
        return b'voted-' + identifier

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        self.path = config.get('database_path', 'database/')

        self.db = plyvel.DB(self.path, create_if_missing=True)
        self.check_version()
        self.comment_lock = threading.Lock()

        self.tracked_comments = {}

    def check_version(self):
        """Check the database version and update it if possible."""
        version = self.get_version()
        # Version is '0.0.0' if from before db version was stored.
        if version < '0.1.0':
            self.logger.warning('Incompatible or nonexistent database. Creating new database')
            self.db.close()
            plyvel.destroy_db(self.path)
            self.db = plyvel.DB(self.path, create_if_missing=True)
            self.set_version()
        # Handle future db versions.
        elif version > self.db_version:
            raise DBVersionError('Stored database version (%s) is greater than current version (%s)' % (version, self.db_version))

    def get_version(self):
        """Get the stored database version."""
        return str(self.db.get(b'db-version', b'0.0.0'), 'utf-8')

    def set_version(self):
        """Store the current database version."""
        self.db.put(b'db-version', bytes(self.db_version, 'utf-8'))

    def load(self, steem):
        """Load state."""
        # Load the comments to be voted on.
        for key, value in self.db.iterator(prefix=b'post-'):
            if value == b'1':
                continue
            comment = Comment.deserialize_key(key, steem)
            self.tracked_comments[comment.identifier] = comment

    def close(self):
        self.db.close()

    def add_comment(self, comment):
        """Add a comment to be voted on later."""
        with self.comment_lock:
            # Check if the post is already voted on in the database.
            if self.db.get(comment.serialize_key(), b'0') != b'0':
                return

            self.db.put(comment.serialize_key(), b'0')
            self.tracked_comments[comment.identifier] = comment
            self.logger.info('Added %s' % comment.identifier)

    def update_voted_comments(self, comments):
        """Update comments that have been voted on."""
        with self.comment_lock:
            wb = self.db.write_batch()
            for comment in comments:
                wb.put(comment.serialize_key(), b'1')
            wb.write()

            for identifier in [comment.identifier for comment in comments]:
                if self.tracked_comments.get(identifier):
                    del self.tracked_comments[identifier]

    def get_comments_to_vote(self, minimum_age):
        """Get the comments that are ready for voting."""
        now = time.time()
        comments = []
        with self.comment_lock:
            for comment in self.tracked_comments.values():
                if now - comment.timestamp > minimum_age:
                    comments.append(comment)

        return comments
