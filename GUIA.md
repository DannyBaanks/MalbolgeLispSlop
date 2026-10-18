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

**Regla de oro:** compilar o aceptar una imagen no demuestra Lisp. H2 solo
implementa el CFG de `examples/branch.slop`: selector cero termina; selector
no cero lee y devuelve otro byte. No se promete que un `.slop` arbitrario compile.

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
