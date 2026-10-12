# Tasks

Tareas ordenadas por dependencia. Cada una se da por cerrada solo cuando su
verificación pasa. Verificación global tras cada tarea:

```bash
uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest
```

## 1. Dominio

- [x] **1.1 Modelos.** `Severity.rank`, `ReviewTarget`, `Finding.line`,
  `ReviewItem`, `InlineComment`, `TokenUsage`, `LLMResult`, `GraphState`
  nuevo. — `domain/models.py`
  - Verifica: `pytest tests/unit/test_models.py`
- [x] **1.2 Utilidades de diff.** `added_lines`, `commentable_lines`,
  `annotate_patch`, `apply_budget`. — `domain/diff.py`
  - Verifica: `pytest tests/unit/test_diff.py` (hunks múltiples, borrados,
    `\ No newline`, truncado por archivo y total).
- [x] **1.3 Puertos y errores.** `DiffProvider`, `ReviewPublisher`,
  `StaticAnalyzer`, `LLMClient`; `ReviewError`, `LLMError`,
  `StaticAnalysisError`. — `domain/ports.py`, `domain/errors.py`
  - Verifica: `mypy src`.

## 2. Adapters

- [x] **2.1 Cliente GitHub compartido** con paginación por `Link` y retry en
  429/5xx. — `adapters/github/rest_client.py`
  - Verifica: `pytest tests/unit/adapters/test_github.py::test_paginates`
- [x] **2.2 Diff provider** sobre `/pulls/{n}/files`.
  - Verifica: test con HTTP mockeado, 2 páginas, archivo binario sin `patch`.
- [x] **2.3 Review publisher**: upsert del comentario sticky por marcador;
  review inline con dedupe.
  - Verifica: tests "crea si no existe", "actualiza si existe", "no
    re-publica inline idéntico".
- [x] **2.4 Gemini** con `response_schema`, retry HTTP, `usage_metadata`,
  errores → `LLMError`. — `adapters/llm/gemini_client.py`
  - Verifica: tests con cliente falso: JSON válido, JSON inválido → `LLMError`.
- [x] **2.5 Ruff** en JSON, solo archivos presentes y líneas agregadas,
  severidad máxima `medium`. — `adapters/static_analysis/ruff_runner.py`
  - Verifica: test que escribe un `.py` con un import sin usar en `tmp_path`
    y espera un `Finding` en la línea correcta.

## 3. Aplicación

- [x] **3.1 Prompts** con diff delimitado, numerado y cláusula anti-injection.
  — `application/prompts.py`
- [x] **3.2 Agente de revisión genérico** (reemplaza `security_agent.py`,
  `code_arch_agent.py`, `parsing.py`). — `application/nodes/review_agent.py`
  - Verifica: tests "mapea items a findings", "`LLMError` → `agent_errors`".
- [x] **3.3 Ingest** con presupuesto de diff.
- [x] **3.4 Supervisor** con triggers ampliados y ruta solo-docs.
  - Verifica: tests para `Dockerfile`, `.env.production`,
    `requirements.txt`, `README.md`.
- [x] **3.5 Static analysis** como rama del fan-out.
- [x] **3.6 Aggregator** con dedupe y gate configurable.
- [x] **3.7 Rendering** del resumen, del aviso de pendiente y del rechazo, con
  saneo de mensajes. — `application/rendering.py`
  - Verifica: tests de menciones neutralizadas, sección "incompleta",
    truncados.
- [x] **3.8 `notify_pending`, `human_review`, `post`.**
  - Verifica: tests "inline solo en líneas del diff", "rechazo no publica
    hallazgos".
- [x] **3.9 Grafo**: topología nueva, `RetryPolicy` en nodos de IO,
  instrumentación de duración por nodo. — `application/graph.py`,
  `application/instrumentation.py`
  - Verifica: `pytest tests/integration` — limpio, solo-docs, HIGH aprobado,
    HIGH rechazado, agente caído, sin duplicados entre corridas, resume desde
    SQLite con otro objeto grafo.

## 4. Entrypoints

- [x] **4.1 Settings y wiring** tipados desde env. — `entrypoints/settings.py`,
  `entrypoints/wiring.py`
  - Verifica: tests de defaults y de variable faltante.
- [x] **4.2 Runner + CLI**: `review run --repo --pr`, `review resume
  --thread --approve|--reject`. — `entrypoints/runner.py`, `entrypoints/cli.py`
  - Verifica: `uv run review --help`.
- [x] **4.3 Entrypoint de Actions**: `analyze` (lee el evento, escribe
  `GITHUB_OUTPUT` y `GITHUB_STEP_SUMMARY`) y `resume`.
  - Verifica: test con evento de fixture y archivos temporales.
- [x] **4.4 Logging JSON.** — `entrypoints/logging_setup.py`
- [x] **4.5 Visualize** actualizado; `docs/graph.mmd` regenerado.
  - Verifica: `uv run visualize-graph`.

## 5. CI/CD

- [x] **5.1 `pr-review.yml`**: jobs `analyze` y `approve`, guard de forks,
  permisos mínimos, artifact del checkpoint, concurrency por PR.
- [x] **5.2 `ci.yml`**: ruff, format, mypy, pytest.
- [x] **5.3 `evals.yml`**: `workflow_dispatch`.

## 6. Evals

- [x] **6.1 Dataset semilla** (`evals/dataset.jsonl`).
- [x] **6.2 Scorer y runner** (`uv run eval`) con precision/recall por agente
  y umbrales. — `src/agent_langgraph/evals/`
  - Verifica: `pytest tests/unit/test_evals.py` (scorer con LLM falso).

## 7. Cierre

- [x] **7.1 README** actualizado; limpieza de referencias a Groq; `.gitignore`.
- [x] **7.2 Verificación global en verde.**

## 7b. Portabilidad

- [x] **7b.1 Adapter compatible con OpenAI** seleccionable con `LLM_PROVIDER`.
  — `adapters/llm/openai_compatible_client.py`, `adapters/llm/schema.py`
  - Verifica: `pytest tests/unit/adapters/test_openai_compatible.py`
- [x] **7b.2 Workflow reutilizable** (`review.yml`, `workflow_call`);
  `pr-review.yml` pasa a ser el caller de este repo.

## 7c. Configuración por repo

- [x] **7c.1 `.pr-review.yml`** leído del commit base: revisores activos,
  paths ignorados, severidad del gate y reglas propias.
  — `adapters/github/rest_config_provider.py`, `application/nodes/ingest.py`
  - Verifica: `pytest tests/unit/test_repo_config.py`

## 8. Manual (requiere credenciales y GitHub real)

- [ ] **8.1** Crear el Environment `review-approval` en *Settings →
  Environments* y agregar *Required reviewers*.
- [ ] **8.2** Cargar el secret `GEMINI_API_KEY` en el repo.
- [ ] **8.3** `uv run eval` con `.env` completo y registrar las métricas
  base en el README.
- [ ] **8.3b** Si se usa otro proveedor: cargar el secret `LLM_API_KEY` y las
  variables `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`; correr `uv run eval`
  con ese modelo antes de confiar en sus revisiones.
- [ ] **8.4** Abrir un PR de prueba con un secreto hardcodeado en un `.py` y
  comprobar: comentario "esperando aprobación" → aprobar el deployment →
  resumen + inline publicados; un segundo push actualiza el mismo comentario.
