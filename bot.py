import re
import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
import yt_dlp

TOKEN = os.getenv("TELEGRAM_TOKEN", "COLOCA_O_TEU_TOKEN_AQUI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- CADEADO - SO TU USAS ---
ALLOWED_IDS = os.getenv("ALLOWED_USER_IDS", "161211861").split(",")
ALLOWED_IDS = [x.strip() for x in ALLOWED_IDS if x.strip()]
def pode_usar(user_id):
    return str(user_id) in ALLOWED_IDS

logging.basicConfig(level=logging.INFO)

gemini_client = None
try:
    if GEMINI_API_KEY:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Gemini nao ligado: {e}")

ai_client = None
try:
    if OPENAI_API_KEY:
        import openai
        ai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    print(f"OpenAI nao configurado: {e}")

def extrair_hashtags(texto: str):
    if not texto: return []
    return re.findall(r'#\w+', texto)

def limpar_descricao(descricao: str):
    if not descricao: return "Sem descricao"
    limpo = re.sub(r'#\w+', '', descricao).strip()
    if len(limpo) > 800: limpo = limpo[:800] + "..."
    return limpo if limpo else "Sem descricao"

def formatar_info(info):
    titulo = info.get('title') or "Sem titulo"
    descricao_raw = info.get('description') or ""
    autor = info.get('uploader') or info.get('channel') or "Desconhecido"
    plataforma = info.get('extractor_key') or "Desconhecido"
    hashtags = set(info.get('tags') or [])
    hashtags.update([h.replace('#','') for h in extrair_hashtags(descricao_raw)])
    hashtags_formatadas = " ".join([f"#{h}" for h in sorted(hashtags)]) if hashtags else "Sem hashtags"
    descricao_limpa = limpar_descricao(descricao_raw)
    texto = (
        f"🎬 <b>TITULO</b>\n{titulo}\n\n"
        f"👤 <b>Autor:</b> {autor}\n🌐 <b>Plataforma:</b> {plataforma}\n\n"
        f"📝 <b>DESCRICAO</b>\n{descricao_limpa}\n\n"
        f"#️⃣ <b>HASHTAGS ({len(hashtags)})</b>\n{hashtags_formatadas}"
    )
    return texto, titulo, descricao_limpa, hashtags_formatadas

# --- ARRANJO INSTAGRAM FOTO ---
def buscar_instagram_pela_capa(url):
    """Quando o yt-dlp falha no Instagram foto, vai buscar a capa / og:image"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
        # Tenta a pagina embed, que o Instagram deixa ver sem login
        shortcode = url.split("/p/")[1].split("/")[0].split("?")[0]
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
        r = requests.get(embed_url, headers=headers, timeout=15)
        html = r.text
        # Procura og:image, og:title, og:description
        def pega(prop):
            m = re.search(rf'<meta property="{prop}" content="([^"]+)"', html)
            if m: return m.group(1)
            m = re.search(rf'<meta name="{prop}" content="([^"]+)"', html)
            return m.group(1) if m else ""
        img = pega("og:image")
        titulo = pega("og:title") or "Post do Instagram"
        descricao = pega("og:description") or ""
        # Limpa entidades html
        import html as html_lib
        titulo = html_lib.unescape(titulo)
        descricao = html_lib.unescape(descricao)
        return {"title": titulo, "description": descricao, "uploader": "Instagram", "extractor_key": "Instagram", "tags": [], "thumbnail": img, "is_photo_fallback": True, "photo_url": img}
    except Exception as e:
        print(f"Fallback Instagram falhou: {e}")
        return None

async def gerar_nova_descricao(titulo, descricao_original, hashtags_originais):
    prompt = f"""
Tu es especialista em legendas virais para 【entity-Instagram¦canonical_name=Instagram】, TikTok e YouTube Shorts.
Reescreve esta descricao para a pessoa poder republicar o video sem ser copia.
Titulo original: {titulo}
Descricao original: {descricao_original}
Hashtags originais: {hashtags_originais}
Regras:
1. Usa portugues de Portugal, informal e com emojis, mas sem exagero.
2. Mantem o sentido, mas muda 100% as palavras e a estrutura.
3. Comeca com um gancho forte na primeira linha.
4. No fim, adiciona uma CTA (ex: Guarda para depois, Segue para mais).
5. Cria 12 hashtags novas, misturando grandes + nicho, em portugues e ingles.
6. Devolve APENAS neste formato:
NOVA DESCRICAO:
[texto aqui]
NOVAS HASHTAGS:
[hashtags aqui]
"""
    try:
        if gemini_client:
            resp = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            return resp.text
        if ai_client:
            resp = ai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], temperature=0.9, max_tokens=600)
            return resp.choices[0].message.content
        return "Sem chave de IA configurada."
    except Exception as e:
        return f"❌ Erro na IA: {e}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pode_usar(update.effective_user.id):
        await update.message.reply_text("🔒 Este bot e privado. So a dona pode usar.")
        return
    await update.message.reply_text("👋 Ola! Manda-me um link do Instagram / TikTok / YouTube / Pinterest e eu devolvo-te o video + Titulo + Descricao + Hashtags + Nova Descricao com IA ✨")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pode_usar(update.effective_user.id):
        await update.message.reply_text("🔒 Este bot e privado. So a dona pode usar.")
        return
    url_original = update.message.text.strip()
    if "http" not in url_original:
        await update.message.reply_text("Manda-me um link 📎")
        return
    # Limpa tudo a partir do ? - tira img_index, mdx, etc.
    url = url_original.split('?')[0]
    # Garante / no fim para Instagram
    if "instagram.com" in url and not url.endswith("/"):
        url += "/"
    msg = await update.message.reply_text("A analisar o link... 🔍")
    info = None
    is_instagram_photo = False
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
    except Exception as e:
        print(f"yt-dlp falhou: {e}")
        # Se for Instagram, tenta o fallback da capa
        if "instagram.com" in url:
            await msg.edit_text("📸 Este post é só foto, o Instagram bloqueou o download normal. Vou buscar pela capa...")
            info = buscar_instagram_pela_capa(url)
            if info:
                is_instagram_photo = True
            else:
                await msg.edit_text("❌ O 【entity-Instagram¦canonical_name=Instagram】 bloqueou este post.\n\nTenta assim:\n1. Abre o post no 【entity-Instagram¦canonical_name=Instagram】\n2. Clica nos 3 pontinhos > Copiar link\n3. Cola aqui sem o ? no fim\n\nSe for de conta privada, o bot não consegue ver.")
                return
        else:
            await msg.edit_text(f"❌ Não consegui ler este link. Pode ser privado ou bloqueado.\n\nErro: {e}")
            return
    if not info:
        await msg.edit_text("❌ Não consegui ler este link.")
        return
    texto_info, titulo, descricao, hashtags = formatar_info(info)
    context.user_data['last_url'] = url
    context.user_data['last_info'] = texto_info
    context.user_data['titulo'] = titulo
    context.user_data['descricao'] = descricao
    context.user_data['hashtags'] = hashtags
    context.user_data['photo_url'] = info.get('photo_url') or info.get('thumbnail') or ""
    context.user_data['is_photo'] = is_instagram_photo
    # Se for foto do Instagram, manda logo a foto
    if is_instagram_photo and context.user_data['photo_url']:
        try:
            await update.message.reply_photo(photo=context.user_data['photo_url'], caption="📸 Foto do 【entity-Instagram¦canonical_name=Instagram】")
        except Exception:
            pass
    keyboard = [
        [InlineKeyboardButton("✨ Gerar Nova Descrição com IA", callback_data="ai_rewrite")],
        [InlineKeyboardButton("⬇️ Descarregar Vídeo / Foto", callback_data="dl_video")],
        [InlineKeyboardButton("🎵 Só Áudio (MP3)", callback_data="dl_audio")],
        [InlineKeyboardButton("📋 Copiar Hashtags", callback_data="copy_hashtags")],
    ]
    await msg.edit_text(f"{texto_info}\n\n<i>Escolhe:</i>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not pode_usar(query.from_user.id):
        await query.message.reply_text("🔒 Este bot e privado. So a dona pode usar.")
        return
    url = context.user_data.get('last_url')
    titulo = context.user_data.get('titulo','')
    descricao = context.user_data.get('descricao','')
    hashtags = context.user_data.get('hashtags','')
    photo_url = context.user_data.get('photo_url','')
    is_photo = context.user_data.get('is_photo', False)
    if query.data == "ai_rewrite":
        await query.edit_message_text("✨ A IA está a reescrever a tua descrição... Aguarda 5 seg.")
        nova = await gerar_nova_descricao(titulo, descricao, hashtags)
        context.user_data['last_ai'] = nova
        keyboard = [
            [InlineKeyboardButton("🔁 Gerar Outra Vez", callback_data="ai_rewrite")],
            [InlineKeyboardButton("📋 Copiar Nova Descrição", callback_data="copy_ai")],
            [InlineKeyboardButton("⬇️ Descarregar Vídeo / Foto", callback_data="dl_video")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="back_to_info")],
        ]
        await query.edit_message_text(f"✨ <b>NOVA DESCRIÇÃO GERADA PELA IA</b>\n\n{nova}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if query.data == "copy_ai":
        nova = context.user_data.get('last_ai','Ainda não geraste nenhuma.')
        await query.message.reply_text(f"<code>{nova}</code>", parse_mode="HTML")
        return
    if query.data == "back_to_info":
        texto_info = context.user_data.get('last_info','')
        keyboard = [
            [InlineKeyboardButton("✨ Gerar Nova Descrição com IA", callback_data="ai_rewrite")],
            [InlineKeyboardButton("⬇️ Descarregar Vídeo / Foto", callback_data="dl_video")],
            [InlineKeyboardButton("🎵 Só Áudio (MP3)", callback_data="dl_audio")],
            [InlineKeyboardButton("📋 Copiar Hashtags", callback_data="copy_hashtags")],
        ]
        await query.edit_message_text(texto_info, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if query.data == "copy_hashtags":
        await query.message.reply_text(f"Hashtags:\n\n<code>{hashtags}</code>", parse_mode="HTML")
        return
    if query.data in ["dl_video","dl_audio"]:
        # Se for foto do Instagram, manda logo a foto guardada
        if is_photo and photo_url and query.data == "dl_video":
            await query.message.reply_photo(photo=photo_url, caption=f"🎬 {titulo[:200]}")
            return
        if not url:
            await query.edit_message_text("Link expirado. Manda o link outra vez.")
            return
        await query.edit_message_text("A descarregar... ⏳")
        is_audio = query.data == "dl_audio"
        ydl_opts = {
            'format': 'bestaudio/best' if is_audio else 'best/bestimage/best',
            'outtmpl': 'download.%(ext)s',
            'quiet': True,
            'postprocessors': [{'key':'FFmpegExtractAudio','preferredcodec':'mp3'}] if is_audio else [],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dl = ydl.extract_info(url, download=True)
                if 'entries' in info_dl and info_dl['entries']:
                    info_dl = info_dl['entries'][0]
                filename = ydl.prepare_filename(info_dl)
                if is_audio: filename = os.path.splitext(filename)[0] + ".mp3"
            caption = f"🎬 {info_dl.get('title','')[:200]}"
            if is_audio:
                await query.message.reply_audio(audio=open(filename,'rb'), caption=caption)
            elif filename.endswith('.mp4'):
                await query.message.reply_video(video=open(filename,'rb'), caption=caption)
            else:
                await query.message.reply_photo(photo=open(filename,'rb'), caption=caption)
            os.remove(filename)
        except Exception as e:
            # Último recurso: manda a foto da capa
            if photo_url:
                await query.message.reply_photo(photo=photo_url, caption=f"📸 Foto (o Instagram bloqueou o vídeo): {titulo[:200]}")
            else:
                await query.message.reply_text(f"❌ O Instagram bloqueou o download deste post. Mas já tens o Título + Descrição + Hashtags em cima, e a IA funciona na mesma! Erro: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot a correr com IA nova, privado e fix Instagram...")
    app.run_polling()
