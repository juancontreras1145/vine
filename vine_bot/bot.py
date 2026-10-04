import os,json,re,unicodedata,logging
from pathlib import Path
from rapidfuzz import process,fuzz
from telegram import Update
from telegram.ext import Application,CommandHandler,MessageHandler,ContextTypes,filters

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

def norm(s):
 s=unicodedata.normalize('NFD',s.upper()); s=''.join(c for c in s if unicodedata.category(c)!='Mn'); return re.sub(r'[^A-Z0-9 ]+','',s).strip()

def chunks(text,limit=3600):
 text=text.strip(); out=[]
 while len(text)>limit:
  cut=text.rfind('\n\n',0,limit)
  if cut<limit//2: cut=text.rfind('\n',0,limit)
  if cut<limit//2: cut=text.rfind('. ',0,limit)
  if cut<limit//2: cut=text.rfind(' ',0,limit)
  if cut<1: cut=limit
  out.append(text[:cut].strip()); text=text[cut:].strip()
 if text: out.append(text)
 return out

INDEX=Path('vine_index.json')
if not INDEX.exists(): raise SystemExit('Falta vine_index.json. Ejecuta: python prepare_vine.py vine.pdf')
DATA=json.loads(INDEX.read_text(encoding='utf8'))
KEYS=list(DATA)

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text('📖 Diccionario Bíblico Vine\n\nEnvíame una palabra, por ejemplo: FE, GRACIA, BAUTISMO o JUSTIFICACIÓN. Buscaré su entrada en el diccionario.')

async def lookup(update:Update,context:ContextTypes.DEFAULT_TYPE):
 raw=(update.message.text or '').strip()
 if not raw: return
 q=norm(raw)
 if len(q)>60:
  await update.message.reply_text('Envíame solamente la palabra o término que deseas buscar.') ; return
 key=q if q in DATA else None
 if not key:
  # También acepta un término que coincida con una parte de un encabezado compuesto.
  partial=[k for k in KEYS if q and re.search(r'(^| )'+re.escape(q)+r'( |$)',k)]
  if len(partial)==1: key=partial[0]
 if not key:
  matches=process.extract(q,KEYS,scorer=fuzz.WRatio,limit=5,score_cutoff=65)
  if matches:
   names='\n'.join('• '+DATA[k]['title'] for k,_,_ in matches)
   await update.message.reply_text(f'🔎 No encontré una entrada exacta para «{raw}».\n\n¿Quisiste decir?\n{names}')
  else: await update.message.reply_text(f'🔎 No encontré «{raw}» en el índice del diccionario.')
  return
 entry=DATA[key]; parts=chunks(entry['text'])
 for i,part in enumerate(parts,1):
  head=f'📖 {entry["title"]}' + (f' — {i}/{len(parts)}' if len(parts)>1 else '')
  await update.message.reply_text(head+'\n\n'+part)

async def error(update,context): logging.exception('Error del bot',exc_info=context.error)

def main():
 token=os.getenv('TELEGRAM_BOT_TOKEN')
 if not token: raise SystemExit('Falta TELEGRAM_BOT_TOKEN. Ejemplo: export TELEGRAM_BOT_TOKEN="123:ABC"')
 app=Application.builder().token(token).build()
 app.add_handler(CommandHandler('start',start)); app.add_handler(CommandHandler('ayuda',start))
 app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,lookup)); app.add_error_handler(error)
 print(f'Bot iniciado. Entradas cargadas: {len(DATA)}'); app.run_polling(drop_pending_updates=True)
if __name__=='__main__': main()
