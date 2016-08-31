
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from steemvote.gui.util import floated_buttons

class MinutesWidget(QDoubleSpinBox):
    """Widget for setting a timespan in minutes."""
    def __init__(self, parent=None):
        super(MinutesWidget, self).__init__(parent)
        self.setRange(0.1, 1000.0)
        self.setDecimals(2)
        self.setSuffix(' minutes')

    @pyqtProperty(int)
    def seconds(self):
        result = self.value() * 60.0
        return int(result)

    @seconds.setter
    def seconds(self, value):
        val = value / 60.0
        self.setValue(val)

class SettingsModel(QAbstractTableModel):
    """Model for settings."""
    MIN_POST_AGE = 0
    MAX_POST_AGE = 1
    MIN_VOTING_POWER = 2
    MAX_VOTING_POWER = 3
    TOTAL_FIELDS = 4
    def __init__(self, config, parent=None):
        super(SettingsModel, self).__init__(parent)
        self.config = config

    def save(self):
        self.config.save()

    def columnCount(self, parent=QModelIndex()):
        return self.TOTAL_FIELDS

    def rowCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role = Qt.DisplayRole):
        if not index.isValid():
            return None

        data = None
        c = index.column()
        if c == self.MIN_POST_AGE:
            data = self.config.get_seconds('min_post_age')
        elif c == self.MAX_POST_AGE:
            data = self.config.get_seconds('max_post_age')
        elif c == self.MIN_VOTING_POWER:
            data = self.config.get_decimal('min_voting_power') * 100.0
        elif c == self.MAX_VOTING_POWER:
            data = self.config.get_decimal('max_voting_power') * 100.0

        return data

    def setData(self, index, value, role = Qt.EditRole):
        if not index.isValid():
            return False
        if value is None:
            return False

        c = index.column()
        if c == self.MIN_POST_AGE:
            self.config.set('min_post_age', value)
        elif c == self.MAX_POST_AGE:
            self.config.set('max_post_age', value)
        elif c == self.MIN_VOTING_POWER:
            value = str(round(value, 4)) + '%'
            self.config.set('min_voting_power', value)
        elif c == self.MAX_VOTING_POWER:
            value = str(round(value, 4)) + '%'
            self.config.set('max_voting_power', value)
        else:
            return False

        return True

class SettingsWidget(QWidget):
    settingsChanged = pyqtSignal()
    def __init__(self, config, parent=None):
        super(SettingsWidget, self).__init__(parent)
        self.model = SettingsModel(config)
        self.config = config

        self.min_post_age = MinutesWidget()
        self.max_post_age = MinutesWidget()

        self.min_voting_power = QDoubleSpinBox()
        self.max_voting_power = QDoubleSpinBox()
        for widget in [self.min_voting_power, self.max_voting_power]:
            widget.setRange(1.0, 100.0)
            widget.setDecimals(4)
            widget.setSingleStep(0.1)
            widget.setSuffix('%')

        def check_max_voting_power(new_value):
            min_power = self.min_voting_power.value()
            if new_value < min_power:
                self.max_voting_power.setValue(min_power)
        self.max_voting_power.valueChanged.connect(check_max_voting_power)

        self.mapper = QDataWidgetMapper()
        self.mapper.setModel(self.model)
        self.mapper.addMapping(self.min_post_age, self.model.MIN_POST_AGE, 'seconds')
        self.mapper.addMapping(self.max_post_age, self.model.MAX_POST_AGE, 'seconds')
        self.mapper.addMapping(self.min_voting_power, self.model.MIN_VOTING_POWER)
        self.mapper.addMapping(self.max_voting_power, self.model.MAX_VOTING_POWER)

        self.save_settings_button = QPushButton('Save Settings')
        self.save_settings_button.clicked.connect(self.save_settings)

        form = QFormLayout()
        form.addRow('Minimum post age:', self.min_post_age)
        form.addRow('Maximum post age:', self.max_post_age)
        form.addRow('Minimum voting power:', self.min_voting_power)
        form.addRow('Maximum voting power:', self.max_voting_power)
        form.addRow(floated_buttons([self.save_settings_button]))

        self.setLayout(form)

        self.mapper.setCurrentIndex(0)

    def save_settings(self):
        """Save config settings."""
        if self.config.get_decimal('max_voting_power') < self.config.get_decimal('min_voting_power'):
            return QMessageBox.critical(self, 'Invalid Setting', 'Max voting power must not be less than min voting power')
        self.model.save()
        self.settingsChanged.emit()
