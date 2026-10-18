# specimen100 - reglas de trabajo (M0)

Fuente del plan: `/home/danny/Development/ISyCo/.opencode/plans/malbolgelisp-specimen-100.md` (READY_FOR_CODER).

## Reglas duras

1. El repositorio principal (`/home/danny/Development/ISyCo`) es SOLO LECTURA desde este track.
2. El especimen (`lisp.zip`, `core.mb`, `init_module.mb`, `lisp.mb`, manual) NO se copia a este repo ni se distribuye; aqui solo hashes, logs y reportes pequenos.
3. El clon upstream vive en scratch fuera de repos (`/tmp/opencode/malbolgelisp-upstream-0dc37eb1`); no se pushea ni se edita upstream.
4. Blobs grandes regenerados (371 MB) viven en scratch y se descartan; nunca se comitean.
5. Evidencia en rutas nuevas (`evidence/specimen100/...`); jamas se reutiliza un output path ni se reescribe evidencia historica.
6. Builds del VM propio: Zig 0.16.0; cambios de VM solo en M5 (flag apagado por defecto).
7. No publicar / push / PR / release en este track.

## Matriz de aceptacion (E1/E2/E3)

- E1 REPRODUCIR: (a) artefactos upstream desde `0dc37eb1` con veredicto por artefacto; (b) REPL canonico bajo `bolge19` (bateria minima + HALT con conteo vs historico 2,408,246,381); (c) regeneracion byte-exacta de `lisp.mb` (`sha256==092df5cd...`, `len==371,331,415`).
- E2 FALLAS: matriz diferencial (bolge19 / fast20-linux / fast20_fixed-linux / oracle 3^10 control) + casos limite; cada hallazgo con repro exacto o `NOT_DEMONSTRATED`; claims Windows re-clasificados como HISTORICAL no re-ejecutables.
- E3 REDUCIR: representacion generativa con cobertura cuantificada (M4) y/o equivalencia conductual sobre bateria B con S' minimo o contraejemplo minimo (M5).

"100%" = esta matriz ejecutada entera. Subir una etiqueta solo con verificacion ejecutada; si no, `PARTIAL` / `NOT_DEMONSTRATED`.
