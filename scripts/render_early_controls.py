"""Plot frozen M6 incumbent curves; no new solver execution or resampling."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from swarm_location.suite import file_sha256
from evaluate_anytime import write_json


def render(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output=Path(output);data=json.loads((output/'study/curves.json').read_text())
    figures=output/'figures';figures.mkdir(exist_ok=True)
    plots=[]
    for network in ('SiouxFalls','Anaheim'):
        fig=plt.figure(figsize=(10,5.5));ax=fig.add_subplot(111)
        for r in data:
            if r['scope']!=network or r['method'].endswith('_duplicate'):continue
            xy=r['points_seconds_coverage_pct'];x,y=zip(*xy)
            ax.step(x,y,where='post',label=r['method'],linewidth=1.6,
                    linestyle='--' if r['method'].startswith('early_') else '-')
        ax.set_xscale('symlog',linthresh=.02)
        ax.set_xticks([0,.02,.1,.5,2],labels=['0','0.02','0.1','0.5','2'])
        ax.set_xlim(0,2);ax.set_ylim(0,100)
        ax.set_xlabel('Seconds since external GO (nonlinear time axis)')
        ax.set_ylabel('Mean incumbent coverage (%)')
        ax.set_title(f'{network}: early-incumbent controls, six complete paired blocks')
        ax.legend(loc='lower right',ncol=2,fontsize=8)
        ax.grid(alpha=.2);fig.tight_layout()
        path=figures/(network+'.png');fig.savefig(path,dpi=160);plt.close(fig)
        plots.append({'path':path.name,'sha256':file_sha256(path)})
    write_json(figures/'renderer.json',{'source_curves_sha256':file_sha256(output/'study/curves.json'),
        'script_sha256':file_sha256(Path(__file__)),'matplotlib_version':matplotlib.__version__,'plots':plots,
        'scope':'Exact descriptive mean step functions; no smoothing, resampling or confidence bands'})
    text=(ROOT/'README.md').read_text()
    block='\n\nThe figures show all eight fixed-control mean incumbent curves. Dashed lines are early variants; overlapping lines are retained. These are descriptive six-block means, not confidence bands.\n\n'
    for p in plots:block+=f"![{p['path'][:-4]} paired early-control coverage](results/early-controls/figures/{p['path']})\n\n"
    marker='<!-- M6-EARLY-FIGURES:START -->';end='<!-- M6-EARLY-FIGURES:END -->'
    if marker in text:text=text.split(marker)[0]+marker+block+end+text.split(end)[1]
    else:text=text.replace('## 6. Reproduce the first milestone',marker+block+end+'\n\n## 6. Reproduce the first milestone',1)
    (ROOT/'README.md').write_text(text)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',default='results/early-controls')
    render(p.parse_args().output)
