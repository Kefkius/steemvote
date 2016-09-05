from PyQt4.QtGui import *
from PyQt4.QtCore import *

from steemvote.models import Author, Priority
from steemvote.gui.util import floated_buttons, Separator

def yes_or_no(value):
    return 'Yes' if value else 'No'

class AuthorsModel(QAbstractTableModel):
    NAME = 0
    PRIORITY = 1
    VOTE_REPLIES = 2
    UPVOTE = 3
    TOTAL_FIELDS = 4

    # Role for sorting
    SortRole = Qt.UserRole + 1
    def __init__(self, config, parent=None):
        super(AuthorsModel, self).__init__(parent)
        self.config = config
        self.authors = list(config.authors)

        self.headers = [
            {
                Qt.DisplayRole: 'Name',
                Qt.ToolTipRole: 'Author name',
            },
            {
                Qt.DisplayRole: 'Priority',
                Qt.ToolTipRole: 'The importance of voting for this author',
            },
            {
                Qt.DisplayRole: 'Vote Replies?',
                Qt.ToolTipRole: 'Whether to vote for replies by this author',
            },
            {
                Qt.DisplayRole: 'Vote Type',
                Qt.ToolTipRole: 'The type of vote to cast (upvote or downvote)',
            },
        ]

    def author_for_row(self, row):
        """Get the author at row."""
        return self.authors[row]

    def create_author(self):
        """Create a new author."""
        # Find an unused name.
        offset = 1
        name = 'default' + str(offset)
        while any(i.name == name for i in self.authors):
            offset += 1
            name = 'default' + str(offset)

        self.beginResetModel()
        self.authors.append(Author(name))
        self.save()
        self.endResetModel()

        return name

    def remove_author(self, name):
        """Remove an author."""
        author = None
        for i in self.authors:
            if i.name == name:
                author = i
                break

        if not author:
            return
        self.beginResetModel()
        self.authors.remove(author)
        self.save()
        self.endResetModel()

    def save(self):
        """Update config and save."""
        self.config.set_authors(self.authors)

    def columnCount(self, parent=QModelIndex()):
        return self.TOTAL_FIELDS

    def rowCount(self, parent=QModelIndex()):
        return len(self.authors)

    def headerData(self, section, orientation, role = Qt.DisplayRole):
        if orientation != Qt.Horizontal: return None
        try:
            return self.headers[section][role]
        except (IndexError, KeyError):
            return None

    def data(self, index, role = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.authors):
            return None
        if role not in [Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole, Qt.UserRole, Qt.CheckStateRole, self.SortRole]:
            return None

        col = index.column()
        author = self.authors[index.row()]

        if role == Qt.CheckStateRole and col != self.VOTE_REPLIES:
            return None

        data = None
        if col == self.NAME:
            data = author.name
        elif col == self.PRIORITY:
            data = author.priority.value
            if role in [Qt.EditRole, self.SortRole]:
                data = Priority.get_index(author.priority)
        elif col == self.VOTE_REPLIES:
            data = author.vote_replies
            if role == Qt.CheckStateRole:
                data = Qt.Checked if author.vote_replies else Qt.Unchecked
            elif role == Qt.DisplayRole:
                data = yes_or_no(author.vote_replies)
        elif col == self.UPVOTE:
            data = True if author.weight == 100.0 else False
            if role == Qt.DisplayRole:
                data = 'Upvote' if data else 'Downvote'

        return data

    def setData(self, index, value, role = Qt.EditRole):
        if not index.isValid() or index.row() >= len(self.authors):
            return None

        col = index.column()
        author = self.authors[index.row()]

        if col == self.NAME:
            author.name = value
        elif col == self.PRIORITY:
            author.priority = Priority.from_index(value)
        elif col == self.VOTE_REPLIES:
            author.vote_replies = value
        elif col == self.UPVOTE:
            val = 100.0 if value else -100.0
            author.weight = val
        else:
            return False

        self.dataChanged.emit(index, index)
        return True

class AuthorEditor(QWidget):
    """Editor for authors."""
    def __init__(self, parent):
        super(AuthorEditor, self).__init__(parent)

        self.mapper = QDataWidgetMapper()
        self.mapper.setModel(parent.proxy_model)
        self.mapper.setSubmitPolicy(QDataWidgetMapper.ManualSubmit)

        self.name_edit = QLineEdit()
        self.priority_combo = QComboBox()
        self.priority_combo.setModel(QStringListModel([i.value for i in Priority]))
        self.vote_replies_box = QCheckBox()
        self.upvote_box = QCheckBox()

        model = parent.model
        self.mapper.addMapping(self.name_edit, model.NAME)
        self.mapper.addMapping(self.priority_combo, model.PRIORITY, 'currentIndex')
        self.mapper.addMapping(self.vote_replies_box, model.VOTE_REPLIES)
        self.mapper.addMapping(self.upvote_box, model.UPVOTE)

        form = QFormLayout()
        form.addRow('Name:', self.name_edit)
        form.addRow('Priority:', self.priority_combo)
        form.addRow('Vote for replies?', self.vote_replies_box)
        form.addRow('Upvote?', self.upvote_box)

        self.setLayout(form)

class AuthorsWidget(QWidget):
    """Displays and allows editing of authors."""
    def __init__(self, config, parent=None):
        super(AuthorsWidget, self).__init__(parent)
        self.config = config

        # Authors model and view.

        self.model = AuthorsModel(self.config)
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
        self.editor = AuthorEditor(self)
        self.new_author_button = QPushButton('New')
        self.new_author_button.clicked.connect(self.create_new_author)
        self.save_author_button = QPushButton('Save')
        self.save_author_button.clicked.connect(self.save_selected_author)
        self.delete_author_button = QPushButton('Delete')
        self.delete_author_button.clicked.connect(self.delete_selected_author)

        # Layout.
        vbox = QVBoxLayout()
        vbox.addWidget(self.view)
        vbox.addSpacing(1)
        vbox.addWidget(Separator())
        vbox.addWidget(self.editor)
        vbox.addLayout(floated_buttons([self.new_author_button, self.save_author_button, self.delete_author_button]))
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

    def save_selected_author(self):
        """Save the selected author."""
        self.editor.mapper.submit()
        self.model.save()

    def create_new_author(self):
        """Create a new author."""
        name = self.model.create_author()
        self.select_author(name)

    def delete_selected_author(self):
        """Delete the selected author."""
        author = self.get_selected_author()
        if QMessageBox.question(self, 'Delete Author', 'Do you want to delete the following author: %s?' % author.name,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:

            self.model.remove_author(author.name)
            self.view.selectRow(0)

    def get_selected_author(self):
        """Get the selected author."""
        return self.get_author_for_row(self.editor.mapper.currentIndex())

    def select_author(self, name):
        """Select the author with the given name."""
        self.view.clearSelection()
        for i in range(self.proxy_model.rowCount()):
            idx = self.proxy_model.index(i, 0)
            author_name = self.proxy_model.data(idx)
            if author_name == name:
                self.view.selectRow(i)
                break

    def get_author_for_row(self, row):
        """Get the author for a proxy model row."""
        idx = self.proxy_model.mapToSource(self.proxy_model.index(row, 0))
        return self.model.author_for_row(idx.row())
