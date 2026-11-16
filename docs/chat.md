# Local Ollama chat

Chat streams real Ollama responses, saves private conversations, supports cancellation and reloads history. Partial or failed responses are marked incomplete. No generated response is automatically saved as a family memory.

## Windows

Start Ollama, then install `qwen3:8b` using `ollama pull qwen3:8b` if necessary. Run `scripts/start-local.ps1` and select Chat. Existing accounts and memories are preserved by migration 0003. Defaults:

```powershell
$env:CLAIRE_LLM_BASE_URL = 'http://127.0.0.1:11434'
$env:CLAIRE_LLM_MODEL = 'qwen3:8b'
.\scripts\start-local.ps1
```

The selector lists installed local models; a missing model produces an actionable error, not a simulated response.

## Docker

Compose defaults to `http://claire-ollama:11434`. Start and populate the optional service:

```sh
docker compose --profile local-ai up -d claire-ollama
docker compose exec claire-ollama ollama pull qwen3:8b
```

For an existing Ollama server, configure CLAIRE_LLM_BASE_URL with a private address reachable from the application container. Container loopback is not the host. CPU inference is supported; GPU configuration has not been validated.

## Privacy and limits

Only the user's recent conversation is included: at most 20 completed messages and 16,000 history characters, plus the current message and system instructions. Live lexical retrieval searches the latest 200 authorized, non-deleted memories, including imported text documents, and supplies up to three excerpts (at most 2,400 characters each). Long texts contribute passages matching the question, including passages near the end. Accents and case are normalized. Mention a name or detail from the memory; semantic similarity and follow-up query rewriting are not implemented. Reads verify committed revisions and visibility before sending content. Import text files through Documents and Archives; there is no direct chat attachment, tool execution or cloud fallback. Public provider addresses and advertised cloud models are rejected. The operator must trust the configured local service: a private server can itself forward requests elsewhere.

Conversations and messages have owner-only PostgreSQL row-level policies. Family administrators cannot read other users' chats. Transcripts currently live in the database; portable transcript export and deletion UI remain future work. Include the database in backups.

Each conversation allows one generation at a time. Default timeout is 180 seconds, input limit is 4,000 characters, and output is bounded. Stopping a response keeps the partial text with cancelled status. Per-user compute quotas are not yet implemented.

## Validation

An opt-in real-provider browser test runs with `CLAIRE_LIVE_OLLAMA=1`, against the disposable smoke application on port 8010. CI skips this test without a local model. Real inference, reload and cancellation were verified with Ollama 0.40.3 and qwen3:8b on the development host. Protocol reference: https://docs.ollama.com/api/chat.

New memories are available immediately without indexing or re-saving. Sources include title, UUID, revision and verification status in the model context; the model is instructed to cite title and revision. Citations are model-generated and should be checked against the memory. Previously saved chat responses remain in the private transcript even if a source is later deleted or made private.
