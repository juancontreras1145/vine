import json, re, sys, unicodedata
from pathlib import Path
from pypdf import PdfReader

PDF = Path(sys.argv[1] if len(sys.argv) > 1 else 'vine.pdf')
OUT = Path('vine_index.json')

def norm(s):
    s = unicodedata.normalize('NFD', s.upper())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^A-Z0-9 ]+', '', s).strip()

def clean(text):
    text = text.replace('\u00ad','').replace('\r','')
    text = re.sub(r'(?m)^\s*\d+\s*$', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

print(f'Leyendo {PDF}...')
reader = PdfReader(str(PDF))
pages=[]
for i,p in enumerate(reader.pages,1):
    pages.append(p.extract_text() or '')
    if i % 50 == 0: print(f'  {i}/{len(reader.pages)} páginas')
text=clean('\n'.join(pages))
Path('vine_raw.txt').write_text(text, encoding='utf-8')
lines=text.splitlines()

# Vine usa entradas visualmente destacadas. La extracción suele conservarlas como líneas
# cortas en mayúsculas. Excluimos encabezados editoriales frecuentes.
black={'DICCIONARIO','VINE','ANTIGUO TESTAMENTO','NUEVO TESTAMENTO','PREFACIO','INTRODUCCION','INDICE','CONTENIDO'}
heads=[]
for i,line in enumerate(lines):
    s=line.strip(' .,:;–—-\t')
    if not s or len(s)>55: continue
    letters=''.join(c for c in s if c.isalpha())
    if len(letters)<2: continue
    upper=sum(c.isupper() for c in letters)/len(letters)
    n=norm(s)
    if upper >= .90 and n not in black and re.fullmatch(r"[A-ZÁÉÍÓÚÜÑ0-9 ,;()'/-]+", s):
        # Evita frases enteras: las cabeceras suelen ser términos o pequeñas listas de sinónimos.
        if len(s.split()) <= 7:
            heads.append((i,s))

entries={}
for pos,(i,title) in enumerate(heads):
    j=heads[pos+1][0] if pos+1<len(heads) else len(lines)
    body='\n'.join(lines[i:j]).strip()
    if len(body)<30: continue
    key=norm(title)
    # Si el mismo encabezado aparece varias veces, conserva todas las secciones.
    if key in entries: entries[key]['text'] += '\n\n' + body
    else: entries[key]={'title':title,'text':body}

OUT.write_text(json.dumps(entries,ensure_ascii=False),encoding='utf-8')
print(f'Índice creado: {len(entries)} encabezados -> {OUT}')
print('Prueba: python search_vine.py FE')
