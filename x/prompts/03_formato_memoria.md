CAPA 3: FORMATO DE MEMORIA (para PostgreSQL)

Toda la información debe almacenarse en formato estructurado JSON:

{
  "type": "episodic | semantic | structural | procedural",
  "timestamp": "...",
  "context": "...",
  "content": "...",
  "entities": [],
  "relationships": [],
  "importance": 0-1,
  "embedding_ready": true
}