import os
import re
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import google.generativeai as genai

# Configurações de API (Pegando das variáveis de ambiente ou direto aqui)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "SEU_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "SUA_GEMINI_API_KEY")

# 🔒 Insira o seu ID numérico do Telegram aqui para tornar o bot privado
MEU_ID_TELEGRAM = 161211861  # ID configurado com sucesso!

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

def download_social_media(url):
    ydl_opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'Sem título')
        description = info.get('description', 'Sem descrição')
        filename = ydl.prepare_filename(info)
        
        hashtags = re.findall(r'#\w+', description)
        
        return {
            'file_path': filename,
            'title': title,
            'description': description,
            'hashtags': " ".join(hashtags) if hashtags else "Nenhuma hashtag encontrada."
        }

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 VERIFICAÇÃO DE SEGURANÇA: Ignora qualquer usuário que não seja você
    user_id = update.message.from_user.id
    if user_id != MEU_ID_TELEGRAM:
        await update.message.reply_text("⛔ Desculpe, este bot é privado e restrito ao proprietário.")
        return

    url = update.message.text
    if not url.startswith("http"):
        await update.message.reply_text("Por favor, envie um link válido.")
        return

    await update.message.reply_text("Processando o link e baixando a mídia...")

    try:
        data = download_social_media(url)
        context.user_data['last_data'] = data

        with open(data['file_path'], 'rb') as media_file:
            caption_text = (
                f"📌 **Título:** {data['title']}\n\n"
                f"📝 **Descrição:** {data['description'][:300]}...\n\n"
                f"🏷️ **Hashtags:** {data['hashtags']}"
            )
            await update.message.reply_video(video=media_file, caption=caption_text, parse_mode="Markdown")

        if os.path.exists(data['file_path']):
            os.remove(data['file_path'])

        keyboard = [[InlineKeyboardButton("✨ Analisar/Reescrever com IA", callback_data="process_ai")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Deseja aplicar Inteligência Artificial nesta legenda?", reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"Erro ao processar o link: {str(e)}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "process_ai":
        data = context.user_data.get('last_data')
        if not data:
            await query.edit_message_text("Dados não encontrados.")
            return

        await query.edit_message_text("🤖 Gerando nova versão com IA...")

        prompt = f"""
        Com base nas seguintes informações de um post nas redes sociais:
        Título: {data['title']}
        Descrição: {data['description']}
        
        Crie uma nova legenda atraente para redes sociais (Instagram/TikTok), incluindo:
        1. Um gancho chamativo para prender a atenção.
        2. O corpo do texto reorganizado.
        3. Um conjunto com as 10 melhores hashtags otimizadas para engajamento.
        """
        
        response = ai_model.generate_content(prompt)
        await query.message.reply_text(f"✨ **Sugestão gerada por IA:**\n\n{response.text}", parse_mode="Markdown")

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("Bot privado rodando com segurança...")
    app.run_polling()
