from dotenv import load_dotenv
import os
import logging
import json
import re
from datetime import datetime, timezone, timedelta
from livekit import agents, rtc, api
from livekit.agents import AgentSession, Agent, RoomInputOptions, mcp, function_tool, get_job_context
from livekit.agents.voice import RunContext
from livekit.plugins import noise_cancellation, silero, deepgram, elevenlabs
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

# Variables de entorno para llamadas salientes
outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
transfer_to_number = os.getenv("TRANSFER_TO")

# Variables de entorno para Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "documents")

# Configuración de embeddings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
K_TOP = int(os.getenv("K_TOP", "3"))

class Assistant(Agent):
    def __init__(self, *, name: str = None, appointment_time: str = None, dial_info: dict = None, is_outbound: bool = False) -> None:
        # Inicializar clientes para la base de conocimiento
        self._openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._embeddings_model = EMBEDDING_MODEL
        self._embeddings_dimension = EMBEDDING_DIMENSIONS
        
        # Inicializar cliente de Supabase
        if SUPABASE_URL and SUPABASE_KEY:
            self._supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        else:
            self._supabase_client = None
            
        # Configuración para llamadas salientes
        self.participant: rtc.RemoteParticipant | None = None
        self.dial_info = dial_info
        self.is_outbound = is_outbound
        self.name = name
        self.appointment_time = appointment_time
            
        # Construir instrucciones basadas en el tipo de llamada
        if is_outbound and name and appointment_time:
            instructions = f"""
                Hoy es {datetime.now(timezone(timedelta(hours=-5))).strftime('%A, %d de %B de %Y, %H:%M %p (UTC-5)')}.
                ## Rol y Objetivo Principal - LLAMADA SALIENTE
                Eres **Alex**, el asistente virtual de la concesionaria **AutoFuturo IA**. Estás realizando una llamada saliente a **{name}** para recordarle su cita programada para **{appointment_time}**. Tu objetivo es confirmar la cita, resolver cualquier duda y asegurar que el cliente asista.
                
                ## Comportamiento para Llamadas Salientes
                - **Saludo personalizado**: "Hola {name}, te habla Alex de AutoFuturo IA. Te llamo para confirmar tu cita programada para {appointment_time}."
                - **Confirmación de cita**: Verifica que el cliente recuerde y pueda asistir a su cita.
                - **Resolución de dudas**: Si tiene preguntas, usa las herramientas disponibles para responder.
                - **Reagendamiento**: Si no puede asistir, ofrece reagendar usando las herramientas de calendario.
                - **Mantén el enfoque**: Toda la conversación debe girar en torno a la cita confirmada.
            """
        else:
            instructions = f"""
                Hoy es {datetime.now(timezone(timedelta(hours=-5))).strftime('%A, %d de %B de %Y, %H:%M %p (UTC-5)')}.
                ## Rol y Objetivo Principal - LLAMADA ENTRANTE
                Eres **Alex**, el asistente virtual de la concesionaria **AutoFuturo IA**. Eres amable, profesional y muy eficiente. Tu **objetivo principal e irrenunciable** es despertar el interés del cliente en nuestros vehículos y **conseguir que agende una cita presencial** para una prueba de manejo o para recibir asesoría personalizada en nuestra sucursal. Toda la conversación debe dirigirse hacia ese fin.
            """

        super().__init__(
            instructions=instructions + """

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

    def set_participant(self, participant: rtc.RemoteParticipant):
        """Configurar el participante para transferencias"""
        self.participant = participant

    async def generate_initial_greeting(self, session):
        """Generar saludo inicial para llamadas entrantes"""
        logger.info(f"[AGENT] Generando saludo inicial para llamada entrante")
        await session.generate_reply(
            instructions="Saluda al usuario de manera amable y pregunta en qué puedes ayudarle. No pidas información personal inmediatamente."
        )
        logger.info(f"[AGENT] Saludo inicial generado exitosamente")
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
    async def transfer_call(self, transfer_to: str, reason: str, ctx: RunContext) -> str:
        """Call this tool if the user wants to speak to a human agent"""
        logger.info(f"[TOOL] transfer_call iniciada - transfer_to: {transfer_to}, reason: {reason}")
        logger.info(f"[TOOL] transfer_call - contexto: {ctx}")
        logger.info(f"[TOOL] transfer_call - participante: {self.participant}")
        
        if not self.participant:
            logger.error("[TOOL] transfer_call - Error: No hay participante configurado")
            return "Error: No hay participante configurado para transferir"

        if not transfer_to_number:
            logger.warning("[TOOL] transfer_call - No transfer number configured")
            await ctx.session.generate_reply(
                instructions="Lo siento, no puedo transferir la llamada en este momento. Por favor, contacta directamente con nuestro servicio al cliente."
            )
            return "Lo siento, no puedo transferir la llamada en este momento. Por favor, contacta directamente con nuestro servicio al cliente."

        logger.info(f"[TOOL] transfer_call - transfiriendo llamada a: {transfer_to_number}")
        
        # El agente ya maneja los mensajes de transferencia automáticamente según sus instrucciones
        logger.info(f"[TOOL] transfer_call - agente manejará mensaje de transferencia automáticamente")

        job_ctx = get_job_context()
        try:
            await job_ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=job_ctx.room.name,
                    participant_identity=self.participant.identity,
                    transfer_to=f"tel:{transfer_to_number}",
                )
            )
            
            logger.info(f"[TOOL] transfer_call - llamada transferida exitosamente a: {transfer_to_number}")
            return "transferencia completada exitosamente"
            
        except Exception as e:
            logger.error(f"[TOOL] transfer_call - error transferring call: {e}")
            logger.error(f"[TOOL] transfer_call - Traceback completo: ", exc_info=True)
            # El agente ya maneja los mensajes de error automáticamente según sus instrucciones
            logger.info(f"[TOOL] transfer_call - agente manejará mensaje de error automáticamente")
            return f"Lo siento, estoy teniendo problemas para transferir la llamada. Error: {str(e)}"

    @function_tool()
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call or when the conversation is complete"""
        logger.info(f"[TOOL] end_call iniciada - participante: {self.participant.identity if self.participant else 'None'}")

        # Inform the user that the call is ending
        logger.info(f"[TOOL] end_call - generando mensaje de despedida")
        await ctx.session.generate_reply(
            instructions="Gracias por tu tiempo. Ha sido un placer ayudarte. La llamada está terminando."
        )

        # let the agent finish speaking
        current_speech = ctx.session.current_speech
        if current_speech:
            logger.info(f"[TOOL] end_call - esperando que termine el speech actual")
            try:
                await current_speech.wait_for_playout()
            except Exception as e:
                logger.warning(f"[TOOL] end_call - error esperando speech: {e}")

        # Pequeña pausa para asegurar que el mensaje se complete
        import asyncio
        await asyncio.sleep(0.5)

        logger.info(f"[TOOL] end_call - colgando llamada")
        await self.hangup()
        logger.info(f"[TOOL] end_call - llamada terminada exitosamente")
        return "llamada terminada exitosamente"

    async def hangup(self):
        """Helper function to hang up the call by deleting the room"""

        job_ctx = get_job_context()
        if job_ctx is None:
            logger.warning("No job context available for hangup")
            return
        
        try:
            logger.info(f"[HANGUP] Eliminando room: {job_ctx.room.name}")
            await job_ctx.api.room.delete_room(
                api.DeleteRoomRequest(
                    room=job_ctx.room.name,
                )
            )
            logger.info("[HANGUP] Room eliminado exitosamente")
        except Exception as e:
            logger.error(f"[HANGUP] Error eliminando room: {e}")
            # Intentar shutdown como alternativa
            try:
                logger.info("[HANGUP] Intentando shutdown del contexto")
                job_ctx.shutdown()
            except Exception as shutdown_error:
                logger.error(f"[HANGUP] Error en shutdown: {shutdown_error}")
            # Continue anyway to avoid hanging

async def entrypoint(ctx: agents.JobContext):
    logger.info(f"[ENTRYPOINT] Iniciando entrypoint - room: {ctx.room.name}")
    logger.info(f"[ENTRYPOINT] Conectando a la sala")
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)
    logger.info(f"[ENTRYPOINT] Conexión exitosa a la sala")

    # Verificar API keys antes de continuar
    openai_key = os.getenv("OPENAI_API_KEY")
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    
    if not openai_key:
        raise ValueError("OPENAI_API_KEY no está configurado")
    if not deepgram_key:
        raise ValueError("DEEPGRAM_API_KEY no está configurado")

    # Check if this is an outbound call by looking for metadata
    is_outbound = False
    dial_info = None
    agent_name = "Alex"
    appointment_time = None

    if ctx.job.metadata:
        logger.info(f"[ENTRYPOINT] Metadata encontrada: {ctx.job.metadata}")
        try:
            # Intentar parsear como JSON válido primero
            try:
                dial_info = json.loads(ctx.job.metadata)
                logger.info(f"[ENTRYPOINT] Metadata parseada como JSON: {dial_info}")
            except json.JSONDecodeError:
                logger.info(f"[ENTRYPOINT] Falló parseo JSON, intentando formato CLI")
                # Si falla, intentar parsear el formato sin comillas del CLI
                metadata_str = ctx.job.metadata
                logger.info(f"[ENTRYPOINT] Metadata original: {metadata_str}")
                
                # Reemplazar claves sin comillas con claves con comillas
                metadata_str = re.sub(r'(\w+):', r'"\1":', metadata_str)
                
                # Manejar valores que pueden contener espacios y caracteres especiales
                # Buscar patrones como: "key": valor_sin_comillas y envolver el valor en comillas
                def quote_values(match):
                    key = match.group(1)
                    value = match.group(2).strip()
                    # Si el valor ya está entre comillas, no hacer nada
                    if value.startswith('"') and value.endswith('"'):
                        return match.group(0)
                    # Si el valor contiene espacios o caracteres especiales, envolver en comillas
                    return f'"{key}": "{value}"'
                
                metadata_str = re.sub(r'"(\w+)":\s*([^,}]+)', quote_values, metadata_str)
                logger.info(f"[ENTRYPOINT] Metadata procesada: {metadata_str}")
                
                try:
                    dial_info = json.loads(metadata_str)
                    logger.info(f"[ENTRYPOINT] Metadata parseada como CLI: {dial_info}")
                except json.JSONDecodeError as e:
                    logger.error(f"[ENTRYPOINT] Error parseando metadata CLI: {e}")
                    logger.error(f"[ENTRYPOINT] Metadata problemática: {metadata_str}")
                    # Intentar parseo manual como último recurso
                    dial_info = {}
                    # Buscar phone_number específicamente
                    phone_match = re.search(r'phone_number["\']?\s*:\s*["\']?([^,}]+)', metadata_str)
                    if phone_match:
                        dial_info["phone_number"] = phone_match.group(1).strip('"\'')
                        # Buscar otros campos
                        name_match = re.search(r'name["\']?\s*:\s*["\']?([^,}]+)', metadata_str)
                        if name_match:
                            dial_info["name"] = name_match.group(1).strip('"\'')
                        appointment_match = re.search(r'appointment_time["\']?\s*:\s*["\']?([^,}]+)', metadata_str)
                        if appointment_match:
                            dial_info["appointment_time"] = appointment_match.group(1).strip('"\'')
                    logger.info(f"[ENTRYPOINT] Parseo manual: {dial_info}")
            
            if dial_info and "phone_number" in dial_info:
                is_outbound = True
                agent_name = dial_info.get("name", "Alex")
                appointment_time = dial_info.get("appointment_time", "next Tuesday at 3pm")
                logger.info(f"[ENTRYPOINT] Llamada saliente detectada - phone: {dial_info['phone_number']}, name: {agent_name}")
        except Exception as e:
            logger.warning(f"[ENTRYPOINT] Could not parse metadata: {e}")

    # Configurar servidores MCP
    mcp_servers = []
    if mcp_server_url and mcp_token:
        logger.info(f"Configurando MCP server: {mcp_server_url}")
        logger.info(f"MCP timeout: {mcp_timeout}s, session timeout: {mcp_session_timeout}s")
        mcp_servers.append(
            mcp.MCPServerHTTP(
                url=mcp_server_url,
                headers={"token": f"{mcp_token}"},
                timeout=mcp_timeout,
                client_session_timeout_seconds=mcp_session_timeout,
            )
        )
    else:
        logger.warning("MCP server no configurado - funcionalidad limitada")

    if is_outbound:
        # Outbound call logic
        logger.info(f"[ENTRYPOINT] Iniciando lógica de llamada saliente")
        phone_number = dial_info["phone_number"]
        participant_identity = phone_number
        logger.info(f"[ENTRYPOINT] Número de teléfono: {phone_number}, identidad: {participant_identity}")

        # Create outbound agent
        logger.info(f"[ENTRYPOINT] Creando agente saliente")
        agent = Assistant(
            name=agent_name,
            appointment_time=appointment_time,
            dial_info=dial_info,
            is_outbound=True,
        )
        logger.info(f"[ENTRYPOINT] Agente saliente creado exitosamente")

        # Crear y configurar AgentSession para llamada saliente
        logger.info(f"[ENTRYPOINT] Creando sesión para llamada saliente")
        
        session = AgentSession(
            # LLM y STT
            llm="openai/gpt-4o-mini",
            stt=deepgram.STT(model="nova-2", language="es"),

            # TTS con ElevenLabs
            tts=elevenlabs.TTS(
                model="eleven_turbo_v2_5",
                voice_id="b2htR0pMe28pYwCY9gnP",
                language="es"
            ),

            # VAD hiper-sensible
            vad=silero.VAD.load(
                min_silence_duration=0.25,
                min_speech_duration=0.1,
                activation_threshold=0.25,
                prefix_padding_duration=0.1,
                max_buffered_speech=60.0,
                force_cpu=True
            ),

            # Habilitar el modelo de detección de turnos
            turn_detection=MultilingualModel(),

            # HABILITAR GENERACIÓN PREEMPTIVA
            preemptive_generation=True,

            # Endpointing
            min_endpointing_delay=0.2,
            max_endpointing_delay=3.0,

            # Interrupciones hiper-reactivas
            allow_interruptions=True,
            discard_audio_if_uninterruptible=True,
            min_interruption_duration=0.15,
            min_interruption_words=1,
            min_consecutive_speech_delay=0.1,

            # El resto se mantiene igual
            max_tool_steps=3,
            mcp_servers=mcp_servers
        )
        
        logger.info(f"[ENTRYPOINT] Sesión para llamada saliente creada exitosamente")

        # Start the session
        try:
            logger.info(f"[ENTRYPOINT] Iniciando sesión del agente")
            session_started = await session.start(
                agent=agent,
                room=ctx.room,
                room_input_options=RoomInputOptions(
                    # Cancelación de ruido optimizada para telefonía
                    noise_cancellation=noise_cancellation.BVCTelephony()
                )
            )
            logger.info(f"[ENTRYPOINT] Sesión iniciada exitosamente")

        except Exception as e:
            logger.error(f"[ENTRYPOINT] Error starting agent session: {e}")
            logger.error(f"[ENTRYPOINT] Traceback completo: ", exc_info=True)
            if "MCP" in str(e) or "mcp" in str(e):
                logger.error("Error de conexión MCP - verificando configuración del servidor")
            ctx.shutdown()
            return

        # Create SIP participant for outbound call
        try:
            logger.info(f"[ENTRYPOINT] Creando participante SIP para llamada saliente")
            logger.info(f"[ENTRYPOINT] Parámetros SIP - room: {ctx.room.name}, trunk: {outbound_trunk_id}, to: {phone_number}")
            
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=outbound_trunk_id,
                    sip_call_to=phone_number,
                    participant_identity=participant_identity,
                    wait_until_answered=True,
                )
            )
            logger.info(f"[ENTRYPOINT] Participante SIP creado exitosamente")

            # Wait for participant to join
            participant = await ctx.wait_for_participant(identity=participant_identity)
            logger.info(f"[ENTRYPOINT] Participante unido: {participant.identity}")

            agent.set_participant(participant)
            logger.info(f"[ENTRYPOINT] Participante configurado en el agente")

            # El agente manejará el saludo automáticamente según sus instrucciones
            logger.info(f"[ENTRYPOINT] Agente configurado para manejar saludo automáticamente")

        except api.TwirpError as e:
            logger.error(f"[ENTRYPOINT] error creating SIP participant: {e.message}")
            logger.error(f"[ENTRYPOINT] SIP status: {e.metadata.get('sip_status_code')} {e.metadata.get('sip_status')}")
            ctx.shutdown()
    else:
        # Inbound call logic
        logger.info(f"[ENTRYPOINT] Iniciando lógica de llamada entrante")
        
        # Add transfer configuration for inbound calls
        dial_info = {"transfer_to": transfer_to_number} if transfer_to_number else {}
        logger.info(f"[ENTRYPOINT] Configuración de transferencia para llamada entrante: {dial_info}")
        
        logger.info(f"[ENTRYPOINT] Creando agente para llamada entrante")
        agent = Assistant(
            is_outbound=False,
            dial_info=dial_info,
        )
        logger.info(f"[ENTRYPOINT] Agente para llamada entrante creado exitosamente")

        # Crear y configurar AgentSession para llamada entrante
        logger.info(f"[ENTRYPOINT] Creando sesión para llamada entrante")
        
        session = AgentSession(
            # LLM y STT
            llm="openai/gpt-4o-mini",
            stt=deepgram.STT(model="nova-2", language="es"),

            # TTS con Cartesia
            tts=elevenlabs.TTS(
                model="eleven_turbo_v2_5",
                voice_id="b2htR0pMe28pYwCY9gnP",
                language="es"
            ),

            # VAD hiper-sensible
            vad=silero.VAD.load(
                min_silence_duration=0.25,
                min_speech_duration=0.1,
                activation_threshold=0.25,
                prefix_padding_duration=0.1,
                max_buffered_speech=60.0,
                force_cpu=True
            ),

            # Habilitar el modelo de detección de turnos
            turn_detection=MultilingualModel(),

            # HABILITAR GENERACIÓN PREEMPTIVA
            preemptive_generation=True,

            # Endpointing
            min_endpointing_delay=0.2,
            max_endpointing_delay=3.0,

            # Interrupciones hiper-reactivas
            allow_interruptions=True,
            discard_audio_if_uninterruptible=True,
            min_interruption_duration=0.15,
            min_interruption_words=1,
            min_consecutive_speech_delay=0.1,

            # El resto se mantiene igual
            max_tool_steps=3,
            mcp_servers=mcp_servers
        )
        
        logger.info(f"[ENTRYPOINT] Sesión para llamada entrante creada exitosamente")

        # Start session
        try:
            logger.info(f"[ENTRYPOINT] Iniciando sesión para llamada entrante")
            await session.start(
                agent=agent,
                room=ctx.room,
                room_input_options=RoomInputOptions(
                    # Cancelación de ruido optimizada para llamadas entrantes
                    noise_cancellation=noise_cancellation.BVC()
                )
            )
            logger.info(f"[ENTRYPOINT] Sesión para llamada entrante iniciada exitosamente")
            
        except Exception as e:
            logger.error(f"[ENTRYPOINT] Error starting inbound agent session: {e}")
            logger.error(f"[ENTRYPOINT] Traceback completo: ", exc_info=True)
            if "MCP" in str(e) or "mcp" in str(e):
                logger.error("Error de conexión MCP en llamada entrante - verificando configuración del servidor")
            ctx.shutdown()
            return

        # Wait for participant to join and session to be ready
        logger.info(f"[ENTRYPOINT] Esperando que se una el participante")
        
        participant = await ctx.wait_for_participant()
        logger.info(f"[ENTRYPOINT] Participante unido: {participant.identity}")
        
        agent.set_participant(participant)
        logger.info(f"[ENTRYPOINT] Participante configurado en el agente")

        # Generar saludo inicial para llamadas entrantes usando el método del agente
        logger.info(f"[ENTRYPOINT] Llamando método de saludo del agente")
        await agent.generate_initial_greeting(session)
        logger.info(f"[ENTRYPOINT] Saludo inicial completado")
    
    logger.info(f"[ENTRYPOINT] Agente iniciado exitosamente - is_outbound: {is_outbound}")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint, 
        initialize_process_timeout=120,
        agent_name="autofuturo-ia",
    ))