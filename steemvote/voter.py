import datetime
import logging
import threading
import time

import grapheneapi

from steemvote.config import ConfigError
from steemvote.db import DB
from steemvote.models import Priority
from steemvote.rpcnode import SteemvoteSteem

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

        self.config_lock = threading.RLock()
        self.voting_lock = threading.Lock()

        # Load settings from config.

        config.require('voter_account_name')
        config.require('vote_key')
        config.require_class('blacklist_categories', list)

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
            if self.min_post_age > self.max_post_age:
                raise ValueError('Minimum post age cannot be more than maximum post age')

            # Required remaining voting power to vote for each priority of comments.
            self.priority_voting_powers = priorities = {
                Priority.low: config.get_decimal('priority_low'),
                Priority.normal: config.get_decimal('priority_normal'),
                Priority.high: config.get_decimal('priority_high'),
            }
            if not priorities[Priority.low] >= priorities[Priority.normal] >= priorities[Priority.high]:
                raise ValueError('Priority voting powers must be: low >= normal >= high')

            # Categories to ignore posts in.
            self.blacklisted_categories = config.get('blacklist_categories')

            self.rpc_node = config.get('rpc_node')
            self.rpc_user = config.get('rpc_user')
            self.rpc_pass = config.get('rpc_pass')

    def connect_to_steem(self):
        """Connect to a Steem node."""
        self.logger.debug('Connecting to Steem')
        # We use nobroadcast=True so we can handle exceptions better.
        self.steem = SteemvoteSteem(node=self.rpc_node, rpcuser=self.rpc_user,
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

    def is_prioritized(self, priority):
        """Get whether a comment with the given priority should be voted for."""
        return self.current_voting_power >= self.priority_voting_powers[priority]

    def get_voting_weight(self, comment):
        """Get the weight that comment should be voted for with."""
        with self.config_lock:
            author = self.config.get_author(comment.author)
            if author:
                return author.weight
            delegates = self._get_voted_delegates(comment)
            if delegates:
                return max([i.weight for i in delegates])

        raise Exception('Comment should not be voted for')

    def _get_voted_delegates(self, comment):
        """Get the delegates that have voted on comment."""
        with self.config_lock:
            my_delegates = {i.name: i for i in self.config.delegates}
            voted_delegates = comment.get_have_voted(my_delegates.keys())

        result = []
        for delegate_name in voted_delegates:
            result.append(my_delegates[delegate_name])
        return result

    def should_track(self, comment):
        """Get whether comment should be tracked.

        This is a less-strict form of should_vote().

        Returns:
            A 2-tuple of (should_track, reason). should_track is a
            bool, and reason contains the reason not to track the comment
            if should_track is False.
        """
        # Check if the comment has curation disabled.
        if not comment.allow_curation_rewards or not comment.allow_votes:
            return (False, 'comment does not allow curation')
        with self.config_lock:
            # Check if the post is in a blacklisted category.
            if comment.category in self.blacklisted_categories:
                return (False, 'comment is in a blacklisted category')
            # Check if the post is too old.
            if time.time() - comment.timestamp > self.max_post_age:
                return (False, 'comment is too old')
        return (True, '')

    def should_track_for_author(self, comment):
        """Get whether comment should be tracked, based on its author."""
        should_track = self.should_track(comment)
        if not should_track[0]:
            return should_track
        with self.config_lock:
            # Check if the author isn't known to steemvote.
            author = self.config.get_author(comment.author)
            if not author:
                return (False, 'author is unknown')
            # Check if we omit replies by the author.
            if comment.is_reply() and not author.vote_replies:
                return (False, 'comment is a reply')
        return (True, '')

    def should_track_for_delegate(self, comment):
        """Get whether comment should be tracked, based on delegate votes."""
        should_track = self.should_track(comment)
        if not should_track[0]:
            return should_track
        with self.config_lock:
            if not self._get_voted_delegates(comment):
                return (False, 'no delegates have voted for comment')
        print('Delegate voted, should track %s' % comment.identifier)
        return (True, '')

    def _should_vote_author(self, comment):
        """Get whether comment should be voted on, based on its author."""
        with self.config_lock:
            # Check if the priority is high enough given our voting power.
            author = self.config.get_author(comment.author)
            if not author or not self.is_prioritized(author.priority):
                return (False, 'author does not have a high enough priority')
        return (True, '')

    def _should_vote_delegates(self, comment):
        """Get whether comment should be voted on, based on delegate votes."""
        with self.config_lock:
            delegates = self._get_voted_delegates(comment)
            if not delegates:
                return (False, 'delegate votes are no longer present')
            if not any(self.is_prioritized(priority) for priority in [i.priority for i in delegates]):
                return (False, 'no delegates with a high enough priority')

        return (True, '')

    def should_vote(self, comment):
        """Get whether comment should be voted on.

        Returns:
            A 2-tuple of (should_vote, reason). should_vote is a
            bool, and reason contains the reason not to vote
            if should_vote is False.
        """
        # First check against the less-strict should_track() rules.
        should_track = self.should_track(comment)
        if not should_track[0]:
            return should_track
        # Then check against rules that depend on context.
        with self.config_lock:
            # Check if the comment is too young.
            if time.time() - comment.timestamp < self.min_post_age:
                return (False, 'comment is too young')
            should_vote_author = self._should_vote_author(comment)
            should_vote_delegates = self._should_vote_delegates(comment)
            if not should_vote_author[0] and not should_vote_delegates[0]:
                return should_vote_author
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

        # Comments that have been voted on.
        voted_comments = []
        # Identifiers of comments that should no longer be tracked.
        old_identifiers = []

        with self.voting_lock:
            comments = self.db.get_tracked_comments()
            for comment in comments:
                # Skip if the comment shouldn't be voted on now.
                if not self.should_vote(comment)[0]:
                    # Check whether to stop tracking the comment.
                    keep_tracking, reason = self.should_track(comment)
                    if not keep_tracking:
                        old_identifiers.append(comment.identifier)
                        self.logger.debug('Stop tracking %s because %s' % (comment.identifier, reason))
                # Vote for the comment.
                else:
                    weight = self.get_voting_weight(comment)
                    self._vote(comment.identifier, weight)
                    voted_comments.append(comment)

            self.db.update_voted_comments(voted_comments)
            self.db.remove_tracked_comments(old_identifiers)
