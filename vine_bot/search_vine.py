import json,sys,re,unicodedata
from rapidfuzz import process,fuzz

def norm(s):
 s=unicodedata.normalize('NFD',s.upper()); s=''.join(c for c in s if unicodedata.category(c)!='Mn'); return re.sub(r'[^A-Z0-9 ]+','',s).strip()
data=json.load(open('vine_index.json',encoding='utf8'))
q=norm(' '.join(sys.argv[1:]))
if q in data: print(data[q]['text'])
else:
 for k,score,_ in process.extract(q,data.keys(),scorer=fuzz.WRatio,limit=10): print(score,data[k]['title'])
