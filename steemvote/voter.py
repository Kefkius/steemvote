import datetime
import logging
import threading
import time

import grapheneapi
from piston.steem import Steem

from steemvote.config import ConfigError
from steemvote.db import DB

STEEMIT_100_PERCENT = 10000
STEEMIT_VOTE_REGENERATION_SECONDS = 5*60*60*24 # 5 days

class Voter(object):
    """Voter settings and functionality.

    This class is used by first calling connect_to_steem(),
    then calling vote_for_comments() whenever the database
    should be checked for eligible comments.
    """
    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.steem = None
        # Current voting power that we have.
        self.current_voting_power = 0.0
        # Interval for updating stats.
        self.update_interval = 20
        # Last time that stats were updated via RPC.
        self.last_update = 0

        self.config_lock = threading.Lock()
        self.voting_lock = threading.Lock()

        # Load settings from config.

        config.require('voter_account_name')
        config.require('vote_key')

        self.name = config.get('voter_account_name')
        self.wif = config.get('vote_key')

        self.load_settings()

        self.db = DB(config)

    def load_settings(self):
        """Load settings from config."""
        with self.config_lock:
            config = self.config
            # Minimum age of posts to vote for.
            self.min_post_age = config.get_seconds('min_post_age')
            # Maximum age of posts to vote for.
            self.max_post_age = config.get_seconds('max_post_age')

            # Minimum available voting power.
            self.min_voting_power = config.get_decimal('min_voting_power')
            # Maximum available voting power.
            # Steemvote will attempt to use more power than normal if current
            # voting power is greater than this.
            self.max_voting_power = config.get_decimal('max_voting_power')
            # The maximum voting power must not be less than the minimum voting power.
            if self.max_voting_power < self.min_voting_power:
                raise ConfigError('"max_voting_power" must not be less than "min_voting_power"')

            # Categories to ignore posts in.
            self.blacklisted_categories = config.get('blacklist_categories', [])

            self.rpc_node = config.get('rpc_node')
            self.rpc_user = config.get('rpc_user')
            self.rpc_pass = config.get('rpc_pass')

    def connect_to_steem(self):
        """Connect to a Steem node."""
        self.logger.debug('Connecting to Steem')
        # We use nobroadcast=True so we can handle exceptions better.
        self.steem = Steem(node=self.rpc_node, rpcuser=self.rpc_user,
            rpcpassword=self.rpc_pass, wif=self.wif, nobroadcast=True,
            apis=['database', 'network_broadcast'])
        self.db.load(self.steem)
        self.logger.debug('Connected')

    def close(self):
        self.db.close()
        self.logger.debug('Stopped')

    def update(self):
        """Update voter stats."""
        now = time.time()
        # Only update stats every interval.
        if now - self.last_update < self.update_interval:
            return

        d = self.steem.rpc.get_account(self.name)
        if 'voting_power' not in d.keys():
            msg = 'Invalid get_accounts() response: %s' % d
            self.logger.error(msg)
            raise Exception(msg)
        # Calculate our current voting power.
        # From vote_evaluator::do_apply in https://github.com/steemit/steem/blob/master/libraries/chain/steem_evaluator.cpp.
        last_vote_time = datetime.datetime.strptime(d.get('last_vote_time', "1970-01-01T00:00:00"), '%Y-%m-%dT%H:%M:%S')
        last_vote_time = last_vote_time.replace(tzinfo=datetime.timezone.utc).timestamp()
        elapsed_seconds = int(now - last_vote_time)

        regenerated_power = (STEEMIT_100_PERCENT * elapsed_seconds) / STEEMIT_VOTE_REGENERATION_SECONDS
        current_power = min(d['voting_power'] + regenerated_power, STEEMIT_100_PERCENT)
        self.current_voting_power = round(float(current_power) / STEEMIT_100_PERCENT, 4)

        self.last_update = now

    def get_voting_power(self):
        """Get our current voting power as a string."""
        return '{voting_power:.{decimals}%}'.format(voting_power=self.current_voting_power,
                    decimals=len(str(self.current_voting_power)) - 3)

    def use_backup_authors(self):
        """Get whether to vote for backup authors.

        Backup authors are voted for if the current voting power
        is greater than the maximum voting power.
        """
        return self.current_voting_power > self.max_voting_power

    def should_vote(self, comment):
        """Get whether comment should be voted on.

        Returns:
            A 2-tuple of (should_vote, reason). should_vote is a
            bool, and reason contains the reason not to vote
            if should_vote is False.
        """
        with self.config_lock:
            # Do not vote if the post has curation disabled.
            if not comment.allow_curation_rewards or not comment.allow_votes:
                return False
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
            if self.current_voting_power < self.min_voting_power:
                return (False, 'voter does not have enough voting power (current: %s)' % self.get_voting_power())
            return (True, '')

    def _vote(self, identifier, weight):
        """Create and broadcast a vote for identifier."""
        tx = self.steem.vote(identifier, weight, voter=self.name)
        try:
            self.steem.rpc.broadcast_transaction(tx, api='network_broadcast')
            self.logger.info('Voted on %s' % identifier)
        except grapheneapi.graphenewsrpc.RPCError as e:
            already_voted_messages = [
                'Changing your vote requires',
                'Cannot vote again',
            ]
            if e.args and any(i in e.args[0] for i in already_voted_messages):
                self.logger.info('Skipping already-voted post %s' % identifier)
            else:
                raise e

    def vote_for_comments(self):
        """Vote on the comments that are ready."""
        if not self.steem:
            raise Exception('Not connected to a Steem node')

        with self.voting_lock:
            comments = self.db.get_comments_to_vote(self.min_post_age)
            for comment in comments:
                # Skip if the rules have changed for the author.
                should_vote, reason = self.should_vote(comment)
                if not should_vote:
                    self.logger.debug('Skipping %s because %s' % (comment.identifier, reason))
                    continue
                author = self.config.get_author(comment.author, self.use_backup_authors())
                self._vote(comment.identifier, author.weight)

            self.db.update_voted_comments(comments)
