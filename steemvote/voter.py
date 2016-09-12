from collections import namedtuple
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

ShouldTrack = namedtuple('ShouldTrack', ('track', 'reason',))
ShouldVote = namedtuple('ShouldVote', ('vote', 'track', 'reason',))

class Curator(object):
    """Decides whether to vote for things.
    """
    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.config = config
        # Current voting power that we have.
        # Subclasses must handle updating this value.
        self.current_voting_power = 0.0

        # Load settings from config.
        config.require_class('blacklist_authors', list)
        config.require_class('blacklist_categories', list)
        self.load_settings()

    def load_settings(self):
        """Load settings from config."""
        config = self.config
        # Minimum age of posts to vote for.
        self.min_post_age = config.get_seconds('min_post_age')
        # Maximum age of posts to vote for.
        self.max_post_age = config.get_seconds('max_post_age')
        if self.min_post_age > self.max_post_age:
            raise ConfigError('Minimum post age cannot be more than maximum post age')

        # Required remaining voting power to vote for each priority of comments.
        self.priority_voting_powers = priorities = {
            Priority.low: config.get_decimal('priority_low'),
            Priority.normal: config.get_decimal('priority_normal'),
            Priority.high: config.get_decimal('priority_high'),
        }
        if not priorities[Priority.low] >= priorities[Priority.normal] >= priorities[Priority.high]:
            raise ConfigError('Priority voting powers must be: low >= normal >= high')

        # Authors to ignore posts by.
        self.blacklisted_authors = config.get('blacklist_authors')
        # Categories to ignore posts in.
        self.blacklisted_categories = config.get('blacklist_categories')

    def _get_voted_delegates(self, comment):
        """Get the delegates that have voted on comment."""
        my_delegates = {i.name: i for i in self.config.delegates}
        voted_delegates = comment.get_have_voted(my_delegates.keys())

        result = []
        for delegate_name in voted_delegates:
            result.append(my_delegates[delegate_name])
        return result

    def is_blacklisted(self, comment):
        """Get whether comment is blacklisted."""
        return comment.author in self.blacklisted_authors or comment.category in self.blacklisted_categories

    def is_too_young(self, comment):
        """Get whether comment is too young."""
        return time.time() - comment.timestamp < self.min_post_age

    def is_too_old(self, comment):
        """Get whether comment is too old."""
        return time.time() - comment.timestamp > self.max_post_age

    def is_prioritized(self, priority):
        """Get whether a comment with the given priority should be voted for."""
        return self.current_voting_power >= self.priority_voting_powers[priority]

    def should_track(self, comment):
        """Get whether comment should be tracked.

        This is a less-strict form of should_vote().

        Returns:
            A ShouldTrack instance.
        """
        # Check if the comment has curation disabled.
        if not comment.allow_curation_rewards or not comment.allow_votes:
            return ShouldTrack(False, 'comment does not allow curation')
        # Check if the comment is blacklisted.
        if self.is_blacklisted(comment):
            return ShouldTrack(False, 'comment author/category is blacklisted')
        # Check if the comment is too old.
        if self.is_too_old(comment):
            return ShouldTrack(False, 'comment is too old')
        return ShouldTrack(True, '')

    def should_track_for_author(self, comment):
        """Get whether comment should be tracked, based on its author."""
        # First check against the less-strict should_track() rules.
        should_track = self.should_track(comment)
        if not should_track.track:
            return should_track
        # Check if the author isn't known to steemvote.
        author = self.config.get_author(comment.author)
        if not author:
            return ShouldTrack(False, 'author is unknown')
        # Check if we omit replies by the author.
        if comment.is_reply() and not author.vote_replies:
            return ShouldTrack(False, 'comment is a reply')
        return ShouldTrack(True, '')

    def should_track_for_delegate(self, comment):
        """Get whether comment should be tracked, based on delegate votes."""
        # First check against the less-strict should_track() rules.
        should_track = self.should_track(comment)
        if not should_track.track:
            return should_track
        if not self._get_voted_delegates(comment):
            return ShouldTrack(False, 'no delegates have voted for comment')
        return ShouldTrack(True, '')

    def _should_vote_author(self, comment):
        """Get whether comment should be voted on, based on its author.

        Returns:
            A 2-tuple of (should_vote, reason).
        """
        # Check if the priority is high enough given our voting power.
        author = self.config.get_author(comment.author)
        if not author or not self.is_prioritized(author.priority):
            return (False, 'author does not have a high enough priority')
        return (True, '')

    def _should_vote_delegates(self, comment):
        """Get whether comment should be voted on, based on delegate votes.

        Returns:
            A 2-tuple of (should_vote, reason).
        """
        delegates = self._get_voted_delegates(comment)
        if not delegates:
            return (False, 'no delegates have voted for comment')
        if not any(self.is_prioritized(priority) for priority in [i.priority for i in delegates]):
            return (False, 'no delegates with a high enough priority')

        return (True, '')

    def should_vote(self, comment):
        """Get whether comment should be voted on.

        Calls _should_vote_author() and should_vote_delegate().
        The result is False if both are False.

        Returns:
            A ShouldVote instance.
        """
        # First check against the less-strict should_track() rules.
        should_track = self.should_track(comment)
        if not should_track.track:
            return ShouldVote(False, *should_track)
        # Then check against rules that depend on context.
        # Check if the comment is too young.
        if self.is_too_young(comment):
            return ShouldVote(False, True, 'comment is too young')
        # Check if the comment should be voted on based on its author
        # or any delegates that have voted for it.
        should_vote_author = self._should_vote_author(comment)
        should_vote_delegates = self._should_vote_delegates(comment)
        if not should_vote_author[0] and not should_vote_delegates[0]:
            return ShouldVote(False, True, ' and '.join([should_vote_author[1], should_vote_delegates[1]]))
        return ShouldVote(True, True, '')


