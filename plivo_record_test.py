# Just write a quick fix to recording.py
import re
with open("recording.py", "r") as f:
    code = f.read()
code = code.replace("if resp.status == 202:", "if resp.status in (200, 202):")
with open("recording.py", "w") as f:
    f.write(code)
