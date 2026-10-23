"""Read a plugin report without exposing local paths or geometry."""
import json
import sys
from collections import Counter
from pathlib import Path


def summarize(path):
    report = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    tiles = report.get('tiles', [])
    return {
        'state': report.get('state'),
        'planned': report.get('planned_tiles'),
        'processed': len(tiles),
        'counts': dict(Counter(t['status'] for t in tiles)),
        'nodata_cells': sum(t.get('nodata_cells', 0) for t in tiles),
        'transfer_MB': round(report.get('transfer_bytes', 0) / 1e6, 2),
        'output_MB': round(sum(t.get('output_bytes', 0) for t in tiles) / 1e6, 2),
        'recovered_errors': sum(len(t.get('errors', [])) for t in tiles),
        'catalog_errors': len(report.get('catalog_errors', [])),
        'resolutions': report.get('resolutions_m'),
        'height_systems': sorted({t['height'] for t in tiles if t.get('height')}),
    }


if __name__ == '__main__':
    print(json.dumps(summarize(sys.argv[1]), ensure_ascii=False, indent=2))
