import logging
import time

import grapheneapi
from piston.steem import Steem

from steemvote.db import DB
from steemvote.models import Comment

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

    def should_vote(self, comment):
        """Get whether comment should be voted on."""
        author = self.config.get_author(comment.author)
        if not author:
            return False
        if comment.is_reply and not author.vote_replies:
            return False
        # Do not vote if the post is too old.
        if time.time() - comment.timestamp > self.max_post_age:
            return False
        return True

    def monitor(self):
        """Monitor new comments and process them."""
        iterator = self.steem.stream_comments()
        while self.is_running():
            try:
                comment = next(iterator)
                comment = Comment.from_dict(comment)
                if self.should_vote(comment):
                    self.db.add_comment(comment)
            except Exception as e:
                self.logger.error(str(e))
                break
        self.logger.debug('Monitor thread stopped')

    def vote_ready_comments(self):
        """Vote on the comments that are ready."""
        comments = self.db.get_comments_to_vote()
        for comment in comments:
            # Skip if the rules have changed for the author.
            if not self.should_vote(comment):
                self.logger.debug('Skipping %s' % comment.identifier)
                continue
            author = self.config.get_author(comment.author)
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

        self.db.update_voted_comments(comments)
