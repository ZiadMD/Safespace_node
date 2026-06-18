with open("src/handlers/display/main_window.py", "r") as f:
    content = f.read()

# Edit 1 � add gps_status signal
old = '    push_ai_frame_signal = pyqtSignal(object)         # numpy BGR frame (annotated)'
new = '    push_ai_frame_signal = pyqtSignal(object)         # numpy BGR frame (annotated)\n    update_gps_signal = pyqtSignal(bool)              # fix status'

if old in content:
    content = content.replace(old, new)
    print("Edit 1 OK � signal added")
else:
    print("Edit 1 FAILED")

# Edit 2 � connect the signal in __init__
old = '        self.push_input_frame_signal.connect(self._push_input_frame)\n        self.push_ai_frame_signal.connect(self._push_ai_frame)'
new = '        self.push_input_frame_signal.connect(self._push_input_frame)\n        self.push_ai_frame_signal.connect(self._push_ai_frame)\n        self.update_gps_signal.connect(self._update_gps_indicator)'

if old in content:
    content = content.replace(old, new)
    print("Edit 2 OK � signal connected")
else:
    print("Edit 2 FAILED")

# Edit 3 � add gps_label to status bar
old = '    def _add_status_bar(self, root: QVBoxLayout):\n        node_id = self.config.get(\'node.id\', \'?\')\n        desc = self.config.get(\'node.description\', \'\')\n        mode_tag = f"  \u2022  Mode: {self._mode.upper()}"\n        status = QLabel(f"Node {node_id}  \u2022  {desc}{mode_tag}  \u2022  Press SPACE to report manually")\n        status.setAlignment(Qt.AlignmentFlag.AlignCenter)\n        status.setFont(QFont("Segoe UI", 9))\n        status.setStyleSheet("color: #555555; background: transparent;")\n        root.addWidget(status)'
new = '    def _add_status_bar(self, root: QVBoxLayout):\n        node_id = self.config.get(\'node.id\', \'?\')\n        desc = self.config.get(\'node.description\', \'\')\n        mode_tag = f"  \u2022  Mode: {self._mode.upper()}"\n        status = QLabel(f"Node {node_id}  \u2022  {desc}{mode_tag}  \u2022  Press SPACE to report manually")\n        status.setAlignment(Qt.AlignmentFlag.AlignCenter)\n        status.setFont(QFont("Segoe UI", 9))\n        status.setStyleSheet("color: #555555; background: transparent;")\n        root.addWidget(status)\n        # GPS indicator\n        self.gps_label = QLabel("\u25cf  GPS: Searching...")\n        self.gps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)\n        self.gps_label.setFont(QFont("Segoe UI", 9))\n        self.gps_label.setStyleSheet("color: #ff9900; background: transparent;")\n        root.addWidget(self.gps_label)'

if old in content:
    content = content.replace(old, new)
    print("Edit 3 OK � gps_label added to status bar")
else:
    print("Edit 3 FAILED")

# Edit 4 � add public method + slot
old = '    def push_ai_frame(self, frame):\n        self.push_ai_frame_signal.emit(frame)'
new = '    def push_ai_frame(self, frame):\n        self.push_ai_frame_signal.emit(frame)\n\n    def update_gps_status(self, has_fix: bool):\n        """Called from outside Qt thread to update GPS indicator."""\n        self.update_gps_signal.emit(has_fix)'

if old in content:
    content = content.replace(old, new)
    print("Edit 4 OK � public method added")
else:
    print("Edit 4 FAILED")

# Edit 5 � add the slot that actually updates the label
old = '    def _flash_toggle(self):\n        self._flash_visible = not self._flash_visible\n        self.accident_banner.setVisible(self._flash_visible)'
new = '    def _flash_toggle(self):\n        self._flash_visible = not self._flash_visible\n        self.accident_banner.setVisible(self._flash_visible)\n\n    def _update_gps_indicator(self, has_fix: bool):\n        if has_fix:\n            self.gps_label.setText("\u25cf  GPS: Fix Acquired")\n            self.gps_label.setStyleSheet("color: #00ff88; background: transparent;")\n        else:\n            self.gps_label.setText("\u25cf  GPS: Searching...")\n            self.gps_label.setStyleSheet("color: #ff9900; background: transparent;")'

if old in content:
    content = content.replace(old, new)
    print("Edit 5 OK � slot added")
else:
    print("Edit 5 FAILED")

with open("src/handlers/display/main_window.py", "w") as f:
    f.write(content)

print("Display GPS done.")
