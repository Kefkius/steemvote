import logging
import time

import plyvel

from steemvote.models import Comment

class DB(object):
    """Database for storing post data."""
    @staticmethod
    def voted_key(identifier):
        """Get the key for a voted post with identifier."""
        return b'voted-' + identifier

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        self.path = config.get('database_path', 'database/')
        # Vote on posts that are >= 1 minute old by default.
        self.vote_delay = config.get_seconds('vote_delay', 60)

        self.db = plyvel.DB(self.path, create_if_missing=True)

    def close(self):
        self.db.close()

    def add_comment(self, comment):
        """Add a comment to be voted on later."""
        # Check if the post has been voted on.
        if self.db.get(self.voted_key(comment.identifier)):
            return
        # Check if the post is already in the database.
        if self.db.get(comment.serialize_key()):
            return

        self.logger.info('Adding %s' % comment.identifier)
        key, value = comment.serialize()
        self.db.put(key, value)

    def update_voted_comment(self, comment, write_batch=None):
        wb = write_batch if write_batch else self.db.write_batch()
        wb.delete(comment.serialize_key())
        wb.put(self.voted_key(comment.identifier), b'1')

        if not write_batch:
            wb.write()

    def update_voted_comments(self, comments):
        """Update comments that have been voted on."""
        wb = self.db.write_batch()
        for comment in comments:
            self.update_voted_comment(comment, wb)
        wb.write()

    def get_comments_to_vote(self):
        """Get the comments that are ready for voting."""
        now = time.time()
        comments = []

        for key, value in self.db.iterator(prefix=b'post-'):
            comment = Comment.deserialize(key, value)
            if now - comment.timestamp > self.vote_delay:
                comments.append(comment)

        return comments
