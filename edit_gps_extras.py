# ?? Edit 1: GPS location in heartbeat ????????????????????????????
with open("src/managers/network.py", "r") as f:
    content = f.read()

old = '                    "health": self._get_health_metrics(),\n                    "firmwareVersion": self._firmware_version,'
new = '                    "health": self._get_health_metrics(),\n                    "location": self._gps.get_location() if self._gps else {"lat": float(self._lat), "long": float(self._long), "fix": False},\n                    "firmwareVersion": self._firmware_version,'

if old in content:
    content = content.replace(old, new)
    print("Edit 1 OK � GPS added to heartbeat")
else:
    print("Edit 1 FAILED")

with open("src/managers/network.py", "w") as f:
    f.write(content)

# ?? Edit 2: GPS failure tracking in failures.py ???????????????
with open("src/utils/failures.py", "r") as f:
    content = f.read()

print("failures.py content preview:")
print(content[:300])
print("---")

# We'll do this edit after seeing the file structure
print("Edit 2 � will handle after seeing failures.py structure")

# ?? Edit 3: GPS status on display ?????????????????????????????
with open("src/handlers/display/main_window.py", "r") as f:
    content = f.read()

print("main_window.py content preview:")
print(content[:300])
print("---")
print("Edit 3 � will handle after seeing main_window.py structure")
