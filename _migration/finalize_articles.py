"""Apply consistent reading presentation without changing source excerpts."""
from pathlib import Path
import json,re,yaml
REPO=Path(__file__).resolve().parents[1]
manifest=json.loads((REPO/'_migration/article-manifest.json').read_text())
figures={r['asset']:r['title'] for r in json.loads((REPO/'_migration/figure-provenance.json').read_text())}
descriptions={
 'thread-model':'Trace event-loop selection, worker startup, and shared I/O and task scheduling.',
 'server-startup':'Follow channel construction, registration, pipeline initialization, port binding, and connection acceptance.',
 'pipeline':'Follow inbound and outbound event propagation through handler contexts and channel initializers.',
 'socket-read':'Trace selector readiness, receive buffers, the read loop, and adaptive buffer sizing.',
 'socket-write':'Follow queued outbound buffers, gathering writes, flush promises, and socket backpressure.',
 'message-framing':'Understand TCP stream boundaries and length-field decoding across fragmented and coalesced reads.',
 'pooled-memory':'Read the legacy arena, chunk, page, and subpage allocator, and compare the redesigned October 2020 implementation.',
 'recycler':'Explore per-thread object stacks, cross-thread return queues, scavenging, and reuse limits.',
 'java-reference-processing':'Follow OpenJDK 8 reference reachability, the Reference Handler thread, cleaners, and reference queues.',
 'java-zero-copy':'Compare Java socket copying, FileChannel.transferTo, and memory-mapped file access.',
}
for a in manifest['articles']:
 p=Path(a['target_path']);s=p.read_text()
 if a['slug'] in descriptions and a['topic']=='netty':
  s=re.sub(r'^description:.*$', 'description: '+json.dumps(descriptions[a['slug']]),s,count=1,flags=re.M)
 # Promote the original main sections to H2 while preserving relative depth.
 body_start=s.index('\n---\n',4)+5
 pre=s[:body_start];body=s[body_start:]
 boundary=body.find('## Source version and reconstructed figures')
 first=body if boundary<0 else body[:boundary];tail='' if boundary<0 else body[boundary:]
 in_code=False;levels=[]
 for line in first.splitlines():
  if re.match(r'^\s*```',line):in_code=not in_code
  elif not in_code:
   h=re.match(r'^(#{2,6})\s+',line)
   if h:levels.append(len(h.group(1)))
 shift=max(0,min(levels)-2) if levels else 0
 if shift:
  in_code=False;lines=[]
  for line in first.splitlines(keepends=True):
   if re.match(r'^\s*```',line):in_code=not in_code
   elif not in_code:
    h=re.match(r'^(#{2,6})(\s+)',line)
    if h:line='#'*(len(h.group(1))-shift)+line[len(h.group(1)):]
   lines.append(line)
  first=''.join(lines)
 s=pre+first+tail
 # Descriptive alt text and full-size image links, using the actual SVG title.
 def image(m):
  alt,url=m.group(1),m.group(2)
  title=figures[a['topic']+'/'+url]
  return f'[![{title}]({url})]({url})'
 s=re.sub(r'(?<!\[)!\[([^\]]*)\]\((assets/[^\s)]+\.svg)\)',image,s)
 # Math remains visible without depending on an unloaded MathJax runtime.
 def math(m):
  text=' '.join(m.group(1).split()).replace('2^{maxOrder-d}','2^(maxOrder - d)').replace('8K *','8 KiB *')
  text=re.sub(r'2\^\{(\d+)\}',r'2^\1',text)
  return '`'+text+'`'
 s=re.sub(r'\$\$(.*?)\$\$',math,s,flags=re.S)
 s=re.sub(r'\$2\^\{(\d+)\}\$',lambda m:'`2^'+m.group(1)+'`',s)
 # The original export carries large empty tails; remove excess blank lines outside code.
 in_code=False;lines=[];empty=0
 for line in s.splitlines():
  if re.match(r'^\s*```',line):in_code=not in_code
  empty=empty+1 if not line.strip() else 0
  if in_code or empty<=2:lines.append(line)
 normalized=[]
 for line in lines:
  if re.match(r'^\s*```',line):
   if normalized and normalized[-1].strip():normalized.append('')
   normalized.append(line.strip());normalized.append('')
  else:normalized.append(line)
 p.write_text('\n'.join(line.rstrip() for line in normalized).rstrip()+'\n')
# Keep the original overview prose and reading links, with an easy-to-scan series index.
p=REPO/'netty/index.md';s=p.read_text();front=s[:s.index('\n---\n',4)+5]
rows=[a for a in manifest['articles'] if a['topic']=='netty' and a['slug']!='index']
body='\n# Reading Netty Source Code\n\nI recently finished this Netty source-code walkthrough and hope it provides a useful starting point for discussion. These articles follow networking, memory allocation, object reuse, and related Java internals through the source.\n\n## Read the series\n\n| Article | Topic |\n| --- | --- |\n'
for a in rows:body+=f'| [{a["series_order"]}. {a["title"]}]({a["slug"]}.html) | {descriptions[a["slug"]]} |\n'
body+='\n## Source versions and figures\n\nThe networking and Recycler articles use **Netty 4.1.53.Final**, released October 13, 2020. The pooled-memory article preserves the original **Netty 4.1.50.Final legacy allocator** and explains how 4.1.53 differs. The Java reference-processing and zero-copy articles use **OpenJDK 8u272-b10** for their Java implementation references. These are historical source walkthroughs.\n\nAll illustrations are local English SVG files. Click a diagram to open it at full size. Missing original debugger screenshots have been replaced with source excerpts or explanatory diagrams; they are labeled as reconstructions.\n\n- [Netty 4.1.53.Final source tree](https://github.com/netty/netty/tree/d4a0050ef33cab2542a80e11489a4977a63859f8)\n- [Netty 4.1.50.Final legacy allocator source](https://github.com/netty/netty/tree/8c5b72aaf02e7f349a9972dd9179b449b5a6067b)\n- [OpenJDK 8u272-b10 source tree](https://github.com/openjdk/jdk8u/tree/c3b5603e949d6272d777ef57952833672a97b4e3)\n'
p.write_text(front+body)
print('Formatted 23 articles: heading hierarchy, English alt text, full-size figures, visible formulas, and Netty reading index.')
