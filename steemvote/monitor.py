import logging
import threading
import time

import grapheneapi
from piston.steem import Steem

from steemvote.config import ConfigError
from steemvote.db import DB
from steemvote.models import Comment, Voter

# Default maximum remaining voting power.
DEFAULT_MAXIMUM_VOTING_POWER = 0.95
# Default minimum remaining voting power.
DEFAULT_MINIMUM_VOTING_POWER = 0.90 # 90%
# Default minimum age of posts to vote on.
DEFAULT_MIN_POST_AGE = 60 # 1 minute.
# Default maximum age of posts to vote on.
DEFAULT_MAX_POST_AGE = 2 * 24 * 60 * 60 # 2 days.

class Monitor(object):
    """Monitors Steem posts."""
    def __init__(self, config):
        self.config = config
        self.running = False
        self.steem = None
        self.logger = logging.getLogger(__name__)

        config.require('voter_account_name')
        config.require('vote_key')
        config.require('authors')

        # Interval for calculating stats.
        self.stats_update_interval = 20
        # Minimum available voting power.
        self.min_voting_power = config.get_decimal('min_voting_power', DEFAULT_MINIMUM_VOTING_POWER)
        # Maximum available voting power.
        # Steemvote will attempt to use more power than normal if current
        # voting power is greater than this.
        self.max_voting_power = config.get_decimal('max_voting_power', DEFAULT_MAXIMUM_VOTING_POWER)
        # The maximum voting power must not be less than the minimum voting power.
        if self.max_voting_power < self.min_voting_power:
            raise ConfigError('"max_voting_power" must not be less than "min_voting_power"')

        # Categories to ignore posts in.
        self.blacklisted_categories = config.get('blacklist_categories', [])
        # Minimum age of posts to vote for.
        self.min_post_age = config.get_seconds('min_post_age', DEFAULT_MIN_POST_AGE)
        # Maximum age of posts to vote for.
        self.max_post_age = config.get_seconds('max_post_age', DEFAULT_MAX_POST_AGE)
        # Voter account.
        voter_account = config.get('voter_account_name')
        wif = config.get('vote_key')
        self.voter = Voter(voter_account, wif)

        self.rpc_node = config.get('rpc_node')
        self.rpc_user = config.get('rpc_user')
        self.rpc_pass = config.get('rpc_pass')

        self.db = DB(config)
        self.voting_lock = threading.Lock()

        # Time that stats were last calculated at.
        self.last_stats_update = 0

    def is_running(self):
        return self.running

    def stop(self):
        self.running = False
        self.db.close()
        self.logger.debug('Stopped')

    def run(self):
        self.connect()
        self.logger.debug('Connected. Started monitor')

        self.running = True
        self.monitor()

    def connect(self):
        """Instantiate Steem and load database."""
        self.logger.debug('Connecting to Steem')
        # We use nobroadcast=True so we can handle exceptions better.
        self.steem = Steem(node=self.rpc_node, rpcuser=self.rpc_user,
            rpcpassword=self.rpc_pass, wif=self.voter.wif, nobroadcast=True,
            apis=['database', 'network_broadcast'])
        self.db.load(self.steem)

    def use_backup_authors(self):
        """Get whether to vote for backup authors.

        Backup authors are voted for if the current voting power
        is greater than the maximum voting power.
        """
        return self.voter.current_voting_power > self.max_voting_power

    def should_vote(self, comment):
        """Get whether comment should be voted on.

        Returns:
            A 2-tuple of (should_vote, reason). should_vote is a
            bool, and reason contains the reason not to vote
            if should_vote is False.
        """
        author = self.config.get_author(comment.author, self.use_backup_authors())
        if not author:
            return (False, 'author is unknown')
        if comment.is_reply() and not author.vote_replies:
            return (False, 'comment is a reply')
        # Do not vote if the post is in a blacklisted category.
        if comment.category in self.blacklisted_categories:
            return (False, 'comment is in a blacklisted category')
        # Do not vote if the post is too old.
        if time.time() - comment.timestamp > self.max_post_age:
            return (False, 'comment is too old')
        # Do not vote if we're using too much voting power.
        if self.voter.current_voting_power < self.min_voting_power:
            return (False, 'voter does not have enough voting power (current: %s)' % self.voter.get_voting_power())
        return (True, '')

    def monitor(self):
        """Monitor new comments and process them."""
        iterator = self.steem.stream_comments()
        while self.is_running():
            self.update_stats()
            try:
                comment = Comment(self.steem, next(iterator))
                if self.should_vote(comment)[0]:
                    self.db.add_comment(comment)
            except ValueError as e:
                self.logger.debug('Invalid comment. Skipping')
            except Exception as e:
                self.logger.error(str(e))
                break
        self.logger.debug('Monitor thread stopped')

    def get_stats(self):
        """Get runtime statistics."""
        stats = {}
        stats['Current voting power'] = self.voter.current_voting_power
        return stats

    def update_stats(self):
        """Update runtime statistics."""
        now = time.time()
        if now - self.last_stats_update < self.stats_update_interval:
            return
        self.voter.update(self.steem)
        self.last_stats_update = now

    def vote_ready_comments(self):
        """Vote on the comments that are ready."""
        with self.voting_lock:
            comments = self.db.get_comments_to_vote(self.min_post_age)
            for comment in comments:
                # Skip if the rules have changed for the author.
                should_vote, reason = self.should_vote(comment)
                if not should_vote:
                    self.logger.debug('Skipping %s because %s' % (comment.identifier, reason))
                    continue
                author = self.config.get_author(comment.author, self.use_backup_authors())
                tx = self.steem.vote(comment.identifier, author.weight, voter=self.voter.name)
                try:
                    self.steem.rpc.broadcast_transaction(tx, api='network_broadcast')
                    self.logger.info('Upvoted %s' % comment.identifier)
                except grapheneapi.graphenewsrpc.RPCError as e:
                    already_voted_messages = [
                        'Changing your vote requires',
                        'Cannot vote again',
                    ]
                    if e.args and any(i in e.args[0] for i in already_voted_messages):
                        self.logger.info('Skipping already-voted post %s' % comment.identifier)
                    else:
                        raise e

            self.db.update_voted_comments(comments)
