# ?? Edit 2: Add GPSError class + GPS failure tracking ?????????
with open("src/utils/failures.py", "r") as f:
    content = f.read()

old = 'class DisplayError(SafespaceError):\n    """Exception raised for GUI-related failures."""\n    pass'
new = 'class DisplayError(SafespaceError):\n    """Exception raised for GUI-related failures."""\n    pass\n\nclass GPSError(SafespaceError):\n    """Exception raised for GPS-related failures."""\n    pass'

if old in content:
    content = content.replace(old, new)
    print("Edit 2 OK � GPSError class added")
else:
    print("Edit 2 FAILED")

with open("src/utils/failures.py", "w") as f:
    f.write(content)

# ?? Edit 3: Use GPSError in gps_handler.py ????????????????????
with open("src/handlers/gps_handler.py", "r") as f:
    content = f.read()

old = 'from utils.logger import Logger'
new = 'from utils.logger import Logger\nfrom utils.failures import GPSError, FailureManager'

if old in content:
    content = content.replace(old, new)
    print("Edit 3a OK � import added to gps_handler")
else:
    print("Edit 3a FAILED")

old = '        self._consecutive_failures: int = 0\n        self._max_failures: int = 10'
new = '        self._consecutive_failures: int = 0\n        self._max_failures: int = 10\n        self._failure_manager = FailureManager()'

if old in content:
    content = content.replace(old, new)
    print("Edit 3b OK � FailureManager added to gps_handler")
else:
    print("Edit 3b FAILED")

old = '        if self._consecutive_failures >= self._max_failures:\n                self.logger.error("GPS module appears unresponsive � check wiring")\n            return'
new = '        if self._consecutive_failures >= self._max_failures:\n                self.logger.error("GPS module appears unresponsive � check wiring")\n                self._failure_manager.record_failure(\n                    GPSError("GPS module unresponsive � check wiring", critical=True)\n                )\n            return'

if old in content:
    content = content.replace(old, new)
    print("Edit 3c OK � GPS failure recorded in FailureManager")
else:
    print("Edit 3c FAILED")

with open("src/handlers/gps_handler.py", "w") as f:
    f.write(content)

# ?? Edit 4: GPS fix indicator in display main_window.py ???????
with open("src/handlers/display/main_window.py", "r") as f:
    content = f.read()

# Add gps_handler import at top
old = 'from typing import Optional, Callable, List'
new = 'from typing import Optional, Callable, List, Any'

if old in content:
    content = content.replace(old, new)
    print("Edit 4a OK � typing import updated")
else:
    print("Edit 4a FAILED")

with open("src/handlers/display/main_window.py", "w") as f:
    f.write(content)

print("All edits done.")
