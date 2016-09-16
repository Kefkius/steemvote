import logging
import sys
import threading
import time
import traceback

from piston.steem import Steem

from steemvote.models import Comment, AccountHistory
from steemvote.voter import Voter


class Monitor(threading.Thread):
    """Monitors Steem operations.

    Handler methods for operations are named "on_<operation>".

    Thread logic is based on DaemonThread from https://github.com/spesmilo/electrum/blob/master/lib/util.py.
    """
    def __init__(self, voter):
        super(Monitor, self).__init__()
        self.running = False
        self.running_lock = threading.Lock()
        self.voter = voter
        self.config = voter.config
        self.logger = logging.getLogger(__name__)
        # There must be authors to monitor.
        self.config.require('authors')

        # Set up operation handlers.
        self.op_handlers = {}
        for attr in dir(self):
            if attr.startswith('on_'):
                self.op_handlers[attr[3:]] = getattr(self, attr)

    @property
    def db(self):
        return self.voter.db

    @property
    def steem(self):
        return self.voter.steem

    def start(self):
        with self.running_lock:
            self.running = True
        return super(Monitor, self).start()

    def is_running(self):
        with self.running_lock:
            return self.running

    def stop(self):
        with self.running_lock:
            self.running = False

    def run(self):
        self.logger.debug('Starting monitor')
        iterator = self.stream()
        while self.is_running():
            try:
                op_name, op = next(iterator)
                # Call the handler with the operation.
                self.op_handlers[op_name](op)
            except Exception as e:
                self.logger.error(str(e))
                self.logger.error(''.join(traceback.format_tb(sys.exc_info()[2])))
                break
        self.logger.debug('Monitor thread stopped')

    def stream(self):
        """Stream operations that have handlers."""
        for block in self.steem.rpc.block_stream():
            for tx in block['transactions']:
                for op in tx['operations']:
                    if self.has_handler(op[0]):
                        yield op

    def has_handler(self, op_name):
        """Get whether there is a handler for op_name operations."""
        return hasattr(self, 'on_%s' % op_name)

    def on_comment(self, d):
        """Handler for comment operations."""
        try:
            comment = Comment(self.steem, d)
            if self.voter.should_track_for_author(comment).track:
                self.db.add_comment_with_author(comment)
        except ValueError as e:
            self.logger.debug('Invalid comment. Skipping')

    def on_vote(self, d):
        if not self.config.get_delegate(d['voter']):
            return
        try:
            comment = Comment(self.steem, d)
            if self.voter.should_track_for_delegate(comment).track:
                self.db.add_comment_with_delegate(comment, self.config.get_delegate(d['voter']).name)
        except ValueError as e:
            self.logger.debug('Invalid comment. Skipping')


class AccountHistoryMonitor(Monitor):
    def __init__(self, voter):
        super(AccountHistoryMonitor, self).__init__(voter)
        self.update_interval = self.config.get_seconds('account_history_interval', 60 * 60)
        self.last_update = 0

    def run(self):
        self.logger.debug('Starting account history monitor')
        while self.is_running():
            now = time.time()
            if now - self.last_update > self.update_interval:
                self.retrieve_account_history()
                self.last_update = now
            time.sleep(1)
        self.logger.debug('Account history monitor thread stopped')

    def retrieve_account_history(self):
        limit = 500
        highest_stored_sequence = self.db.get_highest_history_sequence_number()
        if highest_stored_sequence == 0:
            limit = 5000
        first = highest_stored_sequence + limit
        history = [i for i in self.steem.rpc.account_history(self.voter.name, first=first, limit=limit, only_ops=['curation_reward', 'curate_reward', 'vote'])]

        if not self.is_running():
            return
        history = AccountHistory(history)
        self.db.update_account_history(history)
