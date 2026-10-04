import os,json,re,unicodedata,logging
from pathlib import Path
from rapidfuzz import process,fuzz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application,CommandHandler,MessageHandler,CallbackQueryHandler,ContextTypes,filters

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

def norm(s):
 s=unicodedata.normalize('NFD',s.upper()); s=''.join(c for c in s if unicodedata.category(c)!='Mn'); return re.sub(r'[^A-Z0-9 ]+',' ',s).strip()

def title_terms(title):
 # Encabezados Vine pueden contener varias entradas: "CONTAMINAR, CONTAMINACIÓN".
 return [norm(x) for x in re.split(r'[,;/]',title) if norm(x)]

def chunks(text,limit=3500):
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
if not INDEX.exists(): raise SystemExit('Falta vine_index.json. Ejecuta: python prepare_vine.py ../../vine.pdf')
DATA=json.loads(INDEX.read_text(encoding='utf8'))
KEYS=list(DATA)
TERM_MAP={}
for k,e in DATA.items():
 for term in title_terms(e['title']): TERM_MAP.setdefault(term,[]).append(k)

async def send_entry(message,key):
 entry=DATA[key]; parts=chunks(entry['text'])
 for i,part in enumerate(parts,1):
  head=f'📖 {entry["title"]}' + (f' — {i}/{len(parts)}' if len(parts)>1 else '')
  await message.reply_text(head+'\n\n'+part)

def candidates(q):
 # 1) encabezado exacto; 2) término exacto dentro de encabezados compuestos.
 if q in DATA: return [q]
 if q in TERM_MAP: return list(dict.fromkeys(TERM_MAP[q]))
 # Coincidencia como palabra completa en encabezado normalizado.
 found=[k for k in KEYS if re.search(r'(^| )'+re.escape(q)+r'( |$)',k)]
 return list(dict.fromkeys(found))

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text('📖 Diccionario Bíblico Vine\n\nEnvíame una palabra, por ejemplo: FE, GRACIA, BAUTISMO, CONTAMINAR o JUSTIFICACIÓN. También reconozco términos incluidos en encabezados compuestos.')

async def lookup(update:Update,context:ContextTypes.DEFAULT_TYPE):
 raw=(update.message.text or '').strip(); q=norm(raw)
 if not q:return
 if len(q)>60:
  await update.message.reply_text('Envíame solamente la palabra o término que deseas buscar.'); return
 found=candidates(q)
 if len(found)==1:
  await send_entry(update.message,found[0]); return
 if len(found)>1:
  keyboard=[[InlineKeyboardButton(DATA[k]['title'][:55],callback_data=f'v|{k}') ] for k in found[:8]]
  await update.message.reply_text(f'🔎 Encontré varias entradas relacionadas con «{raw}». Elige una:',reply_markup=InlineKeyboardMarkup(keyboard)); return
 # Sugerencias sobre términos individuales + encabezados, para no privilegiar títulos compuestos raros.
 choices=list(TERM_MAP)
 matches=process.extract(q,choices,scorer=fuzz.WRatio,limit=5,score_cutoff=65)
 if matches:
  keyboard=[]; seen=set()
  for term,_,_ in matches:
   for k in TERM_MAP[term]:
    if k not in seen:
     seen.add(k); keyboard.append([InlineKeyboardButton(DATA[k]['title'][:55],callback_data=f'v|{k}')]); break
  await update.message.reply_text(f'🔎 No encontré una entrada exacta para «{raw}».\n\n¿Quisiste decir?',reply_markup=InlineKeyboardMarkup(keyboard[:5]))
 else: await update.message.reply_text(f'🔎 No encontré «{raw}» en el índice del diccionario.')

async def choose(update:Update,context:ContextTypes.DEFAULT_TYPE):
 query=update.callback_query; await query.answer()
 key=query.data[2:]
 if key not in DATA:
  await query.edit_message_text('Esa entrada ya no está disponible. Vuelve a escribir la palabra.'); return
 await query.edit_message_reply_markup(reply_markup=None)
 await send_entry(query.message,key)

async def error(update,context): logging.exception('Error del bot',exc_info=context.error)

def main():
 token=os.getenv('TELEGRAM_BOT_TOKEN')
 if not token: raise SystemExit('Falta TELEGRAM_BOT_TOKEN. Ejecuta: set -a; source .env; set +a')
 app=Application.builder().token(token).build()
 app.add_handler(CommandHandler('start',start)); app.add_handler(CommandHandler('ayuda',start))
 app.add_handler(CallbackQueryHandler(choose,pattern=r'^v\\|'))
 app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,lookup)); app.add_error_handler(error)
 print(f'Bot iniciado. Entradas cargadas: {len(DATA)}'); app.run_polling(drop_pending_updates=True)
if __name__=='__main__': main()
