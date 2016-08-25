import logging
import sys
import time
import traceback

from piston.steem import Steem

from steemvote.models import Comment
from steemvote.voter import Voter


class Monitor(object):
    """Monitors Steem posts."""
    def __init__(self, voter):
        self.voter = voter
        self.config = voter.config
        self.running = False
        self.logger = logging.getLogger(__name__)

        self.config.require('authors')

        # Interval for calculating stats.
        self.stats_update_interval = 20
        # Time that stats were last calculated at.
        self.last_stats_update = 0

    @property
    def db(self):
        return self.voter.db

    @property
    def steem(self):
        return self.voter.steem

    def is_running(self):
        return self.running

    def stop(self):
        self.running = False

    def run(self):
        self.logger.debug('Starting monitor')
        self.running = True
        self.monitor()

    def monitor(self):
        """Monitor new comments and process them."""
        iterator = self.steem.stream_comments()
        while self.is_running():
            self.update_stats()
            try:
                comment = Comment(self.steem, next(iterator))
                if self.voter.should_vote(comment)[0]:
                    self.db.add_comment(comment)
            except ValueError as e:
                self.logger.debug('Invalid comment. Skipping')
            except Exception as e:
                self.logger.error(str(e))
                self.logger.error(''.join(traceback.format_tb(sys.exc_info()[2])))
                break
        self.logger.debug('Monitor thread stopped')

    def update_stats(self):
        """Update runtime statistics."""
        now = time.time()
        if now - self.last_stats_update < self.stats_update_interval:
            return
        self.voter.update(self.steem)
        self.last_stats_update = now
