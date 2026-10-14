# Datos de referencia del Myoshoji: aforos oficiales del puente Ochiai

`tokyo_calidad_agua_kanda_2005.csv` ... `_2009.csv` son los resultados de calidad del agua en aguas
publicas de la **cuenca del Kanda (神田川系)** que publica la Oficina de Medio Ambiente del Gobierno
de Tokio, tal como se descargan (Shift-JIS, sin tocar):

- pagina: https://www.kankyo.metro.tokyo.lg.jp/water/tokyo_bay/measurements/measurements/result_2009
  (y `result_2005` ... `result_2008`)
- archivo: `https://www.kankyo.metro.tokyo.lg.jp/documents/d/kankyo/measurements-result_<anio>-files-kanda`
- descargados el 2026-10-14

Cada fila es un muestreo: un dia al mes, con dos tomas (hacia las 9:00 y las 13:00). Lo que se usa del
Myoshoji (妙正寺川) es el punto **落合橋 (puente Ochiai, Shimo-Ochiai 4-16, Shinjuku)**, aguas abajo de la
camara de Kamitakada (segun el trazado del rio, el afluente Ekoda se une antes, en Matsugaoka; entre la
camara y Ochiai no se ha comprobado que no entren aportes), y dos columnas: **流量** (caudal, m3/s) y
**全水深** (calado total, m).

`velocidad_ochiai.py` los lee, quita las crecidas y un error de transcripcion (un calado de 18 m) y
escribe `myoshoji_ochiai.csv` (UTF-8). Con 119 muestreos de tiempo seco:

| | mediana | p10-p90 |
|---|---|---|
| caudal | 0.38 m3/s | 0.23-0.55 |
| calado | 0.13 m | 0.10-0.16 |
| velocidad superficial, ancho mojado 8.8 m | ~0.39 m/s | |
| velocidad superficial, ancho mojado 6 m | ~0.58 m/s | |

**Para que sirve:** el 2026-10-14 el programa midio 0.46-0.50 m/s de dia y 0.04-0.07 de noche con el
mismo nivel. Estos aforos son compatibles con el valor de dia y no con el de noche (ver
`../README.md`). **Limites:** son de 2005-2009 y de otro punto del rio; el ancho mojado en tiempo seco
no se publica y es lo que mueve el resultado entre 0.39 y 0.58 m/s; el largo de la escala de la camara
sigue siendo supuesto. Sirve para descartar un factor 5-10, no para validar un porcentaje.
