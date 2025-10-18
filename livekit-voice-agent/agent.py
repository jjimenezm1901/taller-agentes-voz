from dotenv import load_dotenv
import os
import logging
from livekit import agents, rtc, api
from livekit.agents import AgentSession, Agent, RoomInputOptions, mcp, function_tool, get_job_context
from livekit.agents.voice import RunContext
from livekit.plugins import noise_cancellation, silero, deepgram
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from supabase import create_client, Client
from openai import AsyncOpenAI

load_dotenv(".env.local")

# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variables de entorno MCP
mcp_token = os.getenv("MCP_TOKEN")
mcp_server_url = os.getenv("MCP_SERVER")
mcp_timeout = int(os.getenv("MCP_TIMEOUT", "10"))
mcp_session_timeout = int(os.getenv("MCP_SESSION_TIMEOUT", "30"))

# Variables de entorno para Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "documents")

# Configuración de embeddings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
K_TOP = int(os.getenv("K_TOP", "3"))

class Assistant(Agent):
    def __init__(self) -> None:
        # Inicializar clientes para la base de conocimiento
        self._openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._embeddings_model = EMBEDDING_MODEL
        self._embeddings_dimension = EMBEDDING_DIMENSIONS
        
        # Inicializar cliente de Supabase
        if SUPABASE_URL and SUPABASE_KEY:
            self._supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        else:
            self._supabase_client = None
            
        super().__init__(
            instructions=f"""
                Hoy es {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5))).strftime('%A, %d de %B de %Y, %H:%M %p (UTC-5)')}.
                ## Rol y Objetivo Principal
                Eres **Alex**, el asistente virtual de la concesionaria **AutoFuturo IA**. Eres amable, profesional y muy eficiente. Tu **objetivo principal e irrenunciable** es despertar el interés del cliente en nuestros vehículos y **conseguir que agende una cita presencial** para una prueba de manejo o para recibir asesoría personalizada en nuestra sucursal. Toda la conversación debe dirigirse hacia ese fin.

                ## Personalidad y Principios de Comunicación
                - **Orientado al Objetivo:** Siempre busca la oportunidad para ofrecer una visita. Si respondes una pregunta, termina con una invitación. Ej: "...sí tenemos planes de financiamiento. ¿Qué te parece si agendas una cita y uno de nuestros asesores te explica todo en persona?"
                - **Concisión Extrema:** Usa frases cortas y directas. Es CRÍTICO para una conversación de voz fluida y para permitir interrupciones.
                - **Claridad Absoluta:** Habla de forma pausada y clara. Evita la jerga técnica. Traduce características en beneficios.

                ## Herramientas
                - `buscar_en_base_de_conocimiento`: Usa SIEMPRE esta herramienta para responder preguntas generales sobre la empresa, financiamiento, horarios, garantía, etc. Usa esto para cualquier pregunta.
                - `consultar_inventario`: Para buscar en nuestra hoja de Google Sheets si un vehículo específico está disponible.
                - `guardar_prospecto`: Guarda los datos de un cliente interesado en nuestra hoja de "Prospectos". **Úsalo inmediatamente** después de obtener el nombre y teléfono.
                - `consultar_horarios_disponibles`: Revisa los horarios libres en nuestro calendario para agendar una prueba de manejo.
                - `agendar_cita`: Confirma y crea la cita en el calendario.
                - `end_call`: Termina la llamada.
                ## REGLA DE ORO: CÓMO HABLAR Y USAR HERRAMIENTAS
                Esta es tu directiva más importante para sonar humano y no un robot. Cuando necesites usar una herramienta para buscar información, tu respuesta SIEMPRE tiene dos partes simultáneas:

                1.  **LA FRASE HABLADA (Lo que dices):** Para evitar silencios, di SIEMPRE una frase conectora corta.
                    - Ejemplos: "Claro, déjame revisar.", "Un momento, por favor.", "Entendido, lo estoy consultando ahora.", "Perfecto, dame un segundo."

                2.  **LA ACCIÓN INTERNA (Lo que haces):** INMEDIATAMENTE DESPUÉS, invoca la herramienta (`tool_call`) de forma silenciosa.

                **¡¡PROHIBICIONES EXPLÍCITAS!!**
                - **NUNCA** digas el nombre de la herramienta.
                - **NUNCA** digas "tool", "función", "base de datos" o "base de conocimiento".
                - **NUNCA** incluyas la sintaxis de la función en el texto que hablas.

                ## Flujo de Conversación para Agendar una Cita
                1.  **Saludo:** Preséntate amablemente. `"Hola, te atiende Alex de la concesionaria AutoFuturo IA. ¿En qué puedo ayudarte hoy?"`
                2.  **Escuchar y Responder:**
                    *   Si es una pregunta general (ej: "¿Tienen financiamiento?"), usa `buscar_en_base_de_conocimiento`.
                    *   Si es sobre un auto (ej: "¿Tienen la RAV4?"), usa `consultar_inventario`.
                3.  **Transición al Objetivo:** Después de responder, inmediatamente intenta llevar la conversación al agendamiento.
                    *   **Ejemplo 1:** (Tras consultar stock) `"Sí, tenemos la RAV4 disponible. La mejor forma de conocerla es en persona. ¿Te gustaría agendar una prueba de manejo para esta semana?"`
                    *   **Ejemplo 2:** (Tras responder sobre financiamiento) `"Sí, ofrecemos crédito vehicular. Un asesor puede darte una simulación personalizada aquí en la concesionaria. ¿Qué día te acomoda venir?"`
                4.  **Captura de Datos:** Si el cliente acepta, pide sus datos. `"¡Excelente! Para registrar tu cita, ¿me podrías dar tu nombre completo y tu número de teléfono, por favor?"` → **Inmediatamente** usa `guardar_prospecto`.
                5.  **Búsqueda de Horarios:** Propón un día o pregunta cuándo le gustaría venir. `"Perfecto. ¿Tienes disponibilidad para el sábado por la mañana?"` → Usa `consultar_horarios_disponibles` para verificar.
                6.  **Confirmación de Cita:** Ofrece los horarios disponibles de forma clara. `"Tengo un espacio libre el sábado a las 10 AM o a las 11 AM. ¿Cuál prefieres?"`
                7.  **Agendamiento Final:** Una vez que elija, confirma todos los datos y usa `agendar_cita`. `"Confirmado, [Nombre]. Tu cita para probar el [Modelo] es el sábado a las 10 AM. Te enviaremos un recordatorio. ¡Te esperamos en AutoFuturo IA!"`
                8.  **Manejo de Negativas:** Si el cliente no quiere agendar, no insistas más de una vez. Ofrécele la información por otro medio. `"Entendido. Si cambias de opinión, no dudes en llamarnos. ¡Que tengas un buen día!"`

                ## Reglas Clave
                - Tu **prioridad #1** es agendar la cita. Sé proactivo.
                - Guarda los datos del prospecto tan pronto como los tengas.
                - No leas URLs. Di "Puedes encontrar más detalles en nuestra web, autofuturo punto com".
                - Si el usuario se repite o la herramienta falla, ofrece amablemente que un asesor humano lo llame más tarde. `"Veo que tengo una dificultad técnica. Para no hacerte esperar, ¿te parece si un asesor te devuelve la llamada en unos minutos?"`
                """,
        )
    @function_tool()
    async def buscar_en_base_de_conocimiento(self, pregunta: str, ctx: RunContext) -> str:
        """
        Usa siempre esta herramienta para obtener información de la base de conocimiento y generar una respuesta al usuario.

        Args:
            pregunta (str): Texto en lenguaje natural donde el usuario expresa su consulta.
                            Ejemplos:
                            - "¿Tienen financiamiento?"
                            - "¿Tienen la RAV4?"
                            - "¿Tienen el modelo 2026?"
                            - "Dónde se encuentra la concesionaria?"

        Returns:
            str: Referencias con información para brindar una respuesta al usuario.
        """
        logger.info(f"Query base de conocimiento: {pregunta}")

        try:
            # Verificar si Supabase está configurado
            if not self._supabase_client:
                return "La base de conocimiento no está configurada. Por favor, contacta con nuestro servicio al cliente para obtener información."

            # Crear embedding de la pregunta
            query_embedding = await self._openai_client.embeddings.create(
                input=[pregunta],
                model=self._embeddings_model,
                dimensions=self._embeddings_dimension,
            )

            embeddings = query_embedding.data[0].embedding

            # Buscar en Supabase usando búsqueda vectorial con la función match_documents
            results = self._supabase_client.rpc(
                'match_documents',
                {
                    'query_embedding': embeddings,
                    'match_count': K_TOP,
                    'filter': {}
                }
            ).execute()
            
            if results.data and len(results.data) > 0:
                # Formatear salida
                salida = ""
                for i, r in enumerate(results.data, start=1):
                    content = r.get("content", "").replace("\r\n", "\n").strip()
                    similarity = r.get("similarity", 0)
                    salida += (
                        f"{i}. **referencia {i} - Inicio**\n"
                        f"id: {r.get('id', 'N/A')}\n"
                        f"similarity: {similarity:.4f}\n"
                        f"content: {content}\n"
                        f"**fin de referencia {i}**\n\n"
                    )
                return salida
            else:
                logger.info("[Supabase] No se encontraron resultados relevantes con búsqueda vectorial.")
                return "No encontré información específica sobre tu consulta. Te recomiendo contactar directamente con nuestro servicio al cliente para obtener una respuesta más precisa."
                
        except Exception as e:
            logger.error(f"Error en buscar_en_base_de_conocimiento: {e}")
            return f"Lo siento, estoy teniendo problemas para consultar la información. Por favor, intenta de nuevo o contacta con nuestro servicio al cliente."
    @function_tool()
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call or when the conversation is complete"""
        #logger.info(f"[TOOL] end_call iniciada - participante: {self.participant.identity if self.participant else 'None'}")
        #logger.info(f"[TOOL] end_call - contexto: {ctx}")

        # Inform the user that the call is ending
        logger.info(f"[TOOL] end_call - generando mensaje de despedida")
        await ctx.session.generate_reply(
            instructions="Gracias por tu tiempo. Ha sido un placer ayudarte. La llamada está terminando."

        )

        # let the agent finish speaking
        current_speech = ctx.session.current_speech
        if current_speech:
            logger.info(f"[TOOL] end_call - esperando que termine el speech actual")
            await current_speech.wait_for_playout()

        logger.info(f"[TOOL] end_call - colgando llamada")
        await self.hangup()
        logger.info(f"[TOOL] end_call - llamada terminada exitosamente")
        return "llamada terminada exitosamente"

    async def hangup(self):
        """Helper function to hang up the call by deleting the room"""

        job_ctx = get_job_context()
        if job_ctx is None:
            # Not running in a job context
            return
        
        try:
            await job_ctx.api.room.delete_room(
                api.DeleteRoomRequest(
                    room=job_ctx.room.name,
                )
            )
            logger.info("Room deleted successfully")
        except Exception as e:
            logger.error(f"Error deleting room: {e}")
            # Continue anyway to avoid hanging

async def entrypoint(ctx: agents.JobContext):
    try:

        print("## Iniciando agente de voz...")
        
        # Verificar API keys antes de continuar
        openai_key = os.getenv("OPENAI_API_KEY")
        deepgram_key = os.getenv("DEEPGRAM_API_KEY")
        
        if not openai_key:
            raise ValueError("OPENAI_API_KEY no está configurado")
        if not deepgram_key:
            raise ValueError("DEEPGRAM_API_KEY no está configurado")
        
        mcp_servers = []
        if mcp_server_url and mcp_token:            
            print(f"## Configurando servidor MCP: {mcp_server_url}")
            mcp_servers.append(
                mcp.MCPServerHTTP(
                    url=mcp_server_url,
                    headers={"token": f"{mcp_token}"},
                    timeout=mcp_timeout,
                    client_session_timeout_seconds=mcp_session_timeout,
                )
            )
        else:
            print("###  Servidor MCP no configurado, funcionando sin herramientas MCP")
            
        print("## Configurando sesión del agente...")
        session = AgentSession(
            stt=deepgram.STT(model="nova-2", language="es"),  # Modelo más ligero
            llm="openai/gpt-4o-mini",  # Modelo más estable
            tts="cartesia/sonic-2:5c5ad5e7-1020-476b-8b91-fdcbe9cc313c",
            vad=silero.VAD.load(),
            turn_detection=MultilingualModel(),
            mcp_servers=mcp_servers,
        )
        """
        session = AgentSession(
            # LLM y STT sin cambios
            llm=openai.LLM(
                model="gpt-4.1-mini",
                timeout=60
            ),
            stt=deepgram.STT(model="nova-3", language="es"),

            # TTS con ElevenLabs (usar voz por defecto del SDK para evitar IDs inválidos)
            # Para instalar el plugin de eleven labs ejecutar: "uv add livekit-plugins-elevenlabs"  y el otro comando "uv add elevenlabs"
            tts=elevenlabs.TTS(
                model="eleven_turbo_v2_5",
                voice_id="b2htR0pMe28pYwCY9gnP",
                language="es"
            ),

            # VAD hiper-sensible
            vad=silero.VAD.load(
                min_silence_duration=0.25, # Mantenemos esto bajo para que el agente responda rápido
                min_speech_duration=0.1,   # Detecta incluso los fragmentos de habla más cortos
                activation_threshold=0.25, # Umbral muy bajo para detectar la voz del usuario al instante
                prefix_padding_duration=0.1,
                max_buffered_speech=60.0,
                force_cpu=True
            ),

            # Habilitar el modelo de detección de turnos sigue siendo crucial
            turn_detection=MultilingualModel(),

            # LA CLAVE: HABILITAR GENERACIÓN PREEMPTIVA
            preemptive_generation=True,

            # Endpointing se mantiene
            min_endpointing_delay=0.2,
            max_endpointing_delay=3.0,

            # Interrupciones hiper-reactivas
            allow_interruptions=True,
            discard_audio_if_uninterruptible=True,
            min_interruption_duration=0.15,  # Detecta interrupciones casi instantáneamente
            min_interruption_words=1,        # Una sola palabra es suficiente para interrumpir
            min_consecutive_speech_delay=0.1, # Mínima pausa entre turnos

            # El resto se mantiene igual
            max_tool_steps=3,
            mcp_servers=mcp_servers
        )"""

        print("## Iniciando sesión...")
        await session.start(
            room=ctx.room,
            agent=Assistant(),
            room_input_options=RoomInputOptions(
                # For telephony applications, use `BVCTelephony` instead for best results
                noise_cancellation=noise_cancellation.BVC(), 
            ),
        )

        print("## Generando saludo inicial...")
        await session.generate_reply(
            instructions="Saluda al usuario y ofrécele tu ayuda."
        )
        
    except Exception as e:
        print(f"## Error al inicializar el agente: {e}")
        print("## Sugerencias:")
        print("   - Verifica que OPENAI_API_KEY esté configurado correctamente")
        print("   - Verifica que DEEPGRAM_API_KEY esté configurado correctamente")
        print("   - Asegúrate de tener conexión a internet")
        print("   - Verifica que las API keys sean válidas y tengan créditos")
        raise

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint, 
        initialize_process_timeout=120,
        agent_name="autofuturo-ia",
    ))