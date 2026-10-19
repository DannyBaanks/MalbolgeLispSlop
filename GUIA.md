# Probar el primer salto condicional propio

Desde este directorio, con `build/bolge19` ya construido:

```sh
python3 tools/assemble.py examples/branch.slop --round-trip --out build/branch.mb
```

Salida real del 2026-10-18:

```text
branch.slop: guest zero_filter, 259 cells
  lowering=fixed19-zero-stop-else-echo-v1 (scoped H2; general control flow remains unsupported)
  label choose: cells 105
  label stop: cells 1
  label echo: cells 42,96,123,256
  walk: accepted_cells=259 verdict=ACCEPTED
  image_sha256=519bcf325b380a975fa5424b66e2d4eff3867053140391327841313ce263bc77
round-trip: identical
wrote build/branch.mb (259 bytes)
```

**Regla de oro:** compilar o aceptar una imagen no demuestra Lisp. H2 reconoce
dos plantillas fijas: `examples/branch.slop` (cero termina; no cero lee y
devuelve otro byte) y `examples/branch_both_arms.slop` (cero descarta un byte y
devuelve el siguiente; no cero devuelve el siguiente). No se promete que un
`.slop` arbitrario compile.

Si falta el VM, construirlo con Zig 0.16.0:

```sh
bash tools/build.sh
```

Salida real:

```text
built build/bolge19 with Zig 0.16.0
```

## Ejecutar ambas ramas

```sh
python3 - <<'PY'
import subprocess
for value in (b'\x00A', b'\x01A', b''):
    r = subprocess.run(
        ['build/bolge19', 'build/branch.mb', '--loader', 'canonical', '--max-steps', '512'],
        input=value, capture_output=True, check=True,
    )
    print(f'{value.hex() or "EOF"}: stdout={r.stdout!r}')
PY
```

Salida real:

```text
0041: stdout=b''
0141: stdout=b'A'
EOF: stdout=b'\xda'
```

El byte cero es binario `00`; el carácter de teclado `0` es `30` y toma la
rama no cero. EOF vale `3^19 - 1`; su byte bajo en este VM es `da`.

## Rama con trabajo observable en ambos brazos

```sh
python3 tools/assemble.py examples/branch_both_arms.slop --round-trip --out build/branch-both-arms.mb
```

Comprueba que ambos caminos hacen trabajo distinto dentro del guest:

```sh
python3 - <<'PY'
import subprocess
for value in (bytes.fromhex('004142'), bytes.fromhex('014142')):
    result = subprocess.run(
        ['build/bolge19', 'build/branch-both-arms.mb', '--loader', 'canonical', '--max-steps', '512'],
        input=value, capture_output=True, check=True,
    )
    print(f'{value.hex()}: stdout={result.stdout!r}')
PY
```

Salida:

```text
004142: stdout=b'B'
014142: stdout=b'A'
```

La rama cero consume `41` sin imprimirlo y luego devuelve `42`; la rama no cero
devuelve `41` inmediatamente. Para repetir la matriz de selectores en el modelo
y el VM real, incluidos EOF, espacios canónicos y controles mutados:

```sh
python3 -O tools/verify_both_arms_branch.py
```

`BOTH-ARMS DEMONSTRATED_SCOPED` acredita solo esa plantilla y sus 256 valores
de selector. El lowering sigue usando un layout fijo; no demuestra composición
general de bloques, saltos arbitrarios, memoria, llamadas ni un intérprete Lisp.
El protocolo y resultados quedan en `evidence/both_arms_branch_v1/`.

## Repetir la batería y verificarla

```sh
python3 tools/verify_h2_branch.py
```

Una ejecución real imprimió:

```text
H2 DEMONSTRATED_SCOPED: 259 cells, 1800 VM runs; /home/danny/Development/ISyCo Git/MalbolgeLispSlop/evidence/h2_branch_v1/runs/20261018T175032Z-f10a45e6
```

La ejecución final también se probó con `python3 -O`; las comprobaciones de
aceptación siguen activas con esa opción.

Cada ejecución crea una carpeta distinta. Allí están la imagen, stderr y
stdout exactos codificados en hexadecimal, trazas del modelo, entradas,
estados, límites y hashes. No requiere paquetes Python externos; el control
T24 lee los repos hermanos `MALBOLGE-MB-DATABASE` y `MALGAMES` sin modificarlos.

| Resultado | Significado / acción |
|---|---|
| Compilador, código 0 | Imagen aceptada y emitida; ejecutar el VM para probarla. |
| Código 2 | Error de sintaxis con línea. |
| Código 3 en H2 | CFG/perfil no soportado, caso contradictorio o destino existente; revisar stderr. |
| `HALT` en el VM | Terminó; comparar también stdout con lo esperado. |
| `MAX_STEPS` / timeout | No equivale a una terminación correcta. |
| `DEMONSTRATED_SCOPED` | Pasó solo el comportamiento definido por H2. |

## Trampas

- El archivo de salida de H2 debe ser nuevo. Para repetir el ensamblado usa
  otro nombre o elimina `--out` si solo quieres comprobar el fuente.
- Usar `--loader canonical`: el formato con saltos de línea cuenta como otra
  imagen para el cargador raw.
- No mover instrucciones ni cambiar el final de la imagen a mano: EOF usa
  memoria generada por ese final. El generador y las pruebas fijan ese layout.
- Las cuatro direcciones de `echo` son copias físicas del mismo bloque.
- El ensamblador directo de H1 y el buscador `compile_module` conservan sus
  límites anteriores. H2 se selecciona desde `tools/assemble.py`.
