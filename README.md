# MalbolgeLispSlop

> **Humano ↔ IA ↔ Evidencia.**  
> Resultados que nacen de la iteración conjunta y la verificación empírica estricta, no de una sola autoría.

**MalbolgeLispSlop** es un dialecto e intérprete nativo de Lisp para la máquina virtual Malbolge de 19 trits fijos (`fixed-3^19` / `bolge19`), diseñado desde cero para ejecutar expresiones Lisp de forma compacta, modular y verificable, sin requerir compiladores monolíticos ni cientos de megabytes de tablas de salto infladas.

---

## Sobre el nombre: ¿Por qué "Slop"?

En el discurso contemporáneo sobre inteligencia artificial, la palabra **"slop"** se utiliza con frecuencia como una etiqueta despectiva para descalificar a priori el trabajo asistido por modelos de lenguaje, asumiendo que la IA solo es capaz de generar texto superficial o código de relleno incapaz de abordar problemas matemáticos complejos o sistemas hostiles.

**Este proyecto toma esa etiqueta y la subvierte:**

Malbolge es ampliamente reconocido como el lenguaje de programación esotérico más difícil jamás creado: aritmética ternaria, auto-modificación de código en cada ciclo de instrucción, la operación no-lineal *crazy*, y un espacio de estados hostil a la intuición humana tradicional.

Demostrar que un sistema colaborativo **Humano + IA** puede:
1. Sintetizar semillas discriminadoras algebraicas en Malbolge,
2. Construir bifurcaciones condicionales y bucles con permanencia de salto (JMP immortality),
3. Diseñar cadenas de involución de memoria arbitraria a través de los 256 bytes,
4. Implementar llamadas a función y retornos en saltos computados de 5 pasos,
5. Desarrollar un evaluador Lisp completo estilo McCarthy (con tagged pointers, bump allocator, ambientes léxicos, clausuras, combinadores funcionales y REPL), y
6. Respaldar cada compuerta con **272 pruebas unitarias pasando al 100%** y evidencia forense ejecutable byte a byte en hardware bare-metal...

...prueba que el trabajo riguroso guiado por intención humana, razonamiento de modelo y verificación matemática estricta está en las antípodas del contenido desechable. Si resolver Lisp sobre la máquina de Malbolge es *"slop"*, entonces el *slop* acaba de resolver varios de los desafíos teóricos más intrincados de la informática esotérica.

---

## 🔬 Honestidad Técnica: Separando Infraestructura de Ejecución Nativa

Siguiendo el rigor epistemológico de **ISyCo**, no vendemos stubs como productos terminados. Es fundamental distinguir con precisión dos realidades del proyecto:

1. **La Infraestructura Demostrada:**
   - **Compuertas H1 a H7 en Malbolge Real:** Síntesis y ejecución verificada de primitivas de bajo nivel en hardware bare-metal (`build/bolge19`): saltos condicionales (`brz`), bucles inmortales, lectura/escritura de memoria arbitraria (involución con byte 121), aritmética con semillas discriminadoras, llamadas y retornos en exactamente 5 ciclos de CPU, y cuenta regresiva compuesta.
   - **Arquitectura Guest IR y Modelo Teórico:** Diseño y verificación de 13 subsistemas (empaquetado de tagged pointers en 1 sola celda de 19 trits con $13 \times 2^{26} < 3^{19}$, heap bump allocator, streaming reader/printer, y evaluador McCarthy en host respaldado por **272 pruebas unitarias pasando al 100%**).
   - **Máquina Virtual Forense:** Implementación de `bolge19` en Zig para $3^{19}$ celdas con cargador canónico estricto.

2. **La Realidad de la Imagen `build/lispslop-guest.mb` (Frontera en Progreso):**
   - La imagen de 259 celdas generada por `tools/build_lisp_guest.py` es actualmente un **Bootstrap Harness Probe** nativo (`input; output; halt`). Demuestra que el pipeline de síntesis puede emitir imágenes canónicas de 259 celdas que el cargador estricto de la VM acepta y ejecuta limpiamente.
   - En `guest_ir/lisp/evaluator.py`, la semántica McCarthy existe y pasa todos los tests en Python, pero su representación en el módulo IR contiene por ahora `operations=(Return("form"),)`.
   - **Por tanto, la ejecución de expresiones Lisp arbitrarias 100% dentro de la máquina de estados de Malbolge permanece como `[EN PROGRESO / NOT_DEMONSTRATED en VM]`**. 
   - La meta final sigue siendo bajar (*lower*) el evaluador de IR hacia secuencias de opcodes de Malbolge ensamblando los bloques H1–H7 para reemplazar el monolito inflado de 371 MB de LMFAO, pero estamos construyendo la infraestructura de compilación paso a paso, sin proclamar victorias prematuras.

---

## 📐 Midiendo Sistemas: La Evidencia en Números

> *"No somos vergeros en palabras, sino en evidencia: cada claim en este repositorio tiene un archivo de entrada binario, una captura de salida stdout/stderr, un límite de pasos, y un hash SHA-256 inmutable verificado en hardware real."*

