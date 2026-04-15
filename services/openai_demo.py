# Сервис демо AI для онбординга (OpenAI + ElevenLabs TTS)
# ✅ ВСЕ ОПЕРАЦИИ АСИНХРОННЫЕ для поддержки 500+ пользователей
import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Профессиональный промпт Grego из zaebot
DEMO_SYSTEM_PROMPT = """Eres Grego, un español con CARÁCTER que vive en Madrid desde hace más de 25 años.

⚠️ IDIOMA: ¡SOLO ESPAÑOL (ESPAÑA)! Sin excepciones.

SITUACIÓN: Encuentro casual con un viejo amigo en una plaza de Madrid.

TU PERSONALIDAD (¡CON CARÁCTER!):
- Vives en Madrid con tu familia (esposa, hija)
- Te encanta el fútbol (Real Madrid), El Retiro, los bares de tapas
- Eres cálido pero DIRECTO — no te gustan las respuestas vagas
- Si el amigo responde muy corto o confuso → pides que explique más
- ODIAS repetirte — cada respuesta debe ser NUEVA y DIFERENTE

⚠️ REGLAS ANTI-REPETICIÓN (¡CRÍTICO!):
- ❌ NUNCA empieces con "¡Hola!" después de la primera réplica
- ❌ NUNCA repitas temas que ya mencionaste
- ❌ NUNCA hagas las mismas preguntas
- ✅ Cada réplica debe tener NUEVO contenido
- ✅ Reacciona a lo que DIJO el amigo, no ignores

NIVEL: A2 (frases simples, vocabulario básico)
LONGITUD: 30-50 palabras (para audio 10-15 seg)
ESTILO: Natural, pausas (...), preguntas, exclamaciones"""


def get_context_hint(turn: int) -> str:
    """Возвращает контекстную подсказку для каждой реплики."""
    if turn == 2:
        return """RÉPLICA 2 — REACCIÓN AL SALUDO:
✅ ¡REACCIONA a lo que dijo el amigo! No ignores su mensaje.
✅ Cuenta algo NUEVO: tu trabajo, un bar favorito, el partido del domingo
✅ Haz una pregunta sobre SU vida: "¿Y tú qué tal? ¿Trabajas por aquí?"
❌ ¡NO saludes otra vez! Ya lo hiciste.
❌ ¡NO repitas que llevas 25 años en Madrid!"""
    elif turn == 3:
        return """RÉPLICA 3 — DESARROLLO INTERESANTE:
✅ Reacciona a su respuesta con entusiasmo
✅ Cuenta una anécdota corta o plan para el fin de semana
✅ Propón algo: "¿Quedamos para unas cañas?"
❌ ¡NO repitas temas anteriores!
❌ ¡NO menciones otra vez a tu familia!"""
    else:
        return """RÉPLICA 4 — DESPEDIDA CÁLIDA:
✅ Despídete con cariño: "¡Qué alegría haberte visto!"
✅ Propón vernos pronto: "¡Llámame y quedamos!"
✅ Deseo final: "¡Cuídate mucho!"
❌ Esta es la ÚLTIMA réplica, hazla memorable"""


async def translate_to_russian(api_key: str, spanish_text: str) -> str:
    """Переводит испанский текст на русский через OpenAI. ✅ ASYNC"""
    try:
        client = AsyncOpenAI(api_key=api_key)
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты переводчик. Переведи текст с испанского на русский. Сохрани эмоции и стиль. Только перевод, без пояснений."},
                {"role": "user", "content": spanish_text},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        
        translation = response.choices[0].message.content.strip()
        logger.info(f"[translate] Перевод: {translation[:50]}...")
        return translation
        
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        return "Перевод недоступен"


async def generate_demo_response(
    api_key: str,
    user_message: str,
    turn: int = 1,
    max_turns: int = 3,
) -> str:
    """Генерирует ответ демо AI через OpenAI с характером Grego. ✅ ASYNC"""
    try:
        client = AsyncOpenAI(api_key=api_key)
        
        if turn > max_turns:
            return "Ладно, амиго, мне пора бежать! Было здорово поболтать. Ты знаешь где меня найти — заходи ещё! Пока-пока!"
        
        context_hint = get_context_hint(turn)
        user_content = f"Réplica del amigo: '{user_message}'\n\n{context_hint}\n\nResponde en español (30-50 palabras):"
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DEMO_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=150,
            temperature=0.9,
        )
        
        grego_text = response.choices[0].message.content.strip()
        
        if grego_text.startswith('"') and grego_text.endswith('"'):
            grego_text = grego_text[1:-1]
        
        logger.info(f"[demo] AI ответ (turn={turn}): {grego_text[:50]}...")
        return grego_text
        
    except Exception as e:
        logger.error(f"Ошибка OpenAI демо: {e}")
        return get_fallback_response(turn)


def _sync_generate_voice(
    elevenlabs_api_key: str,
    text: str,
    voice_id: str,
) -> Optional[bytes]:
    """Синхронная генерация голоса (вызывается в отдельном потоке)."""
    try:
        from elevenlabs import ElevenLabs
        from elevenlabs.types import VoiceSettings
        
        client = ElevenLabs(api_key=elevenlabs_api_key)
        
        voice_settings = VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
        )
        
        audio_generator = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id="eleven_flash_v2_5",
            output_format="mp3_44100_128",
            voice_settings=voice_settings,
        )
        
        audio_bytes = b"".join(audio_generator)
        logger.info(f"[TTS] Сгенерировано {len(audio_bytes)} байт аудио")
        return audio_bytes
        
    except Exception as e:
        logger.error(f"Ошибка ElevenLabs TTS: {e}")
        return None


async def generate_voice_response(
    elevenlabs_api_key: str,
    text: str,
    voice_id: str = "RuJuetv6EsF42EMkBapY",
) -> Optional[bytes]:
    """
    Генерирует голосовой ответ через ElevenLabs.
    
    ✅ АСИНХРОННАЯ версия — не блокирует event loop!
    Использует asyncio.to_thread() для выполнения в отдельном потоке.
    """
    try:
        # Выполняем синхронный вызов ElevenLabs в отдельном потоке
        audio_bytes = await asyncio.to_thread(
            _sync_generate_voice,
            elevenlabs_api_key,
            text,
            voice_id,
        )
        return audio_bytes
        
    except Exception as e:
        logger.error(f"Ошибка async TTS: {e}")
        return None


# Заготовленные ответы для fallback
FALLBACK_RESPONSES = [
    "¡Hola, amigo! ¡Qué alegría verte por aquí! Llevo ya veinticinco años en Madrid, con mi esposa y mi hija. ¿Qué tal te va a ti? ¿Cómo estás?",
    "¡Qué bien! Oye, ¿sabes qué? Este fin de semana hay partido del Real Madrid. ¿Te gusta el fútbol? A mí me encanta, siempre voy al Bernabéu cuando puedo.",
    "¡Ha sido genial hablar contigo, amigo! Me alegro mucho de verte. ¡Pásate cuando quieras, aquí estaré! ¡Hasta pronto y mucha suerte!",
]


def get_fallback_response(turn: int) -> str:
    """Возвращает заготовленный ответ для fallback."""
    if turn <= 0:
        turn = 1
    if turn > len(FALLBACK_RESPONSES):
        turn = len(FALLBACK_RESPONSES)
    return FALLBACK_RESPONSES[turn - 1]
