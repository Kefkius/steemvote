from PyQt4.QtGui import *
from PyQt4.QtCore import *

from steemvote.models import Delegate, Priority
from steemvote.gui.util import floated_buttons, Separator

def yes_or_no(value):
    return 'Yes' if value else 'No'

class DelegatesModel(QAbstractTableModel):
    NAME = 0
    PRIORITY = 1
    UPVOTE = 2
    TOTAL_FIELDS = 3

    # Role for sorting
    SortRole = Qt.UserRole + 1
    def __init__(self, config, parent=None):
        super(DelegatesModel, self).__init__(parent)
        self.config = config
        self.delegates = list(config.delegates)

        self.headers = [
            {
                Qt.DisplayRole: 'Name',
                Qt.ToolTipRole: 'Delegate name',
            },
            {
                Qt.DisplayRole: 'Priority',
                Qt.ToolTipRole: 'The importance of voting after this delegate',
            },
            {
                Qt.DisplayRole: 'Vote Type',
                Qt.ToolTipRole: 'The type of vote to cast (upvote or downvote)',
            },
        ]

    def delegate_for_row(self, row):
        """Get the delegate at row."""
        return self.delegates[row]

    def create_delegate(self):
        """Create a new delegate."""
        # Find an unused name.
        offset = 1
        name = 'default' + str(offset)
        while any(i.name == name for i in self.delegates):
            offset += 1
            name = 'default' + str(offset)

        self.beginResetModel()
        self.delegates.append(Delegate(name))
        self.save()
        self.endResetModel()

        return name

    def remove_delegate(self, name):
        """Remove a delegate."""
        delegate = None
        for i in self.delegates:
            if i.name == name:
                delegate = i
                break

        if not delegate:
            return
        self.beginResetModel()
        self.delegates.remove(delegate)
        self.save()
        self.endResetModel()

    def save(self):
        """Update config and save."""
        self.config.set_delegates(self.delegates)

    def columnCount(self, parent=QModelIndex()):
        return self.TOTAL_FIELDS

    def rowCount(self, parent=QModelIndex()):
        return len(self.delegates)

    def headerData(self, section, orientation, role = Qt.DisplayRole):
        if orientation != Qt.Horizontal: return None
        try:
            return self.headers[section][role]
        except (IndexError, KeyError):
            return None

    def data(self, index, role = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.delegates):
            return None
        if role not in [Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole, Qt.UserRole, self.SortRole]:
            return None

        col = index.column()
        delegate = self.delegates[index.row()]

        data = None
        if col == self.NAME:
            data = delegate.name
        elif col == self.PRIORITY:
            data = delegate.priority.value
            if role in [Qt.EditRole, self.SortRole]:
                data = Priority.get_index(delegate.priority)
        elif col == self.UPVOTE:
            data = True if delegate.weight == 100.0 else False
            if role == Qt.DisplayRole:
                data = 'Upvote' if data else 'Downvote'

        return data

    def setData(self, index, value, role = Qt.EditRole):
        if not index.isValid() or index.row() >= len(self.delegates):
            return None

        col = index.column()
        delegate = self.delegates[index.row()]

        if col == self.NAME:
            delegate.name = value
        elif col == self.PRIORITY:
            delegate.priority = Priority.from_index(value)
        elif col == self.UPVOTE:
            val = 100.0 if value else -100.0
            delegate.weight = val
        else:
            return False

        self.dataChanged.emit(index, index)
        return True

