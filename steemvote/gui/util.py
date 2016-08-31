
from PyQt4.QtGui import *
from PyQt4.QtCore import *

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

