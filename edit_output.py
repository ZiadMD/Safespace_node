with open("src/managers/output.py", "r") as f:
    content = f.read()

old = '        # Track current state\n        self._accident_active = False'
new = '        # GPS handler reference (injected after init)\n        self._gps = None\n\n        # Track current state\n        self._accident_active = False'

if old in content:
    content = content.replace(old, new)
    print("Edit 1 OK � _gps attribute added")
else:
    print("Edit 1 FAILED")

with open("src/managers/output.py", "w") as f:
    f.write(content)