class DelegateEditor(QWidget):
    """Editor for delegates."""
    def __init__(self, parent):
        super(DelegateEditor, self).__init__(parent)

        self.mapper = QDataWidgetMapper()
        self.mapper.setModel(parent.proxy_model)
        self.mapper.setSubmitPolicy(QDataWidgetMapper.ManualSubmit)

        self.name_edit = QLineEdit()
        self.priority_combo = QComboBox()
        self.priority_combo.setModel(QStringListModel([i.value for i in Priority]))
        self.upvote_box = QCheckBox()

        model = parent.model
        self.mapper.addMapping(self.name_edit, model.NAME)
        self.mapper.addMapping(self.priority_combo, model.PRIORITY, 'currentIndex')
        self.mapper.addMapping(self.upvote_box, model.UPVOTE)

        form = QFormLayout()
        form.addRow('Name:', self.name_edit)
        form.addRow('Priority:', self.priority_combo)
        form.addRow('Upvote?', self.upvote_box)

        self.setLayout(form)

class DelegatesWidget(QWidget):
    """Displays and allows editing of delegates."""
    def __init__(self, config, parent=None):
        super(DelegatesWidget, self).__init__(parent)
        self.config = config

        # Delegates model and view.

        self.model = DelegatesModel(self.config)
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setSortRole(self.model.SortRole)
        self.proxy_model.setDynamicSortFilter(True)
        self.view = QTableView()

        self.view.setModel(self.proxy_model)
        self.view.verticalHeader().setVisible(False)
        for header in [self.view.horizontalHeader(), self.view.verticalHeader()]:
            header.setHighlightSections(False)
        self.view.horizontalHeader().setResizeMode(self.model.NAME, QHeaderView.Stretch)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.view.setSortingEnabled(True)
        self.view.sortByColumn(self.model.NAME, Qt.AscendingOrder)
        self.view.selectionModel().selectionChanged.connect(self.on_selection_changed)

        # Editor and editor buttons.
        self.editor = DelegateEditor(self)
        self.new_delegate_button = QPushButton('New')
        self.new_delegate_button.clicked.connect(self.create_new_delegate)
        self.save_delegate_button = QPushButton('Save')
        self.save_delegate_button.clicked.connect(self.save_selected_delegate)
        self.delete_delegate_button = QPushButton('Delete')
        self.delete_delegate_button.clicked.connect(self.delete_selected_delegate)

        # Layout.
        vbox = QVBoxLayout()
        vbox.addWidget(self.view)
        vbox.addSpacing(1)
        vbox.addWidget(Separator())
        vbox.addWidget(self.editor)
        vbox.addLayout(floated_buttons([self.new_delegate_button, self.save_delegate_button, self.delete_delegate_button]))
        self.setLayout(vbox)

        self.view.selectRow(0)

    def on_selection_changed(self, selected, deselected):
        """Update the mapper's current index."""
        row = 0
        try:
            row = selected.indexes()[0].row()
        except Exception:
            pass
        self.editor.mapper.setCurrentIndex(row)

    def save_selected_delegate(self):
        """Save the selected delegate."""
        self.editor.mapper.submit()
        self.model.save()

    def create_new_delegate(self):
        """Create a new delegate."""
        name = self.model.create_delegate()
        self.select_delegate(name)

    def delete_selected_delegate(self):
        """Delete the selected delegate."""
        delegate = self.get_selected_delegate()
        if QMessageBox.question(self, 'Delete Delegate', 'Do you want to delete the following delegate: %s?' % delegate.name,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:

            self.model.remove_delegate(delegate.name)
            self.view.selectRow(0)

    def get_selected_delegate(self):
        """Get the selected delegate."""
        return self.get_delegate_for_row(self.editor.mapper.currentIndex())

    def select_delegate(self, name):
        """Select the delegate with the given name."""
        self.view.clearSelection()
        for i in range(self.proxy_model.rowCount()):
            idx = self.proxy_model.index(i, 0)
            delegate_name = self.proxy_model.data(idx)
            if delegate_name == name:
                self.view.selectRow(i)
                break

    def get_delegate_for_row(self, row):
        """Get the delegate for a proxy model row."""
        idx = self.proxy_model.mapToSource(self.proxy_model.index(row, 0))
        return self.model.delegate_for_row(idx.row())
