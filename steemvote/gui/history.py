from PyQt4.QtGui import *
from PyQt4.QtCore import *

from steemvote.gui.util import format_vote_type

class CurationHistoryModel(QAbstractTableModel):
    """Model of curation history items."""
    REWARD_TIME = 0
    IDENTIFIER = 1
    REASON = 2
    VOTE_WEIGHT = 3
    REWARD = 4
    TOTAL_FIELDS = 5

    # Role for sorting.
    SortRole = Qt.UserRole + 1
    def __init__(self, parent=None):
        super(CurationHistoryModel, self).__init__(parent)
        self.items = []
        self.headers = [
            {
                Qt.DisplayRole: 'Reward Time',
                Qt.ToolTipRole: 'When the curation reward occurred',
            },
            {
                Qt.DisplayRole: 'Identifier',
                Qt.ToolTipRole: 'Post Identifier',
            },
            {
                Qt.DisplayRole: 'Reason',
                Qt.ToolTipRole: 'Why the post was voted for',
            },
            {
                Qt.DisplayRole: 'Vote Type',
                Qt.ToolTipRole: 'The type of vote that was cast',
            },
            {
                Qt.DisplayRole: 'Reward',
                Qt.ToolTipRole: 'Curation reward for the post',
            },
        ]

    def set_items(self, items):
        """Set the items for this model."""
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def columnCount(self, parent=QModelIndex()):
        return self.TOTAL_FIELDS

    def rowCount(self, parent=QModelIndex()):
        return len(self.items)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        try:
            return self.headers[section][role]
        except (IndexError, KeyError):
            return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.items):
            return None
        if role not in [Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole, Qt.TextAlignmentRole, self.SortRole]:
            return None

        c = index.column()
        item = self.items[index.row()]
        data = alignment = None

        if c == self.REWARD_TIME:
            data = item.reward_time
            if role == Qt.DisplayRole:
                data = item.reward_time.strftime('%Y-%m-%d %H:%M UTC')
            elif role == self.SortRole:
                data = data.timestamp()
        elif c == self.IDENTIFIER:
            data = item.identifier
        elif c == self.REASON:
            data = '/'.join([item.reason_type, item.reason_value])
        elif c == self.VOTE_WEIGHT:
            data = item.vote_weight
            if role == Qt.DisplayRole:
                data = format_vote_type(item.vote_weight, verbose=False)
        elif c == self.REWARD:
            data = str(item.reward)
            if role == Qt.DisplayRole:
                data = data + ' VESTS'
            elif role == self.SortRole:
                data = float(item.reward)
            elif role == Qt.TextAlignmentRole:
                alignment = Qt.AlignRight | Qt.AlignVCenter

        if role == Qt.TextAlignmentRole:
            return alignment
        return data

class CurationHistoryWidget(QWidget):
    """Displays curation history."""
    def __init__(self, db, parent=None):
        super(CurationHistoryWidget, self).__init__(parent)
        self.db = db
        self.model = CurationHistoryModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setSortRole(self.model.SortRole)
        self.proxy_model.setDynamicSortFilter(True)

        self.view = QTableView()
        self.view.setModel(self.proxy_model)
        self.view.verticalHeader().setVisible(False)
        for header in [self.view.horizontalHeader(), self.view.verticalHeader()]:
            header.setHighlightSections(False)
        self.view.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.view.horizontalHeader().setResizeMode(self.model.IDENTIFIER, QHeaderView.Stretch)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.view.setSortingEnabled(True)
        self.view.sortByColumn(self.model.REWARD_TIME, Qt.DescendingOrder)

        # Layout.
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addWidget(self.view)
        self.setLayout(vbox)

    def update_history(self):
        """Update displayed history from the database."""
        self.model.set_items(self.db.get_curation_history())
