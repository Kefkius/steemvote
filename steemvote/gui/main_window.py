import logging
import signal
import sys
import time
import traceback

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from steemvote.monitor import Monitor
from steemvote.voter import Voter
from steemvote.gui.author import AuthorsWidget
from steemvote.gui.delegate import DelegatesWidget
from steemvote.gui.comment import CommentsWidget
from steemvote.gui.settings import SettingsWidget

DEFAULT_VOTE_INTERVAL = 10 # 10 seconds.

# Based on Timer from https://github.com/spesmilo/electrum/blob/master/gui/qt/util.py.
class Timer(QThread):
    stopped = False
    onTimer = pyqtSignal()

    def run(self):
        while not self.stopped:
            self.onTimer.emit()
            time.sleep(0.5)

    def stop(self):
        self.stopped = True
        self.wait()


class SteemvoteWindow(QMainWindow):
    def __init__(self, config, app):
        super(SteemvoteWindow, self).__init__()
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.app = app
        self.timer = Timer()

        self.voter = Voter(config)
        self.monitor = Monitor(self.voter)

        # Timer-related attributes.

        self.last_vote = 0
        self.vote_interval = config.get_seconds('vote_interval', DEFAULT_VOTE_INTERVAL)
        # Vote interval cannot be less than one second.
        if self.vote_interval < 1:
            raise ConfigError('The minimum value for "vote_interval" is 1 second')
        # The set of tracked comments as of the last timer action.
        self.last_tracked_comments = set()

        self.timer.onTimer.connect(self.timer_actions)


        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_status_tab(), 'Status')
        self.tabs.addTab(self.create_settings_tab(), 'Settings')
        self.tabs.addTab(self.create_authors_tab(), 'Authors')
        self.tabs.addTab(self.create_delegates_tab(), 'Delegates')

        # Status bar widgets.
        self.voting_power_label = QLabel()
        self.statusBar().setVisible(True)
        self.statusBar().addPermanentWidget(self.voting_power_label)

        self.setCentralWidget(self.tabs)
        self.show()

    def main(self):
        self.voter.connect_to_steem()
        self.voter.update()
        self.monitor.start()

        signal.signal(signal.SIGINT, lambda *args: self.app.quit())

        self.timer.start()
        self.app.exec_()

        self.timer.stop()

        self.monitor.stop()
        self.voter.close()

    def create_status_tab(self):
        desc = QLabel('The posts that are currently being tracked are displayed below:')
        desc.setWordWrap(True)
        self.comments_widget = CommentsWidget(self.voter.db)

        vbox = QVBoxLayout()
        vbox.addWidget(desc)
        vbox.addWidget(self.comments_widget)
        w = QWidget()
        w.setLayout(vbox)
        return w

    def create_settings_tab(self):
        self.settings_widget = SettingsWidget(self.config)
        self.settings_widget.settingsChanged.connect(lambda: self.voter.load_settings())
        return self.settings_widget

    def create_authors_tab(self):
        self.authors_widget = AuthorsWidget(self.config)
        return self.authors_widget

    def create_delegates_tab(self):
        self.delegates_widget = DelegatesWidget(self.config)
        return self.delegates_widget

    def timer_actions(self):
        now = time.time()
        try:
            # voter will update via RPC once every interval.
            self.voter.update()

            if now - self.last_vote > self.vote_interval:
                self.last_vote = now
                self.voter.vote_for_comments()
        except Exception as e:
            self.logger.error(str(e))
            self.logger.error(''.join(traceback.format_tb(sys.exc_info()[2])))

        # Update tracked comments.
        tracked_comments = set(self.voter.db.tracked_comments.values())
        if self.last_tracked_comments != tracked_comments:
            self.comments_widget.update_comments()
            self.last_tracked_comments = tracked_comments

        self.voting_power_label.setText('Voting power: %s' % self.voter.get_voting_power())


    def sizeHint(self):
        return QSize(900, 480)
