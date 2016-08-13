import logging
import time

import grapheneapi
from piston.steem import Steem

from steemvote.db import DB
from steemvote.models import Comment

# Number of votes allotted each day.
DAILY_VOTE_ALLOTMENT = 20
# Default fraction of voting power to use.
DEFAULT_TARGET_VOTING_POWER_USE = 0.75 # 75%
# Default maximum age of posts to vote on.
DEFAULT_MAX_POST_AGE = 2 * 24 * 60 * 60 # 2 days.

class ConfigError(Exception):
    """Exception raised when not enough configuration was done."""
    pass

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
        # Target fraction of voting power to use.
        self.target_voting_power_use = config.get_decimal('target_voting_power_use', DEFAULT_TARGET_VOTING_POWER_USE)
        # Maximum age of posts to vote for.
        self.max_post_age = config.get_seconds('max_post_age', DEFAULT_MAX_POST_AGE)
        # Voter account name.
        self.voter_account = config.get('voter_account_name', '')
        # Vote private key.
        self.wif = config.get('vote_key', '')

        self.rpc_node = config.get('rpc_node')
        self.rpc_user = config.get('rpc_user')
        self.rpc_pass = config.get('rpc_pass')

        self.db = DB(config)

        # Time that stats were last calculated at.
        self.last_stats_update = 0
        # Current voting power that we've used.
        self.current_used_voting_power = 0.0

        self.update_stats()

    def is_running(self):
        return self.running

    def stop(self):
        self.running = False
        self.db.close()
        self.logger.debug('Stopped')

    def run(self):
        self.logger.debug('Connecting to Steem')
        # We use nobroadcast=True so we can handle exceptions better.
        self.steem = Steem(node=self.rpc_node, rpcuser=self.rpc_user,
            rpcpassword=self.rpc_pass, wif=self.wif, nobroadcast=True,
            apis=['database', 'network_broadcast'])
        self.logger.debug('Connected. Started monitor')

        self.running = True
        self.monitor()

    def use_backup_authors(self):
        """Get whether to vote for backup authors.

        Backup authors are voted for if the current voting power use
        is less than 50% of the target voting power use.
        """
        return self.current_used_voting_power < self.target_voting_power_use * 0.5

    def should_vote(self, comment):
        """Get whether comment should be voted on."""
        author = self.config.get_author(comment.author, self.use_backup_authors())
        if not author:
            return False
        if comment.is_reply and not author.vote_replies:
            return False
        # Do not vote if the post is too old.
        if time.time() - comment.timestamp > self.max_post_age:
            return False
        # Do not vote if we're using too much voting power.
        if self.current_used_voting_power >= self.target_voting_power_use:
            return False
        return True

    def monitor(self):
        """Monitor new comments and process them."""
        iterator = self.steem.stream_comments()
        while self.is_running():
            self.update_stats()
            try:
                comment = next(iterator)
                comment = Comment.from_dict(comment)
                if self.should_vote(comment):
                    self.db.add_comment(comment)
            except Exception as e:
                self.logger.error(str(e))
                break
        self.logger.debug('Monitor thread stopped')

    def get_stats(self):
        """Get runtime statistics."""
        stats = {}
        stats['Current voting power use'] = self.current_used_voting_power
        return stats

    def update_stats(self):
        """Update runtime statistics."""
        now = time.time()
        if now - self.last_stats_update < self.stats_update_interval:
            return
        self.update_voting_power_use()
        self.last_stats_update = now

    def update_voting_power_use(self):
        """Recalculate the current voting power that we've used."""
        votes = self.db.get_votes_in_last_day()
        self.current_used_voting_power = float(len(votes)) / DAILY_VOTE_ALLOTMENT

    def vote_ready_comments(self):
        """Vote on the comments that are ready."""
        comments = self.db.get_comments_to_vote()
        vote_times = []
        for comment in comments:
            # Skip if the rules have changed for the author.
            if not self.should_vote(comment):
                self.logger.debug('Skipping %s' % comment.identifier)
                continue
            author = self.config.get_author(comment.author, self.use_backup_authors())
            tx = self.steem.vote(str(comment.identifier, 'utf-8'), author.weight, voter=self.voter_account)
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
            else:
                vote_times.append(int(time.time()))

        self.db.update_voted_comments(comments)
        self.db.update_vote_times(vote_times)
