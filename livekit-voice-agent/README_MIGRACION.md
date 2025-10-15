# Migración del Agente de Voz - AutoFuturo IA

## Resumen de Cambios

Este documento describe los pasos principales para migrar del agente anterior (`agent2.py`) al nuevo agente (`agent.py`) con funcionalidades mejoradas.

## 1. Actualizar Imports y Dependencias

### Agregar nuevos imports:
```python
import logging
from livekit.agents import function_tool
from livekit.agents.voice import RunContext
from supabase import create_client, Client
from openai import AsyncOpenAI
```

### Actualizar pyproject.toml:
```toml
dependencies = [
    "supabase>=2.0.0",
    "openai>=1.0.0",
]
```

## 2. Agregar Variables de Entorno

### Nuevas variables para Supabase:
```bash
# Variables para Supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu_supabase_anon_key_aqui
SUPABASE_TABLE=documents

# Configuración de embeddings
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
K_TOP=3
```

## 3. Actualizar Configuración de Modelos

### Cambiar modelos en AgentSession:
```python
session = AgentSession(
    stt=deepgram.STT(model="nova-2", language="es"),  # Cambio: nova-3 → nova-2
    llm="openai/gpt-4o-mini",  # Cambio: gpt-4.1-mini → gpt-4o-mini
    tts="elevenlabs/eleven_turbo_v2_5",  # Cambio: cartesia → elevenlabs
    vad=silero.VAD.load(),
    turn_detection=MultilingualModel(),
    mcp_servers=mcp_servers,
)
```

## 4. Agregar Inicialización de Clientes

### En la clase Assistant, agregar inicialización:
```python
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
            
        super().__init__(instructions="""...""")
```

## 5. Implementar Función de Búsqueda Vectorial

### Agregar función tool para Supabase:
```python
@function_tool()
async def buscar_en_base_de_conocimiento(self, pregunta: str, ctx: RunContext) -> str:
    """
    Usa siempre esta herramienta para obtener información de la base de conocimiento.
    """
    try:
        # Verificar si Supabase está configurado
        if not self._supabase_client:
            return "La base de conocimiento no está configurada."

        # Crear embedding de la pregunta
        query_embedding = await self._openai_client.embeddings.create(
            input=[pregunta],
            model=self._embeddings_model,
            dimensions=self._embeddings_dimension,
        )

        embeddings = query_embedding.data[0].embedding

        # Buscar en Supabase usando búsqueda vectorial
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
            return "No encontré información específica sobre tu consulta."
            
    except Exception as e:
        return f"Lo siento, estoy teniendo problemas para consultar la información."
```

## 6. Configurar Supabase

### Crear tabla en Supabase:
```sql
-- Enable the pgvector extension
create extension vector;

-- Create a table to store your documents
create table documents (
  id bigserial primary key,
  content text,
  metadata jsonb,
  embedding vector(1536)
);

-- Create a function to search for documents
create function match_documents (
  query_embedding vector(1536),
  match_count int default null,
  filter jsonb DEFAULT '{}'
) returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
#variable_conflict use_column
begin
  return query
  select
    id,
    content,
    metadata,
    1 - (documents.embedding <=> query_embedding) as similarity
  from documents
  where metadata @> filter
  order by documents.embedding <=> query_embedding
  limit match_count;
end;
$$;
```

## 7. Actualizar Timeout de Inicialización

### Cambiar en la función main:
```python
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint, 
        initialize_process_timeout=60  # Agregar timeout de 60 segundos
    ))
```

## 8. Insertar Documentos en Supabase

### Script para insertar documentos con embeddings:
```python
import openai
from supabase import create_client

# Configurar clientes
openai_client = openai.OpenAI(api_key="tu_openai_key")
supabase = create_client("tu_supabase_url", "tu_supabase_key")

def create_embedding(text):
    response = openai_client.embeddings.create(
        input=[text],
        model="text-embedding-3-small",
        dimensions=1536
    )
    return response.data[0].embedding

def insert_document(content, metadata=None):
    embedding = create_embedding(content)
    supabase.table('documents').insert({
        'content': content,
        'metadata': metadata or {},
        'embedding': embedding
    }).execute()

# Insertar documentos de ejemplo
documents = [
    {
        'content': 'AutoFuturo IA está ubicada en Av. Principal 123, Centro Comercial Plaza Mayor, Lima, Perú...',
        'metadata': {'category': 'ubicacion', 'source': 'manual.pdf'}
    },
    {
        'content': 'Ofrecemos financiamiento vehicular con tasas competitivas del 8.5% anual...',
        'metadata': {'category': 'financiamiento', 'source': 'manual.pdf'}
    }
]

for doc in documents:
    insert_document(doc['content'], doc['metadata'])
```

## Resumen de Cambios Principales

1. **Nuevas dependencias**: Supabase y OpenAI
2. **Variables de entorno**: Configuración para Supabase
3. **Modelos actualizados**: Modelos más estables y confiables
4. **Búsqueda vectorial**: Función tool para consultar base de conocimiento
5. **Configuración Supabase**: Tabla y función RPC para búsqueda vectorial
6. **Timeout aumentado**: Para evitar errores de inicialización

## Resultado Final

El nuevo agente incluye:
- ✅ Búsqueda vectorial con Supabase
- ✅ Modelos más estables
- ✅ Mejor manejo de errores
- ✅ Funcionalidad de base de conocimiento
- ✅ Configuración robusta

El agente mantiene toda la funcionalidad anterior del MCP server pero ahora también tiene capacidades de búsqueda vectorial local.