class Voter(Curator):
    """Voter settings and functionality.

    This class is used by first calling connect_to_steem(),
    then calling vote_for_comments() whenever the database
    should be checked for eligible comments.
    """
    def __init__(self, config):
        super(Voter, self).__init__(config)
        # Ensure that authentication settings were supplied.
        config.require('voter_account_name')
        config.require('vote_key')

        self.steem = None
        # Interval for updating stats.
        self.update_interval = 20
        # Last time that stats were updated via RPC.
        self.last_update = 0

        self.voting_lock = threading.Lock()
        self.db = DB(config)

    def load_settings(self):
        """Load settings from config."""
        super(Voter, self).load_settings()
        self.name = self.config.get('voter_account_name')
        self.wif = self.config.get('vote_key')

        self.rpc_node = self.config.get('rpc_node')
        self.rpc_user = self.config.get('rpc_user')
        self.rpc_pass = self.config.get('rpc_pass')

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

    def get_voting_weight(self, comment):
        """Get the weight that comment should be voted for with."""
        author = self.config.get_author(comment.author)
        if author:
            return author.weight
        delegates = self._get_voted_delegates(comment)
        if delegates:
            return max([i.weight for i in delegates])

        raise Exception('Comment should not be voted for')

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
            comments = self.db.get_tracked_comments(with_metadata=False)
            for comment in comments:
                # Skip if the comment shouldn't be voted on now.
                should_vote = self.should_vote(comment)
                if not should_vote.vote:
                    # Check whether to stop tracking the comment.
                    if not should_vote.track:
                        old_identifiers.append(comment.identifier)
                        self.logger.debug('Stop tracking %s because %s' % (comment.identifier, should_vote.reason))
                # Vote for the comment.
                else:
                    weight = self.get_voting_weight(comment)
                    self._vote(comment.identifier, weight)
                    voted_comments.append(comment)

            self.db.update_voted_comments(voted_comments)
            self.db.remove_tracked_comments(old_identifiers)
