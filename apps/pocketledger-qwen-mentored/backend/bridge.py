import json
from pathlib import Path
import runpy
import sys

transform = runpy.run_path(str(Path(__file__).with_name('logic.py')))['transform']
request = json.loads(sys.stdin.read())
print(json.dumps(transform(request)))
