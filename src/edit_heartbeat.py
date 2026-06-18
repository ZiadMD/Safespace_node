with open("src/managers/network.py", "r") as f:
    content = f.read()

old = '                    "health": self._get_health_metrics(),\n                    "firmwareVersion": self._firmware_version,'
new = '                    "health": self._get_health_metrics(),\n                    "location": self._gps.get_location() if self._gps else {"lat": float(self._lat), "long": float(self._long), "fix": False},\n                    "firmwareVersion": self._firmware_version,'

if old in content:
    content = content.replace(old, new)
    print("Heartbeat GPS OK")
else:
    print("FAILED")

with open("src/managers/network.py", "w") as f:
    f.write(content)
