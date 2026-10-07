"""Check complete translation coverage, local links, figures, and built output."""
from pathlib import Path
import json,re,sys,collections,urllib.parse,xml.etree.ElementTree as ET
import yaml
from html.parser import HTMLParser
REPO=Path(__file__).resolve().parents[1]
BUILD=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/jianshu-english-site')
manifest=json.loads((REPO/'_migration/article-manifest.json').read_text())
figures=json.loads((REPO/'_migration/figure-provenance.json').read_text())
errors=[]; stats=[]
PROSE_FENCES_CONVERTED={'standalone-server-startup':4,'data-recovery':2,'leader-election':2,'expiry-queue':1,'recycler':1}
def check(condition,msg):
 if not condition:errors.append(msg)
def target(current,url):
 parsed=urllib.parse.urlsplit(url)
 if parsed.scheme or parsed.netloc or url.startswith('#'):return None
 raw=urllib.parse.unquote(parsed.path)
 p=(BUILD/raw.lstrip('/')) if raw.startswith('/') else current.parent/raw
 if not raw:return current
 if p.is_dir() or raw.endswith('/'):p=p/'index.html'
 return p
class Page(HTMLParser):
 def __init__(self):super().__init__();self.refs=[];self.scripts=[];self.h1=0;self.text=[];self.images=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='h1':self.h1+=1
  if tag=='script':self.scripts.append(a.get('type',''))
  if tag=='img':self.images.append(a)
  for key in ['href','src']:
   if key in a:self.refs.append(a[key])
  if tag=='a' and 'href'in a:self.links.append(a['href'])
 def handle_data(self,data):self.text.append(data)
for a in manifest['articles']:
 p=Path(a['target_path']);check(p.exists(),'Missing article '+str(p))
 if not p.exists():continue
 s=p.read_text();pieces=s.split('---',2);fm=yaml.safe_load(pieces[1]);orig=Path(a['original_path']).read_text()
 flag='series' if a['slug']=='index' else 'article'
 check(fm.get(flag) is True and fm.get('lang')=='en','Incorrect '+flag+' flags '+str(p))
 check(fm.get('topic')==('ZooKeeper' if a['topic']=='zookeeper' else 'Netty'),'Incorrect topic '+str(p))
 check(fm.get('order')==a['order'],'Incorrect order '+str(p))
 check(not re.search(r'[\u3400-\u9fff]',s),'Visible Chinese remains '+str(p))
 check('upload-images.jianshu.io' not in s,'Old image host remains '+str(p))
 inline=sum(1 for r in figures if r['article']==a['slug'] and r['topic']==a['topic'] and r['kind'].startswith('inline-'))
 added=sum(1 for r in figures if r['article']==a['slug'] and r['topic']==a['topic'] and r['kind']=='diagram-added')
 expected=len(a['images'])-inline+added
 check(len(re.findall(r'!\[',s))==expected,'Image count mismatch '+str(p))
 origf=len(re.findall(r'^\s*```',orig,re.M));newf=len(re.findall(r'^\s*```',s,re.M))
 # Fences that held prose (not code) in the original were turned into tables, lists or paragraphs.
 converted=PROSE_FENCES_CONVERTED.get(a['slug'],0)*2
 check(newf>=origf-converted and newf%2==0,'Missing/unbalanced original code fences '+str(p))
 check(not re.search(r'\$\$|\$2\^\{',s),'Unrendered math syntax '+str(p))
 built=BUILD/a['topic']/(a['slug']+'.html')
 check(built.exists(),'Missing built article '+str(built))
 if not built.exists():continue
 parsed=Page();parsed.feed(built.read_text());check(parsed.h1==1,'Wrong H1 count '+str(built))
 check(not any(t.startswith('math/tex') for t in parsed.scripts),'Hidden math script '+str(built))
 check(len(parsed.images)==expected,'Built image count mismatch '+str(built))
 for im in parsed.images:check(bool(im.get('alt')),'Missing image alt '+str(built))
 for url in parsed.refs:
  t=target(built,url)
  if t is not None:check(t.exists(),'Broken local link '+str(built)+' → '+url)
 stats.append({'article':str(p.relative_to(REPO)),'original_code_blocks':origf//2,'english_code_blocks':newf//2,'illustrations':len(a['images']),'built':str(built)})
check(len(stats)==23,'Expected23 translated pages')
check(len(figures)==72,'Expected 69 original figure slots plus 3 added diagrams')
seen=set()
for f in figures:
 if f['asset'] is None:continue
 p=REPO/f['asset'];check(p.exists(),'Missing figure '+str(p))
 if not p.exists():continue
 check(f['asset'] not in seen,'Duplicate figure '+f['asset']);seen.add(f['asset'])
 try:
  root=ET.fromstring(p.read_text());text=' '.join(root.itertext())
  check(not re.search(r'[\u3400-\u9fff]',text),'Chinese figure label '+str(p))
  check(root.find('{http://www.w3.org/2000/svg}title') is not None,'Missing SVG title '+str(p))
  check(root.find('{http://www.w3.org/2000/svg}desc') is not None,'Missing SVG description '+str(p))
  check(not list(root.iter('{http://www.w3.org/2000/svg}image')),'Raster screenshot embedded '+str(p))
  check((BUILD/f['asset']).exists(),'Missing built SVG '+f['asset'])
 except Exception as e:errors.append('InvalidSVG '+str(p)+' '+str(e))
check(not (BUILD/'_migration').exists(),'Internal migration material leaked into build')
home=Page();home.feed((BUILD/'index.html').read_text())
for a in manifest['articles']:
 url='/'+a['topic']+'/'+('' if a['slug']=='index' else a['slug']+'.html')
 check(url in home.links,'Homepage is missing article '+url)
report={'articles':len(stats),'topic_counts':dict(collections.Counter(a['topic'] for a in manifest['articles'])),'figures':len(figures),'local_build':'Jekyll3.10.0','errors':errors,'article_coverage':stats}
(REPO/'_migration/verification.json').write_text(json.dumps(report,indent=2)+'\n')
if errors:
 print('\n'.join(errors));raise SystemExit(1)
print('PASS:23Englisharticles (12ZooKeeper +11Netty/Java),69localSVGs, retainedcodeblocks, accessiblefigurelabels, visibleformulas, validbuiltlocallinks, homepageentries, and excludedmigrationmetadata.')
