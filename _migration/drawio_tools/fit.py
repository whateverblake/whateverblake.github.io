import re, math, dio

def _style(st):
    d = {}
    for p in (st or '').split(';'):
        if '=' in p:
            k, v = p.split('=', 1); d[k] = v
        elif p:
            d[p] = None
    return d

def _setstyle(cell, key, val):
    st = cell.get('style') or ''
    if re.search(r'(^|;)' + key + '=', st):
        st = re.sub(r'(^|;)' + key + '=[^;]*', lambda m: m.group(1) + f'{key}={val}', st)
    else:
        st = st.rstrip(';') + f';{key}={val};'
    cell.set('style', st)

def _sizes(label):
    s = [float(x) for x in re.findall(r'font-size:\s*([\d.]+)px', label)]
    s += [float(x) * 4 / 3 for x in re.findall(r'font-size:\s*([\d.]+)pt', label)]
    return s

def _scale_inline(label, k):
    label = re.sub(r'font-size:\s*([\d.]+)px', lambda m: f'font-size: {float(m.group(1))*k:.1f}px', label)
    return re.sub(r'font-size:\s*([\d.]+)pt', lambda m: f'font-size: {float(m.group(1))*k:.1f}pt', label)

def fit(model, ids):
    objs = {el.get('id'): (el, c) for el, c in dio.all_objects(model)}
    edges = {i for i, (el, c) in objs.items() if c is not None and c.get('edge') == '1'}
    for i in ids:
        el, c = objs[i]
        if c.get('vertex') != '1' or c.get('parent') in edges:
            continue
        g = c.find('mxGeometry')
        if g is None:
            continue
        st = _style(c.get('style'))
        lab = dio.label(el)
        fs = float(st.get('fontSize') or 12)
        inl = _sizes(lab)
        eff = max(inl + [fs]) if inl else fs
        mono = bool(re.search(r'menlo|courier|monospace|consolas', lab + (c.get('style') or ''), re.I))
        cw = 0.61 if mono else 0.56
        paras = [p for p in dio.plain(lab).split('\n')]
        w, h = float(g.get('width', 0)), float(g.get('height', 0))
        need_w = max(len(p) for p in paras) * eff * cw + 8
        is_text = 'text' in st and st.get('strokeColor') in (None, 'none')
        if is_text:
            if len(paras) <= 2 and need_w > w:
                dx = need_w - w
                al = st.get('align', 'center')
                x = float(g.get('x', 0))
                if al == 'center':
                    g.set('x', str(x - dx / 2))
                elif al == 'right':
                    g.set('x', str(x - dx))
                g.set('width', str(need_w)); w = need_w
            lines = sum(max(1, math.ceil(len(p) * eff * cw / max(w - 6, 10))) for p in paras)
            need_h = lines * eff * 1.25
            if need_h > h:
                g.set('y', str(float(g.get('y', 0)) - (need_h - h) / 2)); g.set('height', str(need_h))
            continue
        if w <= 0 or h <= 0:
            continue
        k = 1.0
        while k > 0.62:
            f = eff * k
            lines = sum(max(1, math.ceil(len(p) * f * cw / max(w - 6, 10))) for p in paras)
            if lines * f * 1.22 <= h - 2:
                break
            k -= 0.05
        if k < 0.999:
            if inl:
                lab = _scale_inline(lab, k)
                if el.tag == 'mxCell':
                    el.set('value', lab)
                else:
                    el.set('label', lab)
            _setstyle(c, 'fontSize', f'{fs*k:.1f}')
