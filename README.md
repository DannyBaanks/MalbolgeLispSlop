# MalbolgeLispSlop

> **Humano ↔ IA ↔ Evidencia.** Resultados construidos mediante colaboración y verificación reproducible.

MalbolgeLispSlop reúne un evaluador Lisp en Python, una representación intermedia
(IR) y herramientas de síntesis para la VM Malbolge de 19 trits fijos
(`fixed-3^19` / `bolge19`). **H9 v3 suma dentro de la VM**: para `(+ a b)` con dos
dígitos en formato fijo, el IR se compila a un sumador ternario con acarreo hecho de
compuertas CRAZY, y la VM calcula la suma y la imprime en decimal (`0` a `18`). La
misma imagen corre sin cambios en el `fast20.c` original de MalbolgeLISP (véase
[H9 v3](#h9-v3-sumador-ternario-nativo-compilado-desde-el-ir)). H9 v2, que
seleccionaba la salida en una tabla, se conserva como histórico.

Encima de ese sumador hay un **compilador de programas IR con ramas, bucles
acotados y memoria** (H10–H12). Con él, evaluadores escritos en IR corren dentro de
la VM: `(- 1 (* 2 3))` → `-5`, `(* 99 99)` → `9801`. Véase
[H10–H12](#h10h12-compilador-predicado-de-ir-a-malbolge).

La ejecución nativa de Lisp general continúa en desarrollo. El evaluador Python,
el probe de bootstrap y el circuito H9 son capacidades diferentes.

## Estado verificado — 22 de octubre de 2026

| Componente | Capacidad | Alcance de la evidencia |
| :--- | :--- | :--- |
| **H10–H12 nativos** | Compilador predicado de IR (ramas, bucles desenrollados con cota, memoria con direcciones dinámicas); evaluadores IR de `(op a b)` con `+ - *`, operandos de 1–2 cifras y expresiones anidadas de profundidad 2 | 3.293 casos en `fast20.c` original y en `bolge19`, todos correctos; bucles **desenrollados**, no nativos |
| **H9 v3 nativo** | Compila `Add`, `Sub` por constante y `WriteDecimal` del IR a un sumador ternario con acarreo; valida dígitos con aritmética | 498 casos del IR por defecto y cuatro variantes de IR en `fast20.c` original y en `bolge19`; tres programas rechazados por análisis de intervalos |
| **H9 v2 nativo (histórico)** | Guarda ambos operandos, valida el marco fijo y selecciona la salida con un circuito one-hot de 100 entradas | Las 100 parejas de dígitos con tres finales de entrada; controles negativos, contraste con el modelo y **ejecución en `fast20.c` original de MalbolgeLISP** |
| **Evaluador host** | Evaluación en Python, entornos léxicos, clausuras y funciones numéricas, de listas y de orden superior | Pruebas de integración del host; no equivalen a ejecución Lisp general en la VM |
| **Imagen de bootstrap** | `input; output; halt`, 259 celdas canónicas | Prueba de emisión, cargador y E/S; no contiene el evaluador general |
| **IR Lisp** | Módulos y contratos para el lowering nativo | La aritmética del marco H9 se baja a Malbolge (v3); otros cuerpos IR siguen siendo scaffolding y el evaluador general no está bajado |
| **Matriz completa de Lisp** | Inventario de funciones y semánticas pendientes | `INCOMPLETE`; pasar la suite no completa esta matriz |

La [validación final](evidence/h9_eval_add_v2/validation/20261020T083040Z/REPORT.md)
registra **290 pruebas pasando**, **319 ejecuciones nativas verificadas** y
**dos ejecuciones del modelo de transiciones**. Los totales se refieren a esa
revisión y están respaldados por salidas y hashes conservados en el repositorio.

## H10–H12: compilador predicado de IR a Malbolge

`slopsynth/predicated.py` compila programas IR completos. Cada bloque se ejecuta con
un predicado 0/1 (if-conversion); solo las salidas son condicionales. Los bucles
del IR se **desenrollan hasta una cota declarada**, y `Load`/`Store` con dirección
dinámica se vuelven selectores sobre las celdas posibles. Un análisis de intervalos
y de conjuntos de valores decide rondas de acarreo, dígitos decimales y celdas
alcanzables. El intérprete de referencia en Python aplica la misma cota.

Los evaluadores son programas IR normales; el compilador no sabe nada de Lisp:

| Compuerta | Lenguaje | Celdas | Casos (`fast20.c` y `bolge19`) |
| :--- | :--- | ---: | ---: |
| H10 | `(op a b)`, `op` en `+ - *`, un dígito, resultado con signo | 9.612.592 | 1110/1110 |
| H11 | `(op a b)` con operandos de 1–2 cifras; un byte por vuelta, cota 11 | 57.978.001 | 1113/1113 |
| H12 | `expr := dígito \| (op expr expr)`, profundidad ≤ 2, descenso recursivo sobre memoria | 28.245.709 | 1070/1070 |

```sh
python3 -B tools/verify_predicated.py   # unos 12 minutos
```

Límites que la [campaña](evidence/h10_h12_predicated_v1/protocol.md) deja escritos:
los bucles **no son bucles nativos de Malbolge** (H11 copia su cuerpo doce veces);
la entrada debe caber en el máximo de cada compuerta (9, 12 o 22 bytes) y stdin debe
cerrarse; no hay división, variables, `lambda`, listas ni profundidad mayor que 2.
Las imágenes son grandes porque se emiten todas las vueltas y todos los caminos.

## H9 v3: sumador ternario nativo compilado desde el IR

El contrato de entrada y salida es el mismo que en v2 (abajo). Cambia lo que hace la VM:

- **Suma de verdad.** Las palabras de 19 trits se suman en paralelo: la suma trit a
  trit módulo 3 y el acarreo se calculan con compuertas CRAZY y tablas unarias, y el
  acarreo se desplaza un trit por ronda. Ningún resultado se precalcula en Python.
- **Dígitos validados con aritmética.** `x` es dígito si `x + 195` acarrea al trit 5
  y `x + 185` no. Solo la puntuación del marco se compara byte a byte.
- **Decimal con acarreo.** Las decenas salen del acarreo de `v + 233` al trit 5; las
  unidades son `v + 38 + 10·(1 − decenas)`.
- **Compilado desde el IR.** `slopsynth/eval_add_v3.py` recorre el IR, asigna un
  rango a cada valor, elige las rondas de acarreo de cada operación y rechaza
  programas que pueden dar negativo, pasar de `3^6` o imprimir más de 19. Otro IR
  produce otra imagen.

| IR | Celdas | `fast20.c` | `bolge19` |
| :--- | ---: | ---: | ---: |
| `sum = op1 + op2; result = sum − 96` (por defecto) | 2.847.163 | 498/498 | 498/498 |
| `s = op1 + op1; result = s − 96` | 2.847.163 | 103/103 | 103/103 |
| `result = op2 − 48` | 2.758.063 | 103/103 | 103/103 |
| `x = op1 − 48; y = op2 − 48; result = x + y` | 3.056.986 | 103/103 | 103/103 |
| `s = op1 + op2; t = s − 96; result = t + 1` | 2.908.156 | 103/103 | 103/103 |

La imagen por defecto ocupa 2.847.163 celdas, un 41 % menos que v2. La
[campaña v3](evidence/h9_eval_add_v3/protocol.md) conserva imágenes, salidas por
VM, rechazos y hashes:

```sh
./tools/build.sh
python3 -B tools/verify_h9_v3.py
```

Sigue **NOT_DEMONSTRATED**: otros marcos, operandos de varias cifras, anidamiento,
restar un valor con nombre, bucles (el circuito es acíclico) y Lisp general.

## H9 v2: circuito nativo con alcance explícito

```text
(+ 0 0)  →  0
(+ 1 1)  →  2
(+ 3 2)  →  5
(+ 9 9)  →  18
```

Contrato de entrada y salida:

- Entrada exacta `(+ a b)`, donde `a` y `b` son dígitos ASCII de `0` a `9`.
- Se admite LF o CRLF opcional, seguido de **EOF**: hay que cerrar stdin.
- El contrato admite como máximo nueve bytes de entrada.
- Salida decimal de `0` a `18`, sin salto de línea.
- Los marcos mal formados dentro de ese límite terminan sin salida.
- Enteros de varias cifras, anidamiento, otros formatos y flujos abiertos quedan fuera de este backend.

El programa conserva los operandos en memoria y ejecuta un circuito nativo de
CRAZY/ROT: decodifica cada dígito en diez banderas one-hot, combina con AND las
100 parejas posibles y une cada resultado en el riel de su suma. Las decenas son
el OR de los rieles 10 a 18. Python construye la imagen; durante la ejecución, la
VM recibe únicamente esa imagen y los bytes de entrada. Los casos de prueba no
seleccionan la implementación.

**Qué no hace:** la VM no suma. El valor `i + j` que conecta cada pareja con su
riel se calcula en Python al generar la imagen (`slopsynth/_native_eval_add.py`);
dentro de la VM ocurre una selección en una tabla de 100 entradas construida con
compuertas. El circuito es acíclico: cada compuerta se ejecuta una vez, sin bucles.
El IR de `build_eval_add_module()` no genera este código: `lower_eval_add` solo
valida que el módulo tenga la forma exacta esperada y después emite la plantilla
fija. Una suma ternaria con acarreo ejecutada en la VM sigue
**NOT_DEMONSTRATED**.

La imagen tiene **4.837.558 celdas canónicas** —unos 4,84 MB de fuente sin
espaciado— y las entradas válidas verificadas requieren **4.837.453 o 4.837.454
pasos de VM**, excluyendo el HALT terminal. Estas son medidas de la VM, no ciclos
físicos de CPU.

La [campaña H9 v2](evidence/h9_eval_add_v2/protocol.md) conserva:

| Comprobación | Ejecuciones nativas |
| :--- | ---: |
| 100 parejas × EOF, LF+EOF y CRLF+EOF | 300 |
| Marcos inválidos representativos | 10 |
| Neutralidad del espaciado de la imagen | 3 |
| Mutaciones de las lecturas de operandos y de la salida | 3 |
| Contraejemplos de la imagen histórica v1 | 3 |
| **Total de expectativas verificadas** | **319** |

Los mutantes y contraejemplos deben fallar la suma esperada: se contabilizan como
controles negativos, no como sumas correctas. Además, el modelo Python de las
transiciones coincide con la VM en `(+ 1 1) → 2` y `(+ 9 9) → 18`.

### Ejecución en un intérprete externo

La misma imagen corre sin cambios en el `fast20.c` original de MalbolgeLISP
(revisión `0dc37eb`, sin parches, CC0), que también usa 19 trits. En
[la campaña de contraste](evidence/h9_fast20_crosscheck_v1/protocol.md),
`fast20.c` y `bolge19` dan la salida esperada en **498 de 498 casos**: las 300
entradas válidas y 198 marcos inválidos, mutados o aleatorios. El resultado no
depende de nuestra VM.

```sh
python3 -B tools/verify_h9_fast20.py
```

**H9 v1 sigue refutado.** Su imagen de 259 celdas descartaba el primer operando;
`(+ 0 0)` y `(+ 1 1)` también imprimían `3`. Se conserva su evidencia histórica y
se rechaza la plantilla IR antigua de salida de un byte. La versión nueva usa
`WriteDecimal` para distinguir salida decimal de salida de bytes. Véase la
[corrección histórica y transición a v2](docs/H9_CORRECTION.md).

## Construir y probar H9

Requisitos de la revisión verificada: **Python 3.12+** y **Zig 0.16.0**.

Desde la raíz del repositorio:

```sh
./tools/build.sh
python3 -B tools/build_eval_add.py --out build/h9-v2/eval_add.mb --manifest build/h9-v2/eval_add.manifest.json
printf '%s' '(+ 9 9)' | build/bolge19 --loader canonical --max-steps 10000000 build/h9-v2/eval_add.mb
```

Stdout esperado: `18`, sin salto de línea. La VM escribe la telemetría de HALT en
stderr. La tubería del ejemplo cierra la entrada; un flujo que permanezca abierto
puede dejar el programa esperando EOF.

Para repetir la campaña y crear un directorio de evidencia nuevo:

```sh
python3 -B tools/verify_h9_eval_add.py
```

La [guía humana](GUIA.md) contiene los comandos y salidas de la revisión, estados
de ejecución y límites del contrato.

## Suite de pruebas y modelo host

Para instalar las dependencias de desarrollo en un entorno aislado:

```sh
python3 -m venv build/venv
. build/venv/bin/activate
python3 -m pip install -r requirements-dev.txt
python3 -B -m unittest discover -s tests -t .
```

Z3 se usa en construcción y verificación; la imagen Malbolge generada no depende
de Python ni de Z3 durante su ejecución.

El host conecta los helpers numéricos, de listas, de orden superior y combinadores.
`.F` anuncia las funciones registradas. `+`, `+'`, `-`, `-'` y `*` operan módulo
`2^26`. El lector conserva los apóstrofos de identificadores y exige una sola forma
completa por paso del REPL.

Los snapshots v2 conservan clausuras, recursión y entornos léxicos, y permiten
importar datos v1. Los valores opacos del host se rechazan explícitamente al
exportar; una importación inválida conserva la sesión anterior.

El runner de conformidad distingue `PASS` (código 0), `FAIL` (1) e `INCOMPLETE`
(2). Cero casos o cobertura pendiente nunca producen un éxito de conformidad.
La matriz de Lisp general incluida permanece incompleta.

## Primitivas y evidencia anterior

Los protocolos H1–H8 documentan plantillas y experimentos previos. Sus resultados
se limitan a los casos registrados; no acreditan un compilador genérico de IR ni
un intérprete Lisp nativo completo.

| Compuerta | Protocolo |
| :--- | :--- |
| H1: frontend y layout canónico | [Protocolo](evidence/hell_frontend_v1/protocol.md) |
| H2: plantillas de bifurcación | [Protocolo](evidence/h2_branch_v1/protocol.md) |
| H3: plantilla de bucle — **no itera más allá de sus casos** ([auditoría](evidence/h3_h7_loop_audit_v1/protocol.md)) | [Protocolo](evidence/h3_loop_v1/protocol.md) |
| H4: plantilla de memoria | [Protocolo](evidence/h4_memory_v1/protocol.md) |
| H5: aritmética acotada | [Protocolo](evidence/h5_arithmetic_v1/protocol.md) |
| H6: llamada y retorno acotados | [Protocolo](evidence/h6_call_return_v1/protocol.md) |
| H7: cuenta regresiva compuesta — **solo n ∈ {0, 1, 3}** ([auditoría](evidence/h3_h7_loop_audit_v1/protocol.md)) | [Protocolo](evidence/h7_countdown_v1/protocol.md) |
| H8: helpers host y probe de bootstrap | [Protocolo](evidence/lisp_conformance_v1/protocol.md) |

La [descripción de la arquitectura](docs/LISP_CONFORMANCE.md) distingue los helpers
del host, los módulos IR y el bootstrap. Un hash acredita la identidad del artefacto;
las entradas, salidas y controles determinan qué comportamiento demuestra.

## Sobre el nombre y la colaboración

“Slop” es una reapropiación deliberada de una etiqueta usada para descalificar el
trabajo asistido por IA. El proyecto responde con código inspeccionable, pruebas
reproducibles y correcciones explícitas cuando una afirmación queda refutada.

Desarrollado por **Danny Baanks** en colaboración con **Antigravity (Google
DeepMind)** y **Codex (OpenAI)**, dentro del ecosistema de investigación ISyCo.

## Licencia

Código bajo [licencia MIT](LICENSE). Consulte también los
[avisos de terceros](THIRD_PARTY_NOTICES.md).
