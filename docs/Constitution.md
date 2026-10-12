# Constitution — reglas innegociables

Estas reglas no se discuten PR a PR. Si una regla estorba, se cambia acá
primero, con su motivo, y recién después en el código.

## I. Arquitectura

1. **Las dependencias apuntan hacia adentro.** `domain/` no importa nada
   fuera de la stdlib. `application/` importa solo `domain/` y LangGraph.
   `adapters/` implementa puertos de `domain/ports.py`. Solo `entrypoints/`
   conoce clases concretas.
2. **Variables de entorno solo en `entrypoints/`.** Ningún nodo ni adapter
   lee `os.environ`; reciben valores ya resueltos.
3. **Un nodo, un archivo, una responsabilidad.** Los nodos devuelven un
   update parcial del estado; no mutan el estado recibido.
4. **Todo IO pasa por un puerto.** Ni `requests`, ni `subprocess`, ni el SDK
   del LLM aparecen en `application/`.

## II. Comportamiento del LLM

5. **Toda salida del LLM es estructurada y validada** contra un schema. No se
   parsea texto libre.
6. **Un fallo nunca se reporta como "limpio".** Error de red, de cuota o de
   validación se registra en `agent_errors` y se publica como "revisión
   incompleta".
7. **El diff es dato, nunca instrucción.** Se envía delimitado y el prompt de
   sistema lo declara no confiable. Nada del diff se interpola en el prompt
   de sistema.
8. **Lo que escribe el modelo se sanea antes de publicarse**: una línea, largo
   acotado, sin menciones.
9. **Un linter no puede disparar el gate humano.** El análisis estático
   reporta como máximo severidad media.
10. **Cambiar un prompt o el modelo exige correr las evals** y dejar el
    resultado en la descripción del PR.

## III. Grafo y estado

11. **El nodo que llama a `interrupt()` no tiene efectos externos.** Al
    reanudar, LangGraph re-ejecuta ese nodo desde el principio.
12. **Los campos escritos por ramas paralelas llevan reducer.**
13. **Un `thread_id` por ejecución.** Nunca se reutiliza un thread para una
    corrida nueva; solo para reanudar la misma.
14. **La publicación es idempotente.** Re-ejecutar cualquier nodo de
    publicación no crea comentarios duplicados.

## IV. Seguridad

14b. **La configuración del repo se lee de la rama base, nunca del head del
    PR.** Un PR no puede apagar a sus propios revisores ni cambiar las reglas
    con las que se lo evalúa. Una config inválida se ignora con aviso; no
    bloquea ni silencia la revisión.

15. **Nunca `pull_request_target`.** El workflow no corre con secrets sobre
    código de forks.
16. **Permisos mínimos del token**: `contents: read`, `pull-requests: write`.
17. **Ningún secret en logs, comentarios, artifacts ni fixtures.**
18. **El agente no ejecuta código del PR.** Solo lo lee y lo lintea.

## V. Calidad

19. **Todo nodo tiene test unitario; todo camino del grafo tiene test de
    integración.** Los tests no tocan la red ni requieren credenciales.
20. **`ruff check`, `ruff format --check`, `mypy src` y `pytest` en verde**
    para mergear.
21. **`docs/graph.mmd` refleja el grafo compilado.** Si cambia la topología,
    se regenera en el mismo PR.
22. **SPEC primero.** Un cambio de comportamiento observable actualiza
    `docs/SPEC.md` en el mismo PR.