- No ejecutar `evidence/specimen100/m6/finalize.py` sobre el árbol nuevo:
  sus hashes documentales son históricos. H2 registra el nuevo cambio sin
  reescribir aquella evidencia.

## Probar el bucle nativo (Gate H3)

Ensamblar el bucle nativo:

```sh
python3 tools/assemble.py examples/echo_loop.slop --round-trip --out build/loop.mb
```

Salida real:

```text
echo_loop.slop: guest echo_loop, 259 cells
  lowering=fixed19-scoped-loop-v1 (scoped H3; general control flow remains unsupported)
  label loop: cells 105,72
  label stop: cells 1,86
  label echo: cells 42,66,96,123,256
  walk: accepted_cells=259 verdict=ACCEPTED
  image_sha256=5c60f8d9c144c8408ca992b96a0451bb486e7e9e61356e39220e7fdbf461d917
round-trip: identical
wrote build/loop.mb (259 bytes)
```

Ejecutar iteraciones en `build/bolge19`:

```sh
python3 - <<'PY'
import subprocess
for stdin in (b'\x00', b'\x02A\x00', b'\x02A\x02B\x00'):
    r = subprocess.run(
        ['build/bolge19', 'build/loop.mb', '--loader', 'canonical', '--max-steps', '512'],
        input=stdin, capture_output=True, check=True,
    )
    print(f'{stdin.hex()}: stdout={r.stdout!r}')
PY
```

Salida real:

```text
00: stdout=b''
024100: stdout=b'A'
0241024200: stdout=b'AB'
```

Verificar la campaña completa de Gate H3:

```sh
python3 tools/verify_h3_loop.py
```

## Probar memoria nativa de guest (Gate H4)

Ensamblar el programa de store/load:

```sh
python3 tools/assemble.py examples/store_load.slop --round-trip --out build/mem.mb
```

Salida real:

```text
store_load.slop: guest store_load, 259 cells
  lowering=fixed19-scoped-memory-v1 (scoped H4; general control flow remains unsupported)
  label main: cells 103,104
  walk: accepted_cells=259 verdict=ACCEPTED
  image_sha256=1e472f836f50a6ac1f343dd108c1b5a77dc5d511e56e6fa79c8477e5131f81b0
round-trip: identical
wrote build/mem.mb (259 bytes)
```

Ejecutar almacenamiento y recarga en `build/bolge19`:

```sh
python3 - <<'PY'
import subprocess
for stdin in (b'\x00', b'A', b'\x7f', b'\xff'):
    r = subprocess.run(
        ['build/bolge19', 'build/mem.mb', '--loader', 'canonical', '--max-steps', '512'],
        input=stdin, capture_output=True, check=True,
    )
    print(f'{stdin.hex()}: stdout={r.stdout!r}')
PY
```

Salida real:

```text
00: stdout=b'\x00'
41: stdout=b'A'
7f: stdout=b'\x7f'
ff: stdout=b'\xff'
```

Verificar la campaña completa de Gate H4:

```sh
python3 tools/verify_h4_memory.py
```

## Probar aritmética nativa de guest (Gate H5)

Ensamblar el programa de adición y sustracción:

```sh
python3 tools/assemble.py examples/add_sub.slop --round-trip --out build/add_sub.mb
```

Salida real:

```text
add_sub.slop: guest add_sub, 259 cells
  lowering=fixed19-scoped-arithmetic-v1 (scoped H5; general control flow remains unsupported)
  label main: cells 105,35,50,247
  walk: accepted_cells=259 verdict=ACCEPTED
  image_sha256=97d6830d56d059f9e4a5298fb861997003c97a076134a5a5a7c031161bfaeb64
round-trip: identical
wrote build/add_sub.mb (259 bytes)
```

Ejecutar adición y decremento `(left + right - 1) mod 256` en `build/bolge19`:

```sh
python3 - <<'PY'
import subprocess
for stdin in (bytes.fromhex('0001'), bytes.fromhex('0101'), bytes.fromhex('ffff')):
    r = subprocess.run(
        ['build/bolge19', 'build/add_sub.mb', '--loader', 'canonical', '--max-steps', '512'],
        input=stdin, capture_output=True, check=True,
    )
    print(f'{stdin.hex()}: stdout={r.stdout.hex()}')
PY
```

Salida real:

```text
0001: stdout=00
0101: stdout=01
ffff: stdout=fd
```

Verificar la campaña completa de Gate H5:

```sh
python3 tools/verify_h5_arithmetic.py
```

## Verificar bloques aritméticos nativos

El sintetizador ya puede encontrar y certificar dos bloques pequeños que
reutilizan `crazy` y `rotate`. Cada bloque exige que su código, sus registros de
datos y su celda de salida estén instalados de antemano. La prueba verifica la
memoria completa, comprueba que el código se restaura y lo ejecuta dos veces en
`bolge19` con varios bytes. Esto todavía no genera el bootstrap ni compila un
programa general.

Con Z3 instalado según `requirements-dev.txt` y Zig 0.16.0:

```sh
make verify-unary
```

El comando construye el VM, vuelve a ejecutar las pruebas con Python normal y
con `-O`, reproduce ambos certificados y guarda una corrida nueva en
`evidence/unary_blocks_v1/runs/`. `REUSABLE_BLOCKS_DEMONSTRATED` acredita solo
estos dos bloques preinstalados; no es evidencia de intérprete Lisp.

