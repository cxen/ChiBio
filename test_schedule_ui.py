#!/usr/bin/env python3
"""The schedule editor's channel list must match what the backend will actually accept.

The dropdown is written out in HTMLScripts.js while the allow-list lives in chibio_schedule.py.
If they drift, the UI offers a channel the server refuses (a save that fails for no visible
reason) or hides one that works. Nothing at runtime would catch it, so catch it here.

    CHIBIO_MOCK_HW=1 python3 test_schedule_ui.py
"""
import os
import re
os.environ['CHIBIO_MOCK_HW'] = '1'

from chibio_schedule import SCHEDULABLE

js = open('static/HTMLScripts.js').read()
block = re.search(r'var SCHED_ITEMS = \[(.*?)\];', js, re.S)
assert block, 'SCHED_ITEMS not found in HTMLScripts.js'
ui_items = re.findall(r"\['([A-Za-z0-9]+)',", block.group(1))

missing = [i for i in SCHEDULABLE if i not in ui_items]
extra = [i for i in ui_items if i not in SCHEDULABLE]
assert not missing, 'schedulable but absent from the UI dropdown: %s' % missing
assert not extra, 'offered by the UI but the server will refuse it: %s' % extra
assert len(ui_items) == len(set(ui_items)), 'duplicate entries in SCHED_ITEMS'

# Every option needs a human label, not the raw key repeated.
labels = re.findall(r"\['[A-Za-z0-9]+', '([^']+)'\]", block.group(1))
assert len(labels) == len(ui_items), 'every SCHED_ITEMS entry needs a label'

html = open('templates/index.html').read()
for el in ('SchedRows', 'SchedStatus', 'SchedAdd', 'SchedSave', 'SchedRun', 'SchedDirty'):
    assert 'id="%s"' % el in html, 'missing element %s' % el

print('PASS: the schedule dropdown offers exactly the %d channels the server accepts, all '
      'labelled, and the panel elements the script drives all exist' % len(SCHEDULABLE))
