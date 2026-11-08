
import os
import re
import asyncio
import logging
import requests

from urllib.parse import urlparse
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from google import genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

PLATFORMS = {
    "instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "pinterest.com": "Pinterest",
    "pin.it": "Pinterest",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
}

def identify_platform(url):
    try:
        domain = urlparse(url).hostname
        if not domain:
            return None

        domain = domain.lower().removeprefix("www.")

        for site, name in PLATFORMS.items():
            if domain == site or domain.endswith("." + site):
                return name
    except ValueError:
        pass

    return None


def get_metadata(url, platform):
    endpoints = {
        "TikTok": "https://www.tiktok.com/oembed",
        "YouTube": "https://www.youtube.com/oembed",
    }

    if platform not in endpoints:
        return {}

    try:
        response = requests.get(
            endpoints[platform],
            params={"url": url},
            timeout=15,
            headers={"User-Agent": "SaveLinkBot/1.0"}
        )
        response.raise_for_status()
        data = response.json()

        return {
            "title": data.get("title", ""),
            "author": data.get("author_name", ""),
        }
    except requests.RequestException:
        return {}


def generate_content(platform, title, original, user_context):
    if not client:
        return "A inteligência artificial ainda não está configurada."

    prompt = f"""
És o assistente de criação de conteúdo do SaveLink.

Escreve SEMPRE em português.

Analisa os dados disponíveis sem inventar informações.

Plataforma: {platform}
Título original: {title}
Descrição original: {original}
Contexto adicional: {user_context}

Cria uma resposta organizada com:

1. TÍTULO MELHORADO
2. DESCRIÇÃO ORIGINAL OU DADOS DISPONÍVEIS
3. HASHTAGS RELEVANTES
4. NOVA DESCRIÇÃO COM IA

Adapta o estilo automaticamente ao assunto:
- Motivação: inspirador.
- Humor: descontraído.
- Educação: informativo.
- Beleza: apelativo e elegante.
- Negócios: profissional.
- Entretenimento: criativo.

Não inventes produtos, pessoas, acontecimentos ou características.
Não afirmes que viste o vídeo se apenas recebeste o título ou a descrição.
Cria hashtags relevantes e evita repetições.
Não acrescentes informações que não estejam fundamentadas.

Apresenta apenas o resultado final, bem organizado.
"""

    try:
        result = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return result.text or "Não foi possível gerar o texto."
    except Exception:
        logger.exception("Erro na geração de conteúdo")
        return "Não foi possível gerar o texto com IA neste momento."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá!\n\n"
        "Manda-me um link do Instagram / TikTok / "
        "YouTube / Pinterest e eu devolvo-te:\n\n"
        "🎬 Vídeo, quando disponível por uma fonte autorizada\n"
        "📝 Título\n"
        "📄 Descrição\n"
        "#️⃣ Hashtags\n"
        "✨ Nova descrição com IA"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 COMO UTILIZAR O SAVELINK\n\n"
        "1. Envia um link de uma plataforma suportada.\n"
        "2. Se necessário, acrescenta a descrição ou "
        "um pequeno resumo do conteúdo.\n"
        "3. Recebe o texto criado pela IA.\n\n"
        "Comandos:\n"
        "/start - Iniciar\n"
        "/help - Ajuda\n"
        "/platforms - Plataformas\n"
        "/about - Sobre"
    )


async def platforms_command(update, context):
    await update.message.reply_text(
        "🌐 PLATAFORMAS\n\n"
        "📸 Instagram\n"
        "🎵 TikTok\n"
        "▶️ YouTube\n"
        "📌 Pinterest"
    )


async def about(update, context):
    await update.message.reply_text(
        "SaveLink\n"
        "Your Links. Your Library.\n\n"
        "Um assistente de análise e criação "
        "de conteúdo com inteligência artificial."
    )


async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    links = re.findall(r"https?://[^\s<>]+", message)

    if not links:
        await update.message.reply_text(
            "Envia um link válido para começar."
        )
        return

    for url in links[:1]:
        url = url.rstrip(".,!?;:)]}")
        platform = identify_platform(url)

        if not platform:
            await update.message.reply_text(
                "Não reconheci essa plataforma."
            )
            continue

        user_context = re.sub(
            r"https?://[^\s<>]+", "", message
        ).strip()

        status = await update.message.reply_text(
            "⏳ A analisar o conteúdo...\n"
            "✨ A preparar a criação com IA."
        )

        metadata = await asyncio.to_thread(
            get_metadata, url, platform
        )

        title = metadata.get("title", "")
        author = metadata.get("author", "")

        if not title and not user_context:
            await status.edit_text(
                f"🔎 Identifiquei: {platform}\n\n"
                "Não consegui obter a descrição original "
                "deste conteúdo.\n\n"
                "Envia novamente o link acompanhado "
                "da descrição ou de um pequeno resumo "
                "do vídeo para eu criar o texto com IA.\n\n"
                f"🔗 {url}"
            )
            continue

        result = await asyncio.to_thread(
            generate_content,
            platform,
            title,
            author,
            user_context
        )

        response = (
            f"✨ SAVELINK — RESULTADO\n\n"
            f"🌐 Plataforma: {platform}\n"
            f"📝 Título original: {title or 'Não disponível'}\n"
            f"👤 Autor: {author or 'Não disponível'}\n\n"
            f"{result}\n\n"
            f"🔗 Conteúdo original:\n{url}\n\n"
            "🎬 O ficheiro de vídeo não foi descarregado "
            "nesta versão."
        )

        await status.edit_text(response)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("platforms", platforms_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_link
        )
    )

    logger.info("SaveLink iniciado!")
    app.run_polling()


if __name__ == "__main__":
    main()
