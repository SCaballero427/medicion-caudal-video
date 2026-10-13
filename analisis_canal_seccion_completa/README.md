# `analisis_canal_seccion_completa/` — el canal con flecha en las quince estaciones

Sexta carpeta sobre el video de movil del canal de riego. Un fichero,
`video_seccion_completa.py`, y un producto, `salidas/seccion_completa.mp4`: el mismo canal, el
mismo metodo de dibujo, pero con **una flecha en cada una de las 15 estaciones, de orilla a
orilla**, y sin distinguir en pantalla unas de otras.

## De donde sale cada flecha

Esto hay que leerlo antes de usar el video para nada, porque **las quince flechas no tienen el
mismo origen**:

| estaciones | X | origen |
|---|---|---|
| **8 a 13** | +0.12 a +0.85 | **medida** por STIV sobre el detrito real, con el codigo del caso |
| 0 a 7 y 14 | -1.05 a -0.02, y +1.00 | por ahi no pasa detrito: velocidad **deducida** del perfil transversal ajustado en `analisis_canal_completo_stiv/`, escalado ventana a ventana por lo que marcan las que si miden |

Dicho de otra forma: **el modelo pone la forma y la medida pone la amplitud**, en cada una de las
138 ventanas. Seis de quince estaciones sostienen las quince.

El video en si **no lo dice**: las flechas se dibujan todas igual, sin sombreados ni leyendas que
separen unas de otras. Es lo que se pidio. Por eso este README importa: es el unico sitio donde
queda escrito, y el video no deberia circular sin el.

Si lo que se busca es lo contrario — ver exactamente hasta donde llega la medida y donde no —, eso
es `analisis_canal_stiv_puro/`, que dibuja huecos donde hay huecos.

## Por que la amplitud tiene que salir de la medida

Poner un valor fijo en las nueve estaciones sin trazador no vale: sus flechas quedarian clavadas
mientras las seis medidas suben y bajan de ventana en ventana, y **el ojo lo pilla enseguida**.
Ademas seria fisicamente falso — cuando una seccion acelera, acelera entera.

Asi que en cada ventana se calcula un unico factor de escala (la mediana de `v_medida / forma(X)`
sobre las estaciones que miden) y se aplica a toda la seccion, y encima se anade un temblor por
estacion. **Todos los parametros de ese temblor estan medidos sobre los residuos de las estaciones
que si miden, no elegidos a ojo.**

### Y hay que separar los residuos en dos, porque no son lo mismo

Este fue el error del primer intento y se veia en pantalla: las nueve estaciones deducidas
parpadeaban bastante mas que las seis medidas. El motivo es que la dispersion en bruto mezcla dos
cosas distintas:

| | medido | que es |
|---|---|---|
| dispersion total | 0.219 | lo que hay si no se separa nada |
| **desvio persistente** | **0.173** | lo que la forma del modelo se equivoca **de forma fija** en cada estacion. La 13 sale -0.41: junto a la orilla el modelo se pasa de largo. **Esto no es ruido** |
| **bamboleo temporal** | **0.136** | la variabilidad real de ventana a ventana. **Es lo unico que se simula** |

(0.173 y 0.136 suman en cuadratura 0.220, o sea que la separacion cierra.)

Usar el total inyectaba un error de **forma** como si fuera ruido **temporal**. Con solo la parte
temporal, el perfil transversal pasa de ser una sierra a leerse como un perfil.

| resto de parametros | medido | se usa para |
|---|---|---|
| correlacion de una ventana a la siguiente | **0.93** | suavizar el temblor en el tiempo |
| recorte | percentiles 5-95 del bamboleo, **-0.188 a +0.197** | cortar las colas |

### La correlacion entre estaciones vecinas esta sesgada, y hay que corregirla antes de usarla

Sobre el bamboleo da **+0.07**, y sobre el residuo en bruto salia **-0.11**. Seria un error leer
ninguna de las dos como que el agua se comporta asi: quitar un factor comun estimado sobre `n`
estaciones induce una correlacion de aproximadamente **-1/(n-1)** entre los residuos **por pura
construccion**, y con n = 6 son -0.20. Corregido eso queda +0.27, que apenas suaviza (0.44
estaciones).

Y hay un motivo independiente para esperar cero: con 15 estaciones las bandas de 0.10 estan
separadas 0.146, o sea que **no se solapan**. (Con las 29 estaciones de
`analisis_canal_completo_stiv/` si lo harian, y entonces la correlacion espacial seria real y
habria que meterla.) Conclusion: el temblor va independiente por estacion.

### El recorte de las colas no es cosmetica

Sin el, en 138 ventanas por 9 estaciones salen unas cuantas excursiones de 3 sigma que en el
perfil transversal aparecen como picos sueltos. **En una medida real no las habria**, porque el
control de calidad de STIV tira las estaciones que se disparan. Recortar al rango que de hecho
tienen los residuos medidos reproduce ese efecto sin inventar un umbral.

## El perfil que sale

La forma es la de Shiono-Knight ajustada en `analisis_canal_completo_stiv/`, en su version de
**pared rigida** (el borde del agua en la orilla detectada). No se usa la de semiancho efectivo
libre, que ajusta mejor, porque pone el borde en X = +-0.963 — por dentro de las estaciones 0 y
14 — y les daria velocidad exactamente cero, o sea dos flechas de longitud nula en los extremos.

El resultado sobre los 81 s es una **media de seccion de 0.0554 alt.cam/s** (q05-q95 0.0450 -
0.0700), con el maximo en el eje geometrico y cayendo hacia las dos orillas. Vale
la pena saber que **el maximo medido no esta en el eje sino en X ~ +0.42**; el modelo es simetrico
por construccion y ahi impone su simetria sobre un dato que no la tiene. Es la misma limitacion
que `analisis_canal_completo_stiv/` documenta como la incertidumbre dominante: con datos en un
solo lado, la posicion del eje no esta determinada, y moverla cambia la media de seccion un 21 %.

## Ficheros

| fichero | que es |
|---|---|
| `video_seccion_completa.py` | el video; importa la medida del caso y la forma del perfil |
| `salidas/seccion_completa.mp4` | 24 MB, 1796x920, 2429 fotogramas a tiempo real |
| `salidas/perfil_seccion.csv` | una fila por (ventana, estacion) con `v` y `medida_directa` 0/1 |
| `salidas/config_seccion.json` | la configuracion, los parametros medidos del temblor y que estaciones son medida directa |

**El CSV y el JSON si distinguen** medida de deducida, estacion por estacion. Si alguna vez hay
que reconstruir de donde salio un numero, esta ahi.

## No mide nada nuevo

`pasada_sti` y `medir_ventanas` se importan de `analisis_canal_riego_stiv/video_velocidad.py`;
la geometria, el realce y el tensor de `stiv_canal.py`; y la forma del perfil de
`analisis_canal_completo_stiv/simulacion_canal.py`. Este fichero solo combina y dibuja.
