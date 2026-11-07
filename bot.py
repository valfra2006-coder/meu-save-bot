import re
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
import yt_dlp

TOKEN = os.getenv("TELEGRAM_TOKEN", "COLOCA_O_TEU_TOKEN_AQUI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

logging.basicConfig(level=logging.INFO)

ai_client = None
gemini_model = None
try:
    if OPENAI_API_KEY:
        import openai
        ai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    print(f"OpenAI nao configurado: {e}")
try:
    if GEMINI_API_KEY and not ai_client:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-3.8-flash")
except Exception as e:
    print(f"Gemini nao configurado: {e}")

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
        if ai_client:
            resp = ai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], temperature=0.9, max_tokens=600)
            return resp.choices[0].message.content
        if gemini_model:
            resp = gemini_model.generate_content(prompt)
            return resp.text
        return f"NOVA DESCRICAO:\n{titulo} - versao reescrita: {descricao_original[:300]}\n\nNOVAS HASHTAGS:\n{hashtags_originais} #viral #fyp #portugal\n\n(Adiciona OPENAI_API_KEY ou GEMINI_API_KEY no Railway para ativar a IA completa)"
    except Exception as e:
        return f"❌ Erro na IA: {e}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Ola! Manda-me um link do Instagram / TikTok / YouTube / Pinterest e eu devolvo-te o video + Titulo + Descricao + Hashtags + Nova Descricao com IA ✨")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "http" not in url:
        await update.message.reply_text("Manda-me um link 📎 Ex: https://www.tiktok.com/...")
        return
    msg = await update.message.reply_text("A analisar o link... 🔍")
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info: info = info['entries'][0]
        texto_info, titulo, descricao, hashtags = formatar_info(info)
        context.user_data['last_url'] = url
        context.user_data['last_info'] = texto_info
        context.user_data['titulo'] = titulo
        context.user_data['descricao'] = descricao
        context.user_data['hashtags'] = hashtags
        keyboard = [
            [InlineKeyboardButton("✨ Gerar Nova Descrição com IA", callback_data="ai_rewrite")],
            [InlineKeyboardButton("⬇️ Descarregar Vídeo", callback_data="dl_video")],
            [InlineKeyboardButton("🎵 Só Áudio (MP3)", callback_data="dl_audio")],
            [InlineKeyboardButton("📋 Copiar Hashtags", callback_data="copy_hashtags")],
        ]
        await msg.edit_text(f"{texto_info}\n\n<i>Escolhe:</i>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ Não consegui ler este link. Pode ser privado ou bloqueado.\n\nErro: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = context.user_data.get('last_url')
    titulo = context.user_data.get('titulo','')
    descricao = context.user_data.get('descricao','')
    hashtags = context.user_data.get('hashtags','')
    if query.data == "ai_rewrite":
        await query.edit_message_text("✨ A IA está a reescrever a tua descrição... Aguarda 5 seg.")
        nova = await gerar_nova_descricao(titulo, descricao, hashtags)
        context.user_data['last_ai'] = nova
        keyboard = [
            [InlineKeyboardButton("🔁 Gerar Outra Vez", callback_data="ai_rewrite")],
            [InlineKeyboardButton("📋 Copiar Nova Descrição", callback_data="copy_ai")],
            [InlineKeyboardButton("⬇️ Descarregar Vídeo", callback_data="dl_video")],
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
            [InlineKeyboardButton("⬇️ Descarregar Vídeo", callback_data="dl_video")],
            [InlineKeyboardButton("🎵 Só Áudio (MP3)", callback_data="dl_audio")],
            [InlineKeyboardButton("📋 Copiar Hashtags", callback_data="copy_hashtags")],
        ]
        await query.edit_message_text(texto_info, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if query.data == "copy_hashtags":
        await query.message.reply_text(f"Hashtags:\n\n<code>{hashtags}</code>", parse_mode="HTML")
        return
    if query.data in ["dl_video","dl_audio"]:
        if not url:
            await query.edit_message_text("Link expirado. Manda o link outra vez.")
            return
        await query.edit_message_text("A descarregar... ⏳")
        is_audio = query.data == "dl_audio"
        ydl_opts = {
            'format': 'bestaudio/best' if is_audio else 'best[ext=mp4]/best',
            'outtmpl': 'download.%(ext)s',
            'quiet': True,
            'postprocessors': [{'key':'FFmpegExtractAudio','preferredcodec':'mp3'}] if is_audio else [],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dl = ydl.extract_info(url, download=True)
                if 'entries' in info_dl: info_dl = info_dl['entries'][0]
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
            await query.message.reply_text(f"❌ Erro: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot a correr com IA...")
    app.run_polling()
