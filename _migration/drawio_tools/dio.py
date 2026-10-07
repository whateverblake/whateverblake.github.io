"""Helpers for reading draw.io files, cropping regions and translating labels."""
import base64, zlib, re, html, copy
import xml.etree.ElementTree as ET
from urllib.parse import unquote

CJK = re.compile(r'[　-〿一-鿿＀-￯]')


def load_pages(path):
    """Return list of (page_name, mxGraphModel Element)."""
    text = open(path, encoding='utf-8').read()
    root = ET.fromstring(text)
    pages = []
    if root.tag == 'mxGraphModel':
        return [('page', root)]
    for d in root.findall('diagram'):
        model = d.find('mxGraphModel')
        if model is None:
            raw = (d.text or '').strip()
            data = zlib.decompress(base64.b64decode(raw), -15)
            model = ET.fromstring(unquote(data.decode('utf-8')))
        pages.append((d.get('name'), model))
    return pages


def cells(model):
    return model.find('root').findall('mxCell') + [
        c for o in model.find('root') if o.tag != 'mxCell' for c in o.findall('mxCell')]


def all_objects(model):
    """Yield (element, cell) — element is the <object>/<UserObject> wrapper or the mxCell itself."""
    out = []
    for o in model.find('root'):
        if o.tag == 'mxCell':
            out.append((o, o))
        else:
            c = o.find('mxCell')
            out.append((o, c))
    return out


def geom(cell):
    g = cell.find('mxGeometry')
    if g is None:
        return None
    f = lambda k, d=0: float(g.get(k, d))
    return f('x'), f('y'), f('width'), f('height')


def label(el):
    v = el.get('value') if el.tag == 'mxCell' else el.get('label')
    return v or ''


def plain(v):
    v = re.sub(r'<br\s*/?>|</div>|</p>', '\n', v or '')
    v = re.sub(r'<[^>]+>', '', v)
    return html.unescape(v).replace('\xa0', ' ').strip()


def absolute(model):
    """Map id -> absolute (x, y, w, h) for vertices; edges get bbox of their points."""
    objs = all_objects(model)
    byid = {el.get('id'): (el, c) for el, c in objs}
    cache = {}

    def origin(pid):
        if pid not in byid or pid in ('0', '1'):
            return (0.0, 0.0)
        el, c = byid[pid]
        if c.get('edge') == '1':
            return (0.0, 0.0)
        if pid in cache:
            return cache[pid][:2]
        g = geom(c) or (0, 0, 0, 0)
        ox, oy = origin(c.get('parent'))
        cache[pid] = (ox + g[0], oy + g[1], g[2], g[3])
        return cache[pid][:2]

    res = {}
    for el, c in objs:
        i = el.get('id')
        if c is None or i in ('0', '1'):
            continue
        if c.get('vertex') == '1':
            origin(i)
            res[i] = cache[i]
    for el, c in objs:
        i = el.get('id')
        if c is None or c.get('edge') != '1':
            continue
        g = c.find('mxGeometry')
        pts = []
        if g is not None:
            for p in g.iter('mxPoint'):
                if p.get('x') is not None or p.get('y') is not None:
                    pts.append((float(p.get('x', 0)), float(p.get('y', 0))))
        ox, oy = origin(c.get('parent'))
        for s in (c.get('source'), c.get('target')):
            if s in res:
                x, y, w, h = res[s]
                pts.append((x + w / 2 - ox, y + h / 2 - oy))
        if pts:
            xs = [p[0] + ox for p in pts]
            ys = [p[1] + oy for p in pts]
            res[i] = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return res


def dump(model, minlen=0):
    ab = absolute(model)
    rows = []
    for el, c in all_objects(model):
        i = el.get('id')
        if i not in ab:
            continue
        x, y, w, h = ab[i]
        kind = 'E' if c.get('edge') == '1' else 'V'
        st = c.get('style', '')
        if 'image=' in st or st.startswith('shape=image'):
            kind += '[img]'
        rows.append((y, x, kind, i, w, h, plain(label(el))[:90].replace('\n', ' | ')))
    rows.sort()
    for y, x, kind, i, w, h, t in rows:
        print(f'{kind:7} {x:8.0f} {y:8.0f} {w:6.0f}x{h:<5.0f} {t}')


