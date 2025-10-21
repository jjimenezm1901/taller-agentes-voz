# Migración para Soporte de Llamadas Salientes

Este documento detalla todos los cambios realizados en el archivo `agent.py` para agregar soporte completo para llamadas salientes, siguiendo el patrón implementado en `entrypoint.py` + `agent_datapath.py`.

## Resumen de Cambios

El agente ahora puede manejar tanto llamadas **entrantes** como **salientes**, detectando automáticamente el tipo de llamada mediante metadata del job y adaptando su comportamiento en consecuencia.

## Cambios Detallados

### 1. Importaciones Agregadas

```python
import json
import re
from datetime import datetime
```

**Propósito**: Necesarias para el parsing de metadata de llamadas salientes y manejo de fechas.

### 2. Variables de Entorno para Llamadas Salientes

```python
# Variables de entorno para llamadas salientes
outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
transfer_to_number = os.getenv("TRANSFER_TO")
```

**Propósito**: Configuración necesaria para crear participantes SIP en llamadas salientes y manejar transferencias.

### 3. Modificación de la Clase Assistant

#### 3.1 Constructor Actualizado

**Antes:**
```python
def __init__(self) -> None:
```

**Después:**
```python
def __init__(self, *, name: str = None, appointment_time: str = None, dial_info: dict = None, is_outbound: bool = False) -> None:
```

**Propósito**: Permite configurar el agente con parámetros específicos para llamadas salientes.

#### 3.2 Propiedades Agregadas

```python
# Configuración para llamadas salientes
self.participant: rtc.RemoteParticipant | None = None
self.dial_info = dial_info
self.is_outbound = is_outbound
self.name = name
self.appointment_time = appointment_time
```

**Propósito**: Almacenar información específica de la llamada para personalizar el comportamiento del agente.

#### 3.3 Instrucciones Dinámicas

**Cambio Principal**: Las instrucciones del agente ahora se generan dinámicamente basándose en el tipo de llamada.

**Para Llamadas Salientes:**
- Saludo personalizado con nombre del cliente
- Enfoque en confirmar citas programadas
- Comportamiento específico para recordatorios

**Para Llamadas Entrantes:**
- Mantiene el comportamiento original
- Enfoque en agendar nuevas citas

#### 3.4 Métodos Agregados

```python
def set_participant(self, participant: rtc.RemoteParticipant):
    """Configurar el participante para transferencias"""
    self.participant = participant

async def generate_initial_greeting(self, session):
    """Generar saludo inicial para llamadas entrantes"""
    # Implementación del saludo inicial
```

**Propósito**: Manejo de participantes y saludos específicos para cada tipo de llamada.

### 4. Reescritura Completa de la Función entrypoint

#### 4.1 Detección de Tipo de Llamada

```python
# Check if this is an outbound call by looking for metadata
is_outbound = False
dial_info = None
agent_name = "Alex"
appointment_time = None

if ctx.job.metadata:
    # Parsing de metadata para detectar llamadas salientes
    # Soporte para formato JSON y formato CLI
```

**Propósito**: Detecta automáticamente si es una llamada saliente mediante metadata del job.

#### 4.2 Lógica para Llamadas Salientes

```python
if is_outbound:
    # Outbound call logic
    phone_number = dial_info["phone_number"]
    participant_identity = phone_number
    
    # Crear agente con parámetros específicos
    agent = Assistant(
        name=agent_name,
        appointment_time=appointment_time,
        dial_info=dial_info,
        is_outbound=True,
    )
    
    # Crear participante SIP
    await ctx.api.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            room_name=ctx.room.name,
            sip_trunk_id=outbound_trunk_id,
            sip_call_to=phone_number,
            participant_identity=participant_identity,
            wait_until_answered=True,
        )
    )
```

**Propósito**: Maneja completamente el flujo de llamadas salientes, incluyendo la creación del participante SIP.

#### 4.3 Lógica para Llamadas Entrantes