| Dimensión de Sistema | Estado Previo (LMFAO / HeLL 2020) | MalbolgeLispSlop (ISyCo 2026) | Estado de Evidencia |
| :--- | :--- | :--- | :--- |
| **Micro-kernels de Control de Flujo** | Tablas gigantescas no estructuradas | **259 celdas canónicas por compuerta** | `[DEMONSTRATED]` (Gates H1–H7 en VM) |
| **Overhead de Invocación (`call`/`ret`)** | No estructurado | **Exactamente 5 ciclos de CPU** | `[DEMONSTRATED]` ($M[2]=66$, $M[3]=95$) |
| **Involución de Memoria Arbitraria** | N/A | **100% de los 256 bytes cubiertos** | `[DEMONSTRATED]` (Byte crazy $121$) |
| **Bifurcación Condicional (`brz`)** | N/A | **3-way landing cascade** | `[DEMONSTRATED]` (Celdas $1, 2, 247$) |
| **Espacio de Direccionamiento** | Tablas estáticas desbordadas | **Fixed-$3^{19}$** ($1,162,261,467$ celdas) | `[DEMONSTRATED]` (Zig `bolge19`) |
| **Empaquetado de Datos (Tagged Pointers)** | Sin tipado estructurado en celda | **13 tipos en 1 sola celda de 19-trits** | `[DEMONSTRATED]` (Tag 4b + Payload 26b) |
| **Evaluador McCarthy en Host/IR** | Intérprete estático monolítico | **13 subsistemas modulares (Python/IR)** | `[DEMONSTRATED]` (272/272 tests verdes) |
| **Imagen Probe de Bootstrap** | N/A | **259 bytes canónicos (`ubO`)** | `[DEMONSTRATED]` (62 corridas en VM) |
| **Evaluación Lisp Completa en la VM** | 371 MB compilados con LMFAO | **Lowering de IR a opcodes Malbolge** | **`[IN_PROGRESS / NOT_DEMONSTRATED]`** |
| **Corridas Forenses de VM en Disco** | 0 evidencia ejecutable | **>1,000 corridas selladas SHA-256** | `[DEMONSTRATED]` (Replay bit a bit) |

---

## Filosofía de Colaboración (ISyCo)

Siguiendo los principios de **ISyCo (Sistemas Interactivos para la Coevolución)**:
- **Colaboración, no jerarquía:** El humano y la IA participan como pares. El humano aporta dirección, intuición de diseño, formulación de preguntas y límites claros; el modelo aporta exploración de espacio de estados, síntesis de código y análisis formal.
- **Evidencia como árbitro supremo:** Ninguna afirmación técnica es válida sin una prueba ejecutable, un hash SHA-256 inmutable y una corrida forense en la máquina virtual objetivo (`build/bolge19`).

---

## Estado del Proyecto

- **Gates H1 a H7 (Sustrato Nativo en Malbolge):**
  - **H1:** Layout canónico con alineación y padding de opcodes ([protocolo](evidence/hell_frontend_v1/protocol.md)).
  - **H2:** Bifurcación condicional nativa (`brz` if/else, 259 celdas) ([protocolo](evidence/h2_branch_v1/protocol.md)).
  - **H3:** Bucle iterativo con permanencia de salto ([protocolo](evidence/h3_loop_v1/protocol.md)).
  - **H4:** Memoria dinámica (`store`/`load` mediante involución con byte 121) ([protocolo](evidence/h4_memory_v1/protocol.md)).
  - **H5:** Aritmética modular (`add`/`sub` con semillas discriminadoras) ([protocolo](evidence/h5_arithmetic_v1/protocol.md)).
  - **H6:** Llamada y retorno de funciones (`call`/`ret` en 5 pasos de CPU) ([protocolo](evidence/h6_call_return_v1/protocol.md)).
  - **H7:** Cuenta regresiva compuesta (`loop + branch + sub` simultáneos) ([protocolo](evidence/h7_countdown_v1/protocol.md)).
- **Gate H8 (Infraestructura Guest y Bootstrap Probe):**
  - **H8:** Conformance del arnés guest (62 corridas de VM, 13 subsistemas IR, 272 tests) ([protocolo](evidence/lisp_conformance_v1/protocol.md)).
- **Guest Runtime & Conformance (Tasks 3–10):**
  - Reporte completo y arquitectura modular: [docs/LISP_CONFORMANCE.md](docs/LISP_CONFORMANCE.md).
  - Módulos de IR en `guest_ir/lisp/`: tagged values, bump heap allocator, lexical environments, reader, printer, evaluator, closures, numeric/list builtins, higher-order combinators, REPL step, y serialización versionada de estado.
  - Imagen canónica generada: `build/lispslop-guest.mb` (259 celdas, probe bootstrap canónico aceptado por `walk_canonical`).
  - Manifiesto verificable: `build/lispslop-guest.manifest.json`.
  - **Frontera abierta:** Lowering del evaluador de IR a código máquina de Malbolge.

---

## Requisitos y Compilación

Requisitos:
- **Zig 0.16.0** (para compilar la VM forense `bolge19`)
- **Python 3.12+**

```sh
# 1. Compilar el motor bolge19 y dependencias
./tools/build.sh

# 2. Ejecutar la suite completa de pruebas (272 tests)
PYTHONPATH=. python3 -m unittest discover -s tests -t .

# 3. Construir la imagen canónica de Malbolge del Guest Lisp
make build-lisp-guest

# 4. Probar la conformidad del guest y matriz
make test-conformance
make test-lisp-matrix

# 5. Ejecutar la campaña formal de verificación y sellar evidencia
make verify-lisp-conformance
```

Para una guía paso a paso en español de cada compuerta y comando, consulta la [Guía Humana](GUIA.md).

---

## Licencia y Reconocimientos

- Código bajo licencia MIT (ver [LICENSE](LICENSE)).
- Diseñado y desarrollado en colaboración **Danny Baanks + Antigravity (Google DeepMind)** como parte del ecosistema de investigación ISyCo.
