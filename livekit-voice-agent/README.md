# Agente de Voz AutoFuturo IA — Guía de Migración y Telefonía Entrante (SIP)

## Objetivo
Pasos para evolucionar desde el agente anterior (`agent_old.py`/`agent2.py`) al agente actual (`agent.py`) con:
- Modelos optimizados para voz
- Base de conocimiento (Supabase + embeddings)
- Telefonía entrante (SIP) con LiveKit CLI
- Tools para controlar la llamada (colgar/terminar)

---

## 1) Preparación
- Mantén dependencias de LiveKit Agents, Deepgram, etc.
- Asegura variables existentes: `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`.
- Si usas LiveKit Cloud: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.

---

## 2) Modelos y UX de voz
- STT: `deepgram.STT(model="nova-2", language="es")` (menor latencia).
- LLM: `openai/gpt-4o-mini` (estable para barge-in).
- TTS: `elevenlabs/eleven_turbo_v2_5` (fluido en streaming).
- VAD/turn-taking: `silero.VAD.load()` + `MultilingualModel()`.

---

## 3) Prompt (rol del asistente)
- Mantén respuestas cortas y claras (voz).
- Reafirma objetivo: siempre llevar a agendar cita.
- “Frase conectora” antes de usar tools para evitar silencios.

---

## 4) Base de conocimiento con Supabase (vectorial)
- Nuevas variables de entorno:
  - `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_TABLE=documents`
  - `EMBEDDING_MODEL=text-embedding-3-small`, `EMBEDDING_DIMENSIONS=1536`, `K_TOP=3`
- Inicializaciones en `Assistant.__init__()`:
  - Cliente OpenAI async (embeddings)
  - Cliente Supabase (`create_client`)
- Tool: `buscar_en_base_de_conocimiento(pregunta)`
  - Crea embedding de la pregunta
  - Llama RPC `match_documents(query_embedding, match_count, filter)` en Supabase
  - Devuelve referencias con `id`, `similarity`, `content`

SQL de Supabase (resumen):
```sql
create extension vector;
create table documents (
  id bigserial primary key,
  content text,
  metadata jsonb,
  embedding vector(1536)
);
create function match_documents (
  query_embedding vector(1536),
  match_count int default null,
  filter jsonb default '{}'
) returns table (id bigint, content text, metadata jsonb, similarity float)
language plpgsql as $$
begin
  return query
  select id, content, metadata,
         1 - (documents.embedding <=> query_embedding) as similarity
  from documents
  where metadata @> filter
  order by documents.embedding <=> query_embedding
  limit match_count;
end;
$$;
```

---

## 5) Telefonía entrante (SIP)
1. Crea los archivos en `livekit-voice-agent/`:
   - `inbound-trunk.json`
   - `dispatch-rule.json`
2. Aplica con LiveKit CLI (desde `livekit-voice-agent/`):
```bash
lk sip inbound create inbound-trunk.json
lk sip dispatch create dispatch-rule.json
# Para actualizar una regla existente (reemplaza el ID):
lk sip dispatch update --id SDR_<ID_EXISTENTE> dispatch-rule.json
```
3. Ejecuta el agente:
```bash
uv run agent.py dev
```
- El worker se registra y recibirá jobs cuando la dispatch rule enrute llamadas entrantes a tu room.

---

## 6) Tools para control de llamada
- Expón tools invocables por el LLM para cerrar la llamada cuando corresponda:
  - `end_call()` / `hangup()` (terminar sesión/room al completar objetivo o por solicitud del usuario).
- Úsalas en flujos como: cita confirmada → despedida → `end_call`.

---

## 7) MCP (opcional) y fallback
- Si usas MCP, configura `MCP_SERVER`, `MCP_TOKEN`.
- Si MCP no está disponible, el agente continúa con STT/LLM/TTS + tool de Supabase.

---

## 8) Git/ramas (sugerido)
```bash
git checkout -b phone
git add .
git commit -m "add inbound"
git push origin phone
```

---

## 9) Checklist de migración
- Dependencias y variables de entorno actualizadas
- Prompt ajustado a voz/objetivo
- Tool de Supabase operativa (`match_documents`)
- Archivos `inbound-trunk.json` y `dispatch-rule.json` creados
- Reglas SIP aplicadas con LiveKit CLI
- Tools `end_call`/`hangup` disponibles para el LLM
- Agente corriendo y recibiendo llamadas: `uv run agent.py dev`

---

## Comandos útiles usados
```bash
# Inicial repositorio y ramas
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/<usuario>/<repo>.git
git push -u origin main
git checkout -b phone

# LiveKit SIP (desde livekit-voice-agent/)
lk sip inbound create inbound-trunk.json
lk sip dispatch create dispatch-rule.json
lk sip dispatch update --id SDR_<ID_EXISTENTE> dispatch-rule.json

# Ejecutar agente
uv run agent.py dev
```

---

## Resultado
Con esta migración tu agente:
- Atiende llamadas entrantes (SIP) con LiveKit
- Consulta base de conocimiento vectorial en Supabase
- Mantiene respuestas concisas orientadas a agendar citas
- Puede finalizar llamadas mediante tools cuando corresponde