```python
else:
    # Inbound call logic
    dial_info = {"transfer_to": transfer_to_number} if transfer_to_number else {}
    
    agent = Assistant(
        is_outbound=False,
        dial_info=dial_info,
    )
    
    # Generar saludo inicial
    await agent.generate_initial_greeting(session)
```

**Propósito**: Mantiene el comportamiento original para llamadas entrantes.

### 5. Configuración de Sesión Unificada

Ambos tipos de llamada usan la misma configuración de `AgentSession` pero con diferentes opciones de cancelación de ruido:

- **Llamadas Salientes**: `noise_cancellation.BVCTelephony()`
- **Llamadas Entrantes**: `noise_cancellation.BVC()`

### 6. Manejo de Errores Mejorado

```python
except api.TwirpError as e:
    logger.error(f"[ENTRYPOINT] error creating SIP participant: {e.message}")
    logger.error(f"[ENTRYPOINT] SIP status: {e.metadata.get('sip_status_code')} {e.metadata.get('sip_status')}")
    ctx.shutdown()
```

**Propósito**: Manejo específico de errores SIP para llamadas salientes.

## Variables de Entorno Requeridas

Para que el sistema funcione correctamente, asegúrate de tener configuradas estas variables:

```bash
# Variables existentes
OPENAI_API_KEY=tu_api_key
DEEPGRAM_API_KEY=tu_api_key
MCP_SERVER=tu_servidor_mcp
MCP_TOKEN=tu_token_mcp

# Variables nuevas para llamadas salientes
SIP_OUTBOUND_TRUNK_ID=tu_trunk_id
TRANSFER_TO=numero_para_transferir
```

## Formato de Metadata para Llamadas Salientes

El sistema acepta metadata en dos formatos:

### Formato JSON:
```json
{"phone_number": "+51948588436", "name": "Juan Pérez", "appointment_time": "next Tuesday at 3pm"}
```

### Formato CLI:
```
{phone_number: +51948588436, name: Juan Pérez, appointment_time: next Tuesday at 3pm}
```

## Comportamiento del Agente

### Llamadas Salientes
- **Saludo**: "Hola [Nombre], te habla Alex de AutoFuturo IA. Te llamo para confirmar tu cita programada para [fecha]."
- **Objetivo**: Confirmar citas, resolver dudas, reagendar si es necesario
- **Herramientas**: Usa las mismas herramientas pero con enfoque en confirmación

### Llamadas Entrantes
- **Saludo**: "Hola, te atiende Alex de la concesionaria AutoFuturo IA. ¿En qué puedo ayudarte hoy?"
- **Objetivo**: Agendar nuevas citas, captar leads
- **Herramientas**: Enfoque en agendamiento y captura de datos

## Logging Mejorado

Se agregó logging detallado para facilitar el debugging:

```python
logger.info(f"[ENTRYPOINT] Llamada saliente detectada - phone: {dial_info['phone_number']}, name: {agent_name}")
logger.info(f"[ENTRYPOINT] Participante SIP creado exitosamente")
logger.info(f"[ENTRYPOINT] Agente configurado para manejar saludo automáticamente")
```

## Compatibilidad

- ✅ **Llamadas Entrantes**: Funciona exactamente igual que antes
- ✅ **Llamadas Salientes**: Nueva funcionalidad completa
- ✅ **MCP**: Compatible con servidores MCP existentes
- ✅ **Herramientas**: Todas las herramientas existentes funcionan en ambos modos

## Pruebas Recomendadas

1. **Llamada Entrante**: Verificar que el saludo inicial funciona correctamente
2. **Llamada Saliente**: Probar con metadata válida
3. **Transferencias**: Verificar que las transferencias funcionan en ambos modos
4. **MCP**: Confirmar que las herramientas MCP funcionan en ambos modos
5. **Errores SIP**: Probar manejo de errores con trunk inválido

## Conclusión

El agente ahora es completamente bidireccional, manteniendo toda la funcionalidad existente para llamadas entrantes mientras agrega soporte completo para llamadas salientes. La implementación sigue las mejores prácticas establecidas en el sistema de referencia y mantiene la compatibilidad total con la configuración existente.