def inside(b, box, tol=2):
    x, y, w, h = b
    X0, Y0, X1, Y1 = box
    return x >= X0 - tol and y >= Y0 - tol and x + w <= X1 + tol and y + h <= Y1 + tol


def crop(model, box, drop=()):
    """New mxGraphModel containing only the cells fully inside box (abs coords)."""
    ab = absolute(model)
    objs = all_objects(model)
    byid = {el.get('id'): (el, c) for el, c in objs}
    keep = set()
    for el, c in objs:
        i = el.get('id')
        if i in ab and inside(ab[i], box) and i not in drop:
            keep.add(i)
    # edges: keep if both connected ends kept (or unconnected end inside box)
    for el, c in objs:
        i = el.get('id')
        if c is None or c.get('edge') != '1' or i in drop:
            continue
        ends = [c.get('source'), c.get('target')]
        ok = all((e is None) or (e in keep) for e in ends)
        if ok and i in ab and inside(ab[i], box, tol=40):
            keep.add(i)
        elif i in keep and not ok:
            keep.discard(i)
    # edge labels (children of edges) follow their edge
    edges = {el.get('id') for el, c in objs if c is not None and c.get('edge') == '1'}
    for el, c in objs:
        i = el.get('id')
        if c is not None and c.get('parent') in edges:
            if c.get('parent') in keep:
                keep.add(i)
            else:
                keep.discard(i)
    # make sure parents kept (containers) — if parent not kept, reparent to layer
    new = copy.deepcopy(model)
    root = new.find('root')
    for o in list(root):
        oid = o.get('id')
        c = o if o.tag == 'mxCell' else o.find('mxCell')
        if oid in ('0',) or (c is not None and c.get('parent') == '0' and oid not in ab):
            continue  # layers
        if oid not in keep:
            root.remove(o)
            continue
        pid = c.get('parent')
        if pid in edges:
            continue
        if pid not in keep and pid in ab:
            # reparent to the top layer with absolute geometry
            lay = pid
            while lay in byid and byid[lay][1].get('parent') not in (None, '0'):
                lay = byid[lay][1].get('parent')
            c.set('parent', lay)
            if c.get('vertex') == '1':
                g = c.find('mxGeometry')
                x, y, w, h = ab[oid]
                g.set('x', str(x)); g.set('y', str(y))
    return new


def translate(model, mapping, strict=True):
    """Replace Chinese substrings in labels and tooltips; mapping applied longest-first."""
    keys = sorted(mapping, key=len, reverse=True)
    missing = []
    for el, c in all_objects(model):
        for attr in ('value', 'label', 'tooltip'):
            v = el.get(attr)
            if not v or not CJK.search(html.unescape(v)):
                continue
            s = html.unescape(v) if attr != 'value' else v
            for k in keys:
                s = s.replace(k, mapping[k])
                ek = html.escape(k, quote=False)
                if ek != k:
                    s = s.replace(ek, mapping[k])
            if CJK.search(html.unescape(s)):
                missing.append(plain(s))
            el.set(attr, s)
    if strict and missing:
        raise SystemExit('untranslated: ' + repr(missing))
    return missing


def chinese_labels(model):
    out = []
    for el, c in all_objects(model):
        v = label(el)
        if CJK.search(html.unescape(v)):
            out.append(plain(v))
    return out


def save(model, path, name='Page-1'):
    mx = ET.Element('mxfile', host='Electron', type='device')
    d = ET.SubElement(mx, 'diagram', id='p1', name=name)
    d.append(model)
    ET.ElementTree(mx).write(path, encoding='utf-8', xml_declaration=False)
