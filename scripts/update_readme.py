"""Update the measured-results table only; never manufacture result rows."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
readme = root / 'README.md'
start, end = '<!-- RESULTS-TABLE:START -->', '<!-- RESULTS-TABLE:END -->'
text = readme.read_text()
if text.count(start) != 1 or text.count(end) != 1:
    raise ValueError('README must contain exactly one results-table marker pair')
a, tail = text.split(start, 1)
_, b = tail.split(end, 1)
table = (root / 'results/step1/table.md').read_text().strip()
readme.write_text(a + start + '\n\n' + table + '\n\n' + end + b)
print('Updated README from results/step1/table.md; review interpretation and limitations separately.')
