"""Command-protocol bridge used by native ShinkaEvolve Headless."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from swarm_location.subscription import cli
from swarm_location.diagnostics import redact
if __name__ == '__main__':
    try:
        cli()
    except Exception as exc:
        print(redact(str(exc)), file=sys.stderr)
        raise SystemExit(1)
