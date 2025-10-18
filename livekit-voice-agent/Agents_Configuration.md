# Configuración de Modelos en AgentSession - LiveKit Agents

Este documento detalla los parámetros de configuración de todos los modelos utilizados dentro de `AgentSession` en el proyecto de agente de voz en tiempo real. La información se basa en la documentación oficial de LiveKit Agents y las mejores prácticas implementadas.

## Tabla de Contenidos

1. [Configuración General de AgentSession](#configuración-general-de-agentsession)
2. [Modelo de Lenguaje (LLM)](#modelo-de-lenguaje-llm)
3. [Reconocimiento de Voz (STT)](#reconocimiento-de-voz-stt)
4. [Síntesis de Voz (TTS)](#síntesis-de-voz-tts)
5. [Detección de Actividad de Voz (VAD)](#detección-de-actividad-de-voz-vad)
6. [Detección de Turnos](#detección-de-turnos)
7. [Configuración de Interrupciones](#configuración-de-interrupciones)
8. [Configuración de Endpointing](#configuración-de-endpointing)
9. [Herramientas y MCP](#herramientas-y-mcp)
10. [Configuración de Audio de Fondo](#configuración-de-audio-de-fondo)

---

## Configuración General de AgentSession

`AgentSession` es la clase principal que coordina todos los componentes del agente de voz.

### Parámetros Principales

| Parámetro | Tipo | Descripción | Valor Actual |
|-----------|------|-------------|--------------|
| `llm` | `openai.LLM` | Modelo de lenguaje para procesamiento de texto | `openai.LLM(...)` |
| `stt` | `deepgram.STT` | Modelo de reconocimiento de voz | `deepgram.STT(...)` |
| `tts` | `elevenlabs.TTS` | Modelo de síntesis de voz | `elevenlabs.TTS(...)` |
| `vad` | `silero.VAD` | Detector de actividad de voz | `silero.VAD.load(...)` |
| `turn_detection` | `MultilingualModel` | Modelo de detección de turnos | `MultilingualModel()` |
| `preemptive_generation` | `bool` | Habilita generación preemptiva | `True` |
| `allow_interruptions` | `bool` | Permite interrupciones del usuario | `True` |
| `max_tool_steps` | `int` | Máximo número de pasos de herramientas | `3` |
| `mcp_servers` | `list` | Lista de servidores MCP | `mcp_servers` |

---

## Modelo de Lenguaje (LLM)

### OpenAI LLM

```python
llm=openai.LLM(
    model="gpt-4.1-mini",
    timeout=60
)
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `model` | `str` | Modelo de OpenAI a utilizar | `"gpt-4.1-mini"` | `"gpt-4o"`, `"gpt-4o-mini"`, `"gpt-3.5-turbo"` |
| `timeout` | `int` | Timeout en segundos para las solicitudes | `60` | `1-300` |
| `temperature` | `float` | Controla la aleatoriedad (comentado) | `0.4` (comentado) | `0.0-2.0` |
| `max_tokens` | `int` | Máximo número de tokens en respuesta | Por defecto | `1-4096` |

#### Notas
- `temperature=0.4` está comentado en llamadas entrantes
- El timeout de 60 segundos es apropiado para respuestas complejas
- `gpt-4.1-mini` es una versión optimizada para velocidad y costo

---

## Reconocimiento de Voz (STT)

### Deepgram STT

```python
stt=deepgram.STT(model="nova-3", language="es")
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `model` | `str` | Modelo de Deepgram | `"nova-3"` | `"nova-2"`, `"nova-3"`, `"base"` |
| `language` | `str` | Código de idioma | `"es"` | `"es"`, `"en-US"`, `"en-GB"` |
| `interim_results` | `bool` | Resultados intermedios | `True` (por defecto) | `True/False` |
| `punctuate` | `bool` | Agregar puntuación | `True` (por defecto) | `True/False` |
| `smart_format` | `bool` | Formato inteligente | `False` (por defecto) | `True/False` |
| `sample_rate` | `int` | Frecuencia de muestreo | `16000` (por defecto) | `8000`, `16000`, `44100` |
| `endpointing_ms` | `int` | Tiempo de silencio para fin de habla | `25` (por defecto) | `0-10000` |
| `enable_diarization` | `bool` | Identificación de hablantes | `False` (por defecto) | `True/False` |
| `filler_words` | `bool` | Incluir palabras de relleno | `True` (por defecto) | `True/False` |

#### Notas
- `nova-3` es el modelo más avanzado de Deepgram
- `language="es"` optimiza para español
- `interim_results=True` permite transcripción en tiempo real
- `enable_diarization=False` evita conflictos con versiones de `livekit-agents`

---

## Síntesis de Voz (TTS)

### ElevenLabs TTS

```python
tts=elevenlabs.TTS(
    model="eleven_turbo_v2_5",
    voice_id="b2htR0pMe28pYwCY9gnP",
    language="es"
)
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `model` | `str` | Modelo de ElevenLabs | `"eleven_turbo_v2_5"` | `"eleven_turbo_v2_5"`, `"eleven_multilingual_v2"` |
| `voice_id` | `str` | ID de la voz | `"b2htR0pMe28pYwCY9gnP"` | IDs válidos de ElevenLabs |
| `language` | `str` | Código de idioma | `"es"` | `"es"`, `"en"`, `"fr"`, `"de"` |
| `encoding` | `str` | Formato de audio | `"mp3_22050_32"` (por defecto) | `"mp3_22050_32"`, `"pcm_16000"` |
| `streaming_latency` | `int` | Optimización de latencia | `0` (por defecto) | `0-4` |
| `inactivity_timeout` | `int` | Timeout de inactividad | `300` (por defecto) | `60-600` |
| `auto_mode` | `bool` | Modo automático | `False` (por defecto) | `True/False` |
| `sync_alignment` | `bool` | Sincronización de alineación | `True` (por defecto) | `True/False` |

#### Notas
- `eleven_turbo_v2_5` es el modelo más rápido de ElevenLabs
- `voice_id` debe ser válido para evitar errores `voice_id_does_not_exist`
- `language="es"` optimiza la pronunciación en español
- `sync_alignment=True` mejora la sincronización de labios

---

## Detección de Actividad de Voz (VAD)

### Silero VAD

```python
vad=silero.VAD.load(
    min_silence_duration=0.25,
    min_speech_duration=0.1,
    activation_threshold=0.25,
    prefix_padding_duration=0.1,
    max_buffered_speech=60.0,
    force_cpu=True
)
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `min_silence_duration` | `float` | Duración mínima de silencio (s) | `0.25` | `0.1-2.0` |
| `min_speech_duration` | `float` | Duración mínima de habla (s) | `0.1` | `0.05-1.0` |
| `activation_threshold` | `float` | Umbral de activación | `0.25` | `0.1-0.9` |
| `prefix_padding_duration` | `float` | Padding antes del habla (s) | `0.1` | `0.0-0.5` |
| `max_buffered_speech` | `float` | Máximo audio bufferizado (s) | `60.0` | `10.0-300.0` |
| `force_cpu` | `bool` | Forzar uso de CPU | `True` | `True/False` |

#### Notas
- Configuración "hiper-sensible" para respuesta rápida
- `activation_threshold=0.25` es muy bajo para detectar voz instantáneamente
- `min_speech_duration=0.1` detecta fragmentos muy cortos
- `force_cpu=True` evita problemas de GPU

---

## Detección de Turnos

### MultilingualModel

```python
turn_detection=MultilingualModel()
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| Constructor | Sin parámetros | Modelo multilingüe por defecto | `MultilingualModel()` | N/A |

#### Notas
- Modelo preentrenado para múltiples idiomas
- Detecta automáticamente cuándo el usuario termina de hablar
- Esencial para conversaciones fluidas
- No requiere configuración adicional

---

## Configuración de Interrupciones

### Parámetros de Interrupciones

```python
allow_interruptions=True,
discard_audio_if_uninterruptible=True,
min_interruption_duration=0.15,
min_interruption_words=1,
min_consecutive_speech_delay=0.1
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `allow_interruptions` | `bool` | Permite interrupciones | `True` | `True/False` |
| `discard_audio_if_uninterruptible` | `bool` | Descarta audio no interrumpible | `True` | `True/False` |
| `min_interruption_duration` | `float` | Duración mínima de interrupción (s) | `0.15` | `0.1-1.0` |
| `min_interruption_words` | `int` | Palabras mínimas para interrumpir | `1` | `1-5` |
| `min_consecutive_speech_delay` | `float` | Pausa mínima entre turnos (s) | `0.1` | `0.05-0.5` |

#### Notas
- Configuración "hiper-reactiva" para interrupciones fluidas
- `min_interruption_duration=0.15` detecta interrupciones casi instantáneamente
- `min_interruption_words=1` permite interrumpir con una sola palabra
- `discard_audio_if_uninterruptible=True` evita audio residual

---

## Configuración de Endpointing

### Parámetros de Endpointing

```python
min_endpointing_delay=0.2,
max_endpointing_delay=3.0
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `min_endpointing_delay` | `float` | Retraso mínimo de endpointing (s) | `0.2` | `0.1-1.0` |
| `max_endpointing_delay` | `float` | Retraso máximo de endpointing (s) | `3.0` | `1.0-10.0` |

#### Notas
- `min_endpointing_delay=0.2` permite respuestas rápidas
- `max_endpointing_delay=3.0` evita esperas excesivas
- Balance entre velocidad y precisión

---

## Herramientas y MCP

### Configuración MCP

```python
max_tool_steps=3,
mcp_servers=mcp_servers
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `max_tool_steps` | `int` | Máximo pasos de herramientas | `3` | `1-10` |
| `mcp_servers` | `list` | Lista de servidores MCP | Variable | Lista de `MCPServerHTTP` |

#### Configuración MCP Server

```python
mcp.MCPServerHTTP(
    url=mcp_server_url,
    headers={"token": f"{mcp_token}"},
    timeout=mcp_timeout,
    client_session_timeout_seconds=mcp_session_timeout,
)
```

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `url` | `str` | URL del servidor MCP | Variable | URL válida |
| `headers` | `dict` | Headers de autenticación | `{"token": "..."}` | Dict con token |
| `timeout` | `int` | Timeout de conexión (s) | `10` | `5-60` |
| `client_session_timeout_seconds` | `int` | Timeout de sesión (s) | `30` | `10-300` |

#### Notas
- `max_tool_steps=3` limita la recursión de herramientas
- MCP servers permiten integración con servicios externos
- Timeouts configurables para diferentes entornos

---

## Configuración de Audio de Fondo

### BackgroundAudioPlayer

```python
background_audio = BackgroundAudioPlayer(
    ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
    thinking_sound=[
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
    ],
)
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `ambient_sound` | `AudioConfig` | Sonido ambiente | `OFFICE_AMBIENCE` | `OFFICE_AMBIENCE`, `CAFE_AMBIENCE` |
| `thinking_sound` | `list[AudioConfig]` | Sonidos de pensamiento | `[KEYBOARD_TYPING, KEYBOARD_TYPING2]` | Lista de clips |
| `volume` | `float` | Volumen del audio | `0.8`, `0.7` | `0.0-1.0` |

#### AudioConfig

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `clip` | `BuiltinAudioClip` | Clip de audio | `OFFICE_AMBIENCE` | Clips predefinidos |
| `volume` | `float` | Volumen | `0.8` | `0.0-1.0` |

#### Notas
- `OFFICE_AMBIENCE` crea ambiente de oficina
- `KEYBOARD_TYPING` simula escritura durante procesamiento
- Volúmenes balanceados para no interferir con la conversación

---

## Configuración de Cancelación de Ruido

### RoomInputOptions

```python
room_input_options=RoomInputOptions(
    noise_cancellation=noise_cancellation.BVCTelephony()  # Para salientes
    # o
    noise_cancellation=noise_cancellation.BVC()  # Para entrantes
)
```

#### Parámetros

| Parámetro | Tipo | Descripción | Valor Actual | Rango/Valores |
|-----------|------|-------------|--------------|---------------|
| `noise_cancellation` | `BVC`/`BVCTelephony` | Cancelación de ruido | `BVCTelephony()`/`BVC()` | `BVC()`, `BVCTelephony()` |

#### Notas
- `BVCTelephony()` optimizado para telefonía (llamadas salientes)
- `BVC()` para llamadas entrantes generales
- Mejora la calidad del audio en entornos ruidosos

---

## Variables de Entorno Requeridas

### API Keys

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Clave API de OpenAI | `sk-...` |
| `DEEPGRAM_API_KEY` | Clave API de Deepgram | `...` |
| `ELEVEN_API_KEY` | Clave API de ElevenLabs | `...` |
| `LIVEKIT_URL` | URL del servidor LiveKit | `wss://...` |
| `LIVEKIT_API_KEY` | Clave API de LiveKit | `...` |
| `LIVEKIT_API_SECRET` | Secreto API de LiveKit | `...` |

### Configuración SIP

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `SIP_OUTBOUND_TRUNK_ID` | ID del tronco SIP saliente | `trunk_123` |
| `TRANSFER_TO` | Número para transferencias | `+1234567890` |

### Configuración MCP

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `MCP_SERVER` | URL del servidor MCP | `https://...` |
| `MCP_TOKEN` | Token de autenticación MCP | `...` |
| `MCP_TIMEOUT` | Timeout MCP (s) | `10` |
| `MCP_SESSION_TIMEOUT` | Timeout de sesión MCP (s) | `30` |

---

## Mejores Prácticas

### Optimización de Latencia

1. **VAD Hiper-sensible**: Configuración de umbrales bajos para detección rápida
2. **Generación Preemptiva**: `preemptive_generation=True` para respuestas más rápidas
3. **Interrupciones Reactivas**: Configuración para interrupciones casi instantáneas
4. **TTS Optimizado**: Uso de `eleven_turbo_v2_5` para síntesis rápida

### Calidad de Audio

1. **Cancelación de Ruido**: Diferentes configuraciones para entrantes/salientes
2. **Audio de Fondo**: Ambiente y sonidos de feedback para mejor UX
3. **STT Avanzado**: `nova-3` para mejor precisión en español

### Robustez

1. **Timeouts Apropiados**: 60s para LLM, 10s para MCP
2. **Manejo de Errores**: Confirmaciones para transferencias/cortes
3. **Versiones Compatibles**: Alineación de dependencias para evitar conflictos

---

## Solución de Problemas

### Errores Comunes

1. **`voice_id_does_not_exist`**: Verificar que el `voice_id` sea válido en ElevenLabs
2. **`STTCapabilities.__init__() got an unexpected keyword argument 'diarization'`**: Alinear versiones de `livekit-agents` y `livekit-plugins-deepgram`
3. **`Session terminated`**: Verificar configuración MCP y conectividad
4. **Latencia alta**: Ajustar parámetros VAD y endpointing

### Debugging

1. **Logs Detallados**: Habilitar `logging.INFO` para seguimiento
2. **Monitoreo MCP**: Verificar conectividad y timeouts
3. **Pruebas de Audio**: Validar calidad de entrada/salida

---

## Referencias

- [LiveKit Agents Documentation](https://docs.livekit.io/agents/)
- [Deepgram API Documentation](https://developers.deepgram.com/)
- [ElevenLabs API Documentation](https://docs.elevenlabs.io/)
- [OpenAI API Documentation](https://platform.openai.com/docs)

---

**Última actualización**: Enero 2025  
**Versión del proyecto**: LiveKit Agents 1.2.3
