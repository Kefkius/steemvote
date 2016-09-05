import enum
import logging
import struct
import threading
import time

import plyvel

from steemvote.models import Comment

class DBVersionError(Exception):
    """Exception raised when an incompatible database version is encountered."""
    pass

class CommentAction(enum.Enum):
    """Constants for actions taken on comments."""
    # Comment has been voted on.
    voted = b'1'
    # Comment is being tracked.
    tracked = b'2'
    # Comment should not be tracked.
    skipped = b'3'

class DB(object):
    """Database for storing post data."""
    # Current database version.
    db_version = '0.1.1'

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        self.path = config.get('database_path', 'database/')

        self.db = plyvel.DB(self.path, create_if_missing=True)
        self.check_version()
        self.comment_lock = threading.RLock()

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
        elif version < '0.1.1':
            self.logger.info('Updating database to 0.1.1')
            wb = self.db.write_batch()
            for key, value in self.db.iterator(prefix=b'post'):
                if value == b'0':
                    wb.put(key, CommentAction.tracked.value)
            wb.write()
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
            if value != CommentAction.tracked.value:
                continue
            comment = Comment.deserialize_key(key, steem)
            self.tracked_comments[comment.identifier] = comment

    def close(self):
        self.db.close()

    def add_comment(self, comment):
        """Add a comment to be voted on later."""
        with self.comment_lock:
            # Check if the post is already in the database.
            if self.db.get(comment.serialize_key()) is not None:
                return

            self.db.put(comment.serialize_key(), CommentAction.tracked.value)
            self.tracked_comments[comment.identifier] = comment
            self.logger.info('Added %s' % comment.identifier)

    def update_voted_comments(self, comments):
        """Update comments that have been voted on."""
        with self.comment_lock:
            wb = self.db.write_batch()
            for comment in comments:
                wb.put(comment.serialize_key(), CommentAction.voted.value)
            wb.write()

            self.remove_tracked_comments([comment.identifier for comment in comments])

    def get_tracked_comments(self):
        """Get the comments that are being tracked."""
        with self.comment_lock:
            comments = list(self.tracked_comments.values())
        return comments

    def remove_tracked_comments(self, identifiers):
        """Stop tracking comments with the given identifiers."""
        with self.comment_lock:
            wb = self.db.write_batch()
            for identifier in identifiers:
                key = Comment.serialize_key_from_identifier(identifier)
                if self.db.get(key) == CommentAction.tracked.value:
                    wb.put(key, CommentAction.skipped.value)
                if identifier in self.tracked_comments:
                    del self.tracked_comments[identifier]
            wb.write()
