
import os
import re
import json
import asyncio
import logging
from urllib.parse import urlparse, quote

import requests
from google import genai
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =====================================
# CONFIGURAÇÕES
# =====================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

BOT_NAME = "SaveLink"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Cliente Gemini
gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)

# =====================================
# IDENTIFICAR PLATAFORMAS
# =====================================

def identify_platform(url):

    try:
        hostname = urlparse(url).hostname or ""
        hostname = hostname.lower()

        if hostname.endswith("instagram.com"):
            return "Instagram"

        if hostname.endswith("tiktok.com"):
            return "TikTok"

        if hostname in (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
        ):
            return "YouTube"

        if hostname.endswith("pinterest.com") or hostname.endswith("pin.it"):
            return "Pinterest"

        return None

    except Exception:
        return None


def extract_url(message):

    pattern = r"https?://[^\s<>]+"
    matches = re.findall(pattern, message)

    if not matches:
        return None

    return matches[0].rstrip(".,!?)]}")


# =====================================
# CONSULTAR METADADOS PÚBLICOS
# =====================================

def get_metadata(url, platform):

    endpoint = None

    if platform == "YouTube":
        endpoint = (
            "https://www.youtube.com/oembed"
            f"?url={quote(url, safe='')}&format=json"
        )

    elif platform == "TikTok":
        endpoint = (
            "https://www.tiktok.com/oembed"
            f"?url={quote(url, safe='')}"
        )

    else:
        return {}

    try:
        response = requests.get(
            endpoint,
            timeout=15,
            headers={
                "User-Agent": "SaveLinkBot/1.0"
            }
        )

        response.raise_for_status()

        data = response.json()

        return {
            "title": data.get("title", ""),
            "author": data.get("author_name", ""),
            "provider": data.get("provider_name", platform),
        }

    except Exception as error:
        logger.warning(
            "Não foi possível obter metadados: %s",
            error
        )
        return {}


# =====================================
# GERAR CONTEÚDO COM GEMINI
# =====================================

def generate_content(platform, metadata):

    if not gemini_client:
        return None

    title = metadata.get("title", "")
    author = metadata.get("author", "")

    prompt = f"""
És o assistente de conteúdo do SaveLink.

Escreve sempre em português.

Plataforma: {platform}
Título disponibilizado pela plataforma: {title}
Autor disponibilizado pela plataforma: {author}

Cria uma resposta organizada com:

1. Título sugerido
2. Resumo
3. Nova descrição para publicação
4. Hashtags relevantes

REGRAS IMPORTANTES:
- Não inventes informações sobre o vídeo.
- Não afirmes que viste ou analisaste o vídeo.
- Se não houver título ou descrição disponíveis,
  informa que os dados do conteúdo são limitados.
- Nesse caso, cria uma descrição genérica e
  identifica-a como sugestão.
- Não inventes nomes, acontecimentos ou pessoas.
- Usa linguagem natural e adequada ao conteúdo disponível.
- Evita hashtags excessivas.
"""

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        return response.text or None

    except Exception as error:
        logger.error("Erro Gemini: %s", error)
        return None


# =====================================
# COMANDO START
# =====================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = (
        "Olá! Sou o SaveLink.\n\n"
        "Envia-me um link público de:\n"
        "Instagram\n"
        "TikTok\n"
        "YouTube\n"
        "Pinterest\n\n"
        "Vou tentar identificar a plataforma e "
        "preparar informações e sugestões de texto.\n\n"
        "Nota: esta versão ainda não descarrega vídeos."
    )

    await update.message.reply_text(message)


# =====================================
# COMANDO HELP
# =====================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Como utilizar o SaveLink:\n\n"
        "1. Copia um link público.\n"
        "2. Envia o link aqui.\n"
        "3. Aguarda a análise dos dados disponíveis.\n\n"
        "Se a plataforma não disponibilizar metadados, "
        "poderás enviar também o título ou a legenda "
        "do conteúdo.\n\n"
        "O SaveLink não acede a contas privadas nem "
        "contorna restrições de acesso."
    )


# =====================================
# RECEBER E PROCESSAR LINKS
# =====================================

async def process_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message or not message.text:
        return

    url = extract_url(message.text)

    if not url:
        await message.reply_text(
            "Envia um link válido para começar."
        )
        return

    platform = identify_platform(url)

    if not platform:
        await message.reply_text(
            "Ainda não reconheço essa plataforma.\n"
            "Aceito Instagram, TikTok, YouTube e Pinterest."
        )
        return

    status = await message.reply_text(
        f"A analisar o link do {platform}...\n"
        "Aguarda um momento."
    )

    try:

        metadata = await asyncio.to_thread(
            get_metadata,
            url,
            platform
        )

        result = await asyncio.to_thread(
            generate_content,
            platform,
            metadata
        )

        if result:

            response_text = (
                f"SaveLink | {platform}\n\n"
                f"{result}\n\n"
                "Link original:\n"
                f"{url}\n\n"
                "Nota: o vídeo não foi descarregado "
                "nesta versão."
            )

        else:

            response_text = (
                f"SaveLink | {platform}\n\n"
                "Não consegui gerar a análise com IA.\n\n"
                "Dados públicos encontrados:\n"
                f"Título: {metadata.get('title') or 'Não disponível'}\n"
                f"Autor: {metadata.get('author') or 'Não disponível'}\n\n"
                "Podes enviar a legenda ou o título "
                "do conteúdo para obter uma análise mais completa.\n\n"
                f"Link original:\n{url}"
            )

        await status.edit_text(
            response_text[:4000]
        )

    except Exception as error:

        logger.exception("Erro ao processar link")

        await status.edit_text(
            "Ocorreu um erro ao analisar o link.\n"
            "Tenta novamente mais tarde."
        )


# =====================================
# TRATAR ERROS DO BOT
# =====================================

async def error_handler(update, context):

    logger.error(
        "Erro durante a execução:",
        exc_info=context.error
    )


# =====================================
# INICIAR SAVE LINK
# =====================================

def main():

    if not TELEGRAM_TOKEN:
        raise RuntimeError(
            "Falta configurar TELEGRAM_BOT_TOKEN."
        )

    if not GEMINI_API_KEY:
        logger.warning(
            "GEMINI_API_KEY não configurada. "
            "O bot funcionará sem geração por IA."
        )

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            process_link
        )
    )

    application.add_error_handler(error_handler)

    logger.info("SaveLink iniciado.")

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
