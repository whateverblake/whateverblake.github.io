"""Rebuild the figures that come from the author's original draw.io diagrams.

For every entry in spec.FIGS: crop the region from the original diagram in
`source code reading/`, translate the Chinese labels with zh_en.T, fit the
English text into the original boxes, write `_migration/drawio/<topic>/<name>.drawio`
and export `<topic>/assets/<name>.svg` with the draw.io desktop CLI.

The two hand-built figures (client-startup-04 and java-zero-copy-01) are kept
as checked-in .drawio files and are only re-exported.
"""
import copy, json, re, subprocess, sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dio, fit
from spec import FIGS
from zh_en import T

REPO = Path(__file__).resolve().parents[2]
SRC = '/Users/blake/Downloads/jianshu_blog/source code reading/'
DRAWIO = '/Applications/draw.io.app/Contents/MacOS/draw.io'
OUT = REPO / '_migration/drawio'
TITLES = json.loads((REPO / '_migration/original-figures.json').read_text())


def merge_packet(model, x0, y0, k):
    """Copy the cells of client-startup-04.drawio into model at (x0, y0), scaled by k."""
    root = model.find('root')
    layer = next(c.get('id') for c in root if c.get('parent') == '0')
    packet = dio.load_pages(str(OUT / 'zookeeper/client-startup-04.drawio'))[0][1]
    for el, cell in dio.all_objects(packet):
        if el.get('id') in ('0', '1'):
            continue
        el = copy.deepcopy(el)
        el.set('id', 'packet-' + el.get('id'))
        el.set('parent', layer)
        g = el.find('mxGeometry')
        for key, off in (('x', x0), ('y', y0), ('width', 0), ('height', 0)):
            g.set(key, str(float(g.get(key, 0)) * k + off))
        el.set('style', re.sub(r'fontSize=([\d.]+)', lambda m: f'fontSize={float(m.group(1)) * k:.1f}', el.get('style')))
        root.append(el)


def build():
    for name, (f, box, *clip) in FIGS.items():
        m = dio.load_pages(SRC + f)[0][1]
        c = dio.crop(m, box, clip=clip[0] if clip else ())
        if name.endswith('node-creation-01'):
            # replace the Chinese-annotated Packet screenshot with the English Packet cells (vector text)
            for el, cell in dio.all_objects(c):
                if 'image=data:' in (cell.get('style') or ''):
                    g = cell.find('mxGeometry')
                    merge_packet(c, float(g.get('x')), float(g.get('y')), 0.75)
                    c.find('root').remove(el)
        before = {el.get('id'): dio.label(el) for el, _ in dio.all_objects(c)}
        dio.translate(c, T)
        fit.fit(c, [el.get('id') for el, _ in dio.all_objects(c) if dio.label(el) != before[el.get('id')]])
        if name.endswith('pooled-memory-05'):
            for el, cell in dio.all_objects(c):
                if 'smaller than' in dio.label(el):
                    cell.set('style', (cell.get('style') or '').rstrip(';') + ';labelBackgroundColor=#ffffff;')
        if name.endswith('data-recovery-03'):
            # this half of the snapshot diagram lost the container title; give it one
            title = next(copy.deepcopy(el) for el, _ in dio.all_objects(m) if 'snap文件格式' in dio.label(el))
            title.set('id', 'dr03-title'); title.set('value', '<b>Snapshot file format: DataTree</b>')
            g = title.find('mxGeometry'); g.set('x', '560'); g.set('y', '1096'); g.set('width', '330'); g.set('height', '22')
            c.find('root').append(title)
        dio.save(c, str(OUT / (name + '.drawio')))


def export():
    for topic in ('zookeeper', 'netty'):
        for f in sorted((OUT / topic).glob('*.drawio')):
            svg = REPO / topic / 'assets' / (f.stem + '.svg')
            subprocess.run([DRAWIO, '-x', '-f', 'svg', '--embed-svg-fonts', 'false', '--theme', 'light',
                            '-s', '1.5', '-b', '10', '-o', str(svg), str(f)], check=True, capture_output=True)
            s = svg.read_text().replace('background: transparent; background-color: transparent;',
                                        'background: #ffffff; background-color: #ffffff;')
            info = TITLES[f'{topic}/assets/{f.stem}.svg']
            meta = f'<title>{escape(info["title"])}</title><desc>{escape(info["note"])}</desc>'
            s = re.sub(r'(<svg\b[^>]*>)', lambda m: m.group(1) + meta, s, count=1)
            svg.write_text(s)


if __name__ == '__main__':
    build()
    export()
    print('Rebuilt', len(FIGS), 'cropped figures and exported', sum(1 for _ in OUT.glob('*/*.drawio')), 'SVGs.')
