
from PyQt4.QtGui import *
from PyQt4.QtCore import *

def format_vote_type(weight):
    """Format weight as a string for displaying vote type."""
    if weight == 0:
        return 'No vote'
    vote_type = 'Upvote'
    if weight < 0:
        vote_type = 'Downvote'
        weight = abs(weight)
    return '{} (weight: {}%)'.format(vote_type, int(weight))

def floated_buttons(btns, left=False):
    """Returns a HBoxLayout with buttons floated to the right or left."""
    hbox = QHBoxLayout()
    for b in btns:
        hbox.addWidget(b)
    if left:
        hbox.addStretch(1)
    else:
        hbox.insertStretch(0, 1)
    return hbox

class Separator(QFrame):
    """A raised horizontal line to separate widgets."""
    def __init__(self, parent=None):
        super(Separator, self).__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(6)
        self.setMidLineWidth(2)

    def sizeHint(self):
        return QSize(6, 8)

class WeightWidget(QWidget):
    """Displays and edits the weight of votes."""
    def __init__(self, parent=None):
        super(WeightWidget, self).__init__(parent)
        self.upvote_button = QRadioButton('Upvote')
        self.downvote_button = QRadioButton('Downvote')
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.valueChanged.connect(self.on_slider_value_changed)
        self.label = QLabel('')
        self.label.setFixedWidth(50)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.VLine)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(self.upvote_button)
        hbox.addWidget(self.downvote_button)
        hbox.addWidget(sep)
        hbox.addWidget(QLabel('Weight:'))
        hbox.addWidget(self.slider)
        hbox.addWidget(self.label)

        self.setLayout(hbox)

    def on_slider_value_changed(self, new_value):
        self.label.setText('({}%)'.format(new_value))

    @pyqtProperty(float)
    def weight(self):
        value = self.slider.value()
        if self.downvote_button.isChecked():
            value *= -1
        return float(value)

    @weight.setter
    def weight(self, value):
        self.upvote_button.setChecked(True)
        if value < 0:
            self.downvote_button.setChecked(True)
            value *= -1
        self.slider.setValue(int(value))
