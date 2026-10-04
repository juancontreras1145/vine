# Bot Telegram — Diccionario Bíblico Vine

## Termux

```bash
pkg update
pkg install python git
pip install -r requirements.txt
```

Descarga el PDF del Diccionario Vine y guárdalo dentro del proyecto con el nombre `vine.pdf`.

Preparar el índice (solo la primera vez):

```bash
python prepare_vine.py vine.pdf
```

Prueba local:

```bash
python search_vine.py FE
python search_vine.py GRACIA
```

Crea tu bot en BotFather y copia el token. **No subas el token a GitHub.** En Termux:

```bash
export TELEGRAM_BOT_TOKEN='TU_TOKEN_AQUI'
python bot.py
```

Mientras ese proceso siga activo, el bot responderá. Para evitar que Android duerma Termux puedes ejecutar `termux-wake-lock` (requiere Termux:API/configuración compatible).

## Qué hace

- Busca la entrada exacta ignorando mayúsculas y tildes.
- Sugiere términos similares si no encuentra una coincidencia.
- Divide automáticamente entradas largas en mensajes de ~3600 caracteres.
- El PDF solo se procesa al crear `vine_index.json`; las consultas posteriores usan el índice local.

## GitHub

`vine.pdf`, `vine_raw.txt`, `vine_index.json` y `.env` están ignorados deliberadamente. Antes de publicar el PDF o texto derivado en un repositorio, comprueba que tengas derecho a redistribuirlo. El código sí puede guardarse normalmente en tu repositorio.
