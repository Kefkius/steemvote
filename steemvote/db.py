import logging
import struct
import threading
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

        self.comment_lock = threading.Lock()
        self.vote_time_lock = threading.Lock()

    def close(self):
        self.db.close()

    def add_comment(self, comment):
        """Add a comment to be voted on later."""
        with self.comment_lock:
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
        with self.comment_lock:
            wb = self.db.write_batch()
            for comment in comments:
                self.update_voted_comment(comment, wb)
            wb.write()

    def get_comments_to_vote(self):
        """Get the comments that are ready for voting."""
        now = time.time()
        comments = []
        with self.comment_lock:
            for key, value in self.db.iterator(prefix=b'post-'):
                comment = Comment.deserialize(key, value)
                if now - comment.timestamp > self.vote_delay:
                    comments.append(comment)

        return comments

    def update_vote_times(self, vote_times):
        """Add vote_times to the most recent votes."""
        with self.vote_time_lock:
            new_vote_times = b''.join([struct.pack(b'<I', i) for i in vote_times])
            last_votes = self.db.get(b'last-votes', b'')
            last_votes += new_vote_times
            # Only keep the last 20 votes.
            if len(last_votes) > 80:
                last_votes = last_votes[-80:]

            self.db.put(b'last-votes', last_votes)

    def get_last_votes(self):
        """Get the most recent vote timestamps."""
        with self.vote_time_lock:
            last_votes = self.db.get(b'last-votes', b'')
            timestamps = []
            while last_votes:
                timestamps.append(struct.unpack(b'<I', last_votes[0:4])[0])
                last_votes = last_votes[4:]
            return timestamps

    def get_votes_in_last_day(self):
        """Get the number of votes cast in the last 24 hours."""
        one_day_ago = time.time() - 24 * 60 * 60
        timestamps = list(filter(lambda i: i >= one_day_ago, self.get_last_votes()))
        return timestamps
