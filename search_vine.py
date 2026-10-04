import json,sys,re,unicodedata
from rapidfuzz import process,fuzz

def norm(s):
 s=unicodedata.normalize('NFD',s.upper()); s=''.join(c for c in s if unicodedata.category(c)!='Mn'); return re.sub(r'[^A-Z0-9 ]+',' ',s).strip()
def terms(title): return [norm(x) for x in re.split(r'[,;/]',title) if norm(x)]
data=json.load(open('vine_index.json',encoding='utf8')); q=norm(' '.join(sys.argv[1:])); tm={}
for k,e in data.items():
 for t in terms(e['title']): tm.setdefault(t,[]).append(k)
keys=[q] if q in data else tm.get(q,[])
if not keys: keys=[k for k in data if re.search(r'(^| )'+re.escape(q)+r'( |$)',k)]
if keys:
 for k in dict.fromkeys(keys): print('\n=== '+data[k]['title']+' ===\n'+data[k]['text'])
else:
 for t,score,_ in process.extract(q,list(tm),scorer=fuzz.WRatio,limit=10): print(score, ' -> ', ', '.join(data[k]['title'] for k in tm[t]))
