import threading

from steemapi.steemnoderpc import SteemNodeRPC
from piston.steem import Steem


class SteemvoteRPC(SteemNodeRPC):
    """Temporary work-around for RPC threading problems."""
    def __init__(self, *args, **kwargs):
        super(SteemvoteRPC, self).__init__(*args, **kwargs)
        self.rpc_lock = threading.Lock()

    def get_account(self, name):
        with self.rpc_lock:
            result = super(SteemvoteRPC, self).get_account(name)
        return result

    def get_account_history(self, *args, **kwargs):
        with self.rpc_lock:
            result = super(SteemvoteRPC, self).__getattr__('get_account_history')(*args, **kwargs)
        return result

    def get_block(self, num):
        with self.rpc_lock:
            result = super(SteemvoteRPC, self).__getattr__('get_block')(num)
        return result

    def get_content(self, author, permlink):
        with self.rpc_lock:
            result = super(SteemvoteRPC, self).__getattr__('get_content')(author, permlink)
        return result

    def get_dynamic_global_properties(self):
        with self.rpc_lock:
            result = super(SteemvoteRPC, self).__getattr__('get_dynamic_global_properties')()
        return result

class SteemvoteSteem(Steem):
    """Subclass of Steem with a work-around for RPC threading problems."""
    def _connect(self, *args, **kwargs):
        super(SteemvoteSteem, self)._connect(*args, **kwargs)
        self.rpc = SteemvoteRPC(self.rpc.url, user=self.rpc.user,
                password=self.rpc.password, num_retries=self.rpc.num_retries)

