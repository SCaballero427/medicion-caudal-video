# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this workspace is

Not a software project — a **research workspace for image-based river discharge estimation** using
[pyorc](https://github.com/localdevices/pyorc) (pyOpenRiverCam, LSPIV). The deliverables are Jupyter
notebooks that take a video of a river and produce a discharge (caudal) in m³/s, validated against an
independent reference. It is not a git repository (only `pyorc_repo/` is).

## Layout

| Path | Role |
|---|---|
| `pyorc_env/` | Python 3.11 venv. `pyopenrivercam` **0.9.8 installed as a normal copy**, not editable. |
| `pyorc_repo/` | Upstream pyorc clone (`v0.9.8-1-g4cc2628`), **read-only reference**. Edits here do NOT affect notebooks. |
| `ngwerere/`, `USGS/` | Input data for the two finished cases, treated as read-only by the notebooks. |
| `analisis_ngwerere/`, `analisis_USGS_SMC_pyorc/` | The two live **pyorc/LSPIV** cases: pipeline notebook + `salidas/` output folder (+ `entradas/` where a case needs a pre-processed input). |
| `analisis_USGS_SMC_stiv/` | Third live case: **STIV from scratch on OpenCV, no pyorc at all**, on the same SMC video as `analisis_USGS_SMC_pyorc/`. See below. Also holds `video_velocidad.py`, which runs that STIV over the whole 22 s video. |
| `analisis_boneyard_stiv/` | Fourth live case: **STIV on an oblique camera with no geometry at all** (USGS Boneyard Creek). Stops at surface velocity in affine units — no discharge. See below. |
| `analisis_hommerich_stiv/` | Fifth live case: **metric STIV on an oblique camera that does have a full camera config** (Geul at Hommerich, NL). Reaches discharge in m³/s. Tool + README, **no notebook**. See below. |
| `analisis_bradano_stiv/` | Sixth live case: **STIV on a video the dataset delivers already orthorectified**, with its scale declared (HARMONIOUS, Rio Bradano). Stops at surface velocity in m/s — no bathymetry. See below. |
| `analisis_arrow_stiv/` | Seventh live case: **a controlled experiment on tracer seeding**, not a measurement (HARMONIOUS, River Arrow). Same camera and framing, seeded vs unseeded. See below. |
| `analisis_canal_riego_stiv/` | Eighth live case: **STIV on a WhatsApp phone video with no geometry and no field data at all** (irrigation canal). The lowest-information case in the workspace. Stops at surface velocity in affine units. Tool + README, **no notebook**. See below. |
| `analisis_canal_lejano_stiv/` | **Not a case, an experiment** on the one above: how far up the canal STIV reaches before aliasing takes over. Imports its method wholesale. See below. |
| `analisis_canal_filtro_adaptado/` | **Not a case, the third experiment** on the canal: track-before-detect over the whole residence window, plus the controlled test showing the far field is erased by *resolution*, not by the encoder. See below. |
| `analisis_canal_completo_stiv/` | **Ninth live case**: STIV on the canal video with error bars and three estimators, plus a Shiono-Knight model that extrapolates the 64 % of the width that has no tracer. Ends in a *simulation*, clearly labelled. See below. |
| `analisis_canal_stiv_puro/` | **Not a case, the un-modelled counterpart** of the one above: one video, nothing but measured STIV — arrows, the STI each arrow comes from, and holes where nothing measures. Imports the whole measurement. See below. |
| `analisis_canal_seccion_completa/` | **Not a case, a presentation**: arrows at all 15 stations, bank to bank, with measured and deduced ones drawn identically. The video carries no on-screen caveat *by request*; the README, CSV and JSON do. See below. |
| `analisis_kurome_directo_stiv/` | **Tenth live case, the first in real time**: STIV on YouTube live streams of Tokyo river-monitoring cameras, one preset per camera (`--camara myoshoji`, the default, or `kurome`). Starts measuring the moment it is launched. Own `.venv`, tool + README, **no notebook**. See below. |
| `RIVeR-STIV_1.0/` | The RIVeR desktop app (MATLAB-compiled `.exe` + bundled `ffmpeg`) plus `RIVeR_Example/`. **Staged data for a case that does not exist yet** — see below. |
| `STIV_desde_cero.ipynb` | From-scratch STIV implementation — a *different method*, not superseded (see below). |
| `Prueba_Castor_River.ipynb` | Stub for the next dataset, **cannot run**: its data was never downloaded (see below). |
| `Notebook_Analisis_Ngwerere.ipynb` | The original exploratory Ngwerere notebook, superseded by `analisis_ngwerere/`. Runs from the workspace root. |
| `datasets_prueba_pyorc.xlsx` | Ranked backlog of candidate datasets to process next. |
| `pixel_locator.py` | Standalone OpenCV tool for picking GCP/AOI pixel coordinates off a video. |
| `estabilizar_video.py` | Standalone tool: video in → stabilized video out, **via pyorc's own `cv` functions** (see below). |
| `estabilizar_stiv.py` | Same job, **pure OpenCV, no pyorc**, for the STIV case. Not a duplicate — see below. |
| `convertir_a_mp4.py` | Standalone tool: any video → viewable `.mp4`. Lossy, for looking at only. |
| `test_pyorc.py`, `video_test.py` | Throwaway 5-line probes (print the pyorc version / a video's fps). Not part of anything; `video_test.py`'s path is dead. |

`pyorc_repo/examples/*.ipynb` are the upstream tutorials the pipeline notebooks are derived from and
validate against; they have uncommitted local modifications (plus untracked `ngwerere.json`,
`ngwerere.jpg`, `ngwerere_camconfig.jpg`).

## Running

```powershell
.\pyorc_env\Scripts\Activate.ps1
jupyter lab
```

Notebooks are meant to be run top-to-bottom from their own directory. There is no test suite, linter,
or build for the workspace itself. To run pyorc's own tests (only relevant when investigating library
behaviour): `cd pyorc_repo; python -m pytest tests/test_velocimetry.py::test_name`.

The venv is Python 3.11.0 with `pyorc` 0.9.8, `ffpiv` 0.2.1, OpenCV 4.13.0, xarray/dask 2026.7.0,
numpy 2.4.6, pandas 3.0.3, scipy 1.17.1 — a *new* stack under an old library, which is why some of
the version-sensitive gotchas below (the even `window_size`, the H.264 writer) exist.

`pixel_locator.py` is run on its own (`python pixel_locator.py`) — it opens a file dialog, lets you
click points on the first frame, and writes `<video>_points.csv` plus an annotated PNG **into the
current directory**. This is how the `>>> AJUSTABLE <<<` pixel coordinates get produced; the stray
`GOPR3225_Trim_points.csv` and `GOPR3225_Trim_first_frame_annotated.png` in the root are its output,
left over from the abandoned RIVeR attempt.

`estabilizar_video.py` takes a video and writes a stabilized copy, so a shaky video is corrected
**once** instead of on every notebook run. It calls pyorc's own `cv.get_ms_gftt` / `cv.transform`,
so the result is what `stabilize=` would have produced in-process. `--poligono` encloses the
*water*; everything outside is the fixed reference. Run from the workspace root:

```powershell
python estabilizar_video.py USGS/Video/SMC_D_RC_022_08172020_AC.mp4 `
    analisis_USGS_SMC_pyorc/entradas/SMC_estabilizado.mkv `
    --poligono "0,420 3840,420 3840,1500 0,1500" --fin 249
```

`--inicio`/`--fin` are frame *indices*, both inclusive (`n = fin - inicio + 1`), so 250 frames is
`--fin 249`, matching the script's own docstring.

Default codec is **FFV1 (lossless), not mp4v** — deliberately. Writing an intermediate video adds a
re-encode that the in-process path never had, and mp4v costs 2.1 grey levels of mean error in the
AOI, ~10% of the tracer pattern's own contrast, which is exactly what PIV correlates. FFV1 re-reads
bit-identical at ~5x the size (1.1 GB vs 220 MB for 250 4K frames). The script verifies both
fidelity and shake reduction on a sample and prints them.

`estabilizar_stiv.py` does the same job for the STIV case with **only OpenCV**, so that chain has no
pyorc dependency anywhere. It is not a copy of the other script: it detects 600 GFTT features once on
frame 0 and tracks them **directly to every frame** (LK seeded with the previous position), rather
than chaining frame-to-frame, so alignment error does not accumulate. Measured on the same 250
frames, it beats the pyorc-based path: shake 0.50 → **0.02 px median (27x)** vs 0.51 → 0.10 (4.9x),
with a 0.27 px fit residual and 25.6 px of total drift removed. ~135 s, 1.14 GB.

```powershell
python estabilizar_stiv.py USGS/Video/SMC_D_RC_022_08172020_AC.mp4 `
    analisis_USGS_SMC_stiv/entradas/SMC_estabilizado_stiv.mkv `
    --poligono "0,420 3840,420 3840,1500 0,1500" --fin 249
```

Because FFV1-in-MKV is awkward to play, `convertir_a_mp4.py` makes a viewable copy
(`..._previsualizacion.mp4` next to the original, `--escala 0.5` to shrink further). That copy is
**for looking at, never as pipeline input** — feeding it back to the notebook reintroduces exactly
the noise FFV1 was avoiding. Note this environment cannot write H.264 (its bundled OpenH264 DLL is
the wrong version), so the fallback is mp4v.

## The pipeline (same 6 parts in each `analisis_*` notebook)

0. **Rutas** — all uppercase `DIR_*` / `ARCHIVO_*` / `SALIDA_*` constants are defined here; every
   artifact goes to `salidas/`. Both notebooks use plain relative paths (`../ngwerere`, `../USGS`,
   `salidas`) and so **must be run from their own directory**. In the SMC pyorc notebook Part 0 holds
   *only* paths: the geometry constants live in the part that uses them and the gauging numbers do
   not exist until Part 7.
1. **Video** — `pyorc.Video(..., start_frame, end_frame)`, one RGB frame for eyeballing.
2. **GCPs** — pixel `src` ↔ real-world `dst`, plus `h_ref` and `z_0`.
3. **CameraConfig** — `set_bbox_from_corners()`, `resolution`, `window_size`, then `to_file(JSON)`.
4. **PIV** — reload the config *from the JSON* (deliberate: proves the file is self-sufficient), then
   `get_frames() → frames.normalize() → frames.project(method="numpy") → frames.get_piv()` →
   `to_netcdf(piv_crudo.nc)`.
   **4b. Masking** — a fixed sequence of `ds.velocimetry.mask.*(inplace=True)` calls → `piv_filtrado.nc`.
   Order matters, because with `inplace=True` each mask conditions the next: value-wise (`corr`,
   `minmax`) → temporal (`rolling`, `outliers`, `variance`) → whole-series/neighbourhood (`count`,
   `window_mean`).
5. **Discharge** — `ds_mask.velocimetry.get_transect(...)` → `.transect.get_q(v_corr=…,
   fill_method="log_interp")` → `.transect.get_river_flow()` → `transecto_caudal.nc`. `v_corr` is
   0.9 in Ngwerere (pyorc's default) and **0.92** in the SMC pyorc case, to match the STIV case.

The SMC pyorc notebook adds **6. Recursos** and **7. Comparación**, mirroring the STIV case; its
Part 5 reports Q and the quantile band but never the reference, and `caudal_resumen.csv` is written
in Part 7. Ngwerere still ends at Part 5.

`get_frames`, `normalize` and `project` are lazy and return dask-backed arrays. **`get_piv` is not**,
despite its own docstring promising results "in a lazy dask.array form" — on 0.9.8 it returns numpy
and computes on the spot, so it is where both the time and the memory peak land, and the subsequent
`to_netcdf` is nearly free. Measured on the SMC case (250 4K frames, `salidas/benchmark_recursos.csv`):
`get_piv` 74.3 s / 14.4 GB peak vs `to_netcdf` 0.13 s / 2.0 GB. `normalize + project` (which only
*builds* the graph) is the second most expensive block at 53.9 s. Don't reason about cost from the
docstring; the SMC notebook measures it every run.

**The workspace's own text still repeats that same wrong claim in two places** — `benchmark.py`'s
module docstring ("la linea que dispara el trabajo de verdad es `to_netcdf`, no `get_piv`") and the
Part 4 comment in the Ngwerere notebook ("`to_netcdf` es lo que dispara realmente el calculo"). Only
the SMC notebook's comment was corrected after the measurement. Trust the CSV, not the prose.

`get_piv` and `get_q` mutate/return datasets in place — `copy.deepcopy` before reusing one. The SMC
notebook used to sweep `v_corr` in a loop that did exactly this; the sweep is gone (see below), so
the only surviving `deepcopy` is the one guarding `ds` from the masks.

## The two cases differ in ways that matter

| | Ngwerere | USGS Sile Main Canal |
|---|---|---|
| Notebook | `analisis_ngwerere/Ngwerere_pipeline_completo.ipynb` | `analisis_USGS_SMC_pyorc/SMC_pipeline_completo.ipynb` |
| Camera | fixed, oblique, 1920×1080 | drone hovering, nadir, 4K |
| GCPs | 4 RTK points | **2 points** on the waterline → pyorc's `is_nadir` mode |
| CRS | `crs=32735` (UTM 35S) | `crs=None`, local metres, scale from the known 1.8288 m channel width |
| Bathymetry | 27 surveyed points, `x,y,z` in UTM | synthetic: rectangular box, 13 gauging stations |
| `resolution` / `window_size` | 0.01 m/px, 25 px | 0.004 m/px, 32 px |
| `end_frame` | 125 | 250 (`N_FRAMES`) |
| Stabilization | in-process, `stabilize=` polygon passed to `pyorc.Video` (as upstream does) | **essential** — done up front by `estabilizar_video.py`, so the notebook passes no `stabilize=` |
| Resource benchmarking | no | yes, via `analisis_USGS_SMC_pyorc/benchmark.py` |
| Angle mask | computed then *discarded* (on purpose) | actually applied (`inplace=True`) |
| Reference | 0.164 m³/s (upstream example) | 1.4362 m³/s (independent ADV FlowTracker gauging) |
| Reference used | throughout, to reproduce the published number | **only in Part 7**, once, after everything is fixed |
| Result achieved (median) | **0.1672 m³/s**, +1.9% | **1.4507 m³/s**, +1.0% |

The quantile spread (0.05→0.95) is the honest error bar: on SMC it runs −5.4% to +9.7%, and a rerun
that lands in that band is working. Ngwerere's `caudal_resumen.csv` is the full quantile table; the
SMC pyorc one is now a `concepto,valor,unidad` summary (same shape as the STIV case) carrying the
median, both tails, the two uncertainties and the measured-vs-filled vertical counts, with the
per-quantile table printed in Part 7 and the per-vertical detail in `perfil_transecto.csv`.

## Conventions to preserve when editing notebooks

- **Prose and comments are in Spanish, without accents**, in the `analisis_*` pipeline notebooks.
  Comments explain *why* a value or argument was chosen, not what the line does. Match that register;
  it is the point of these notebooks. (`STIV_desde_cero.ipynb` is the exception — Spanish *with*
  accents, written as a tutorial that derives a method rather than applies one; so are the older root
  notebooks, which predate the convention.)
- Cells that need human judgement are flagged `>>> AJUSTABLE <<<` (GCP pixel rows, AOI corners,
  stabilization polygon, `v_corr`). Do not silently change these values.
- Known deviations from upstream are documented in-place rather than fixed. Two live examples:
  Ngwerere calls `mask.angle()` **without** `inplace=True` on purpose, to reproduce the published
  0.164 m³/s (applying it would push the median to ~0.174); and no notebook calls `set_encoding()`
  before `to_netcdf`, to avoid quantizing values. If you "fix" either, the reference comparison breaks.
- Each notebook ends with a section listing its known limitations and its equivalence table to the
  upstream examples — keep them in sync when the pipeline changes.

## `analisis_USGS_SMC_pyorc/` — LSPIV configured a priori, compared once

`SMC_pipeline_completo.ipynb` was rewritten (2026-07-29) to the same discipline as the STIV case:
**every case-dependent value is chosen from the video, the channel geometry or pyorc's own default,
and the gauging is not opened until Part 7.** 36 cells, structure 0 rutas → 1 video → 2 GCPs/escala
→ 3 CameraConfig+AOI → 4 PIV → 4b máscaras → 5 sección+caudal → 6 recursos → 7 comparación (and
fin). Figures are `fig1_`…`fig12_` in creation order.

Design rules that are deliberate and worth not "fixing":

- **The `v_corr` sensitivity sweep is gone.** It tried 0.85/0.90/0.95/1.00 and printed each one's
  distance to the gauging, which is tuning against the reference. `V_CORR = 0.92` is now fixed in the
  Part 5 `>>> AJUSTABLE <<<` box on the grounds that it is what the STIV case uses on this video.
  Part 7 still reports the **implied** `v_corr` from the ADV (0.922 over the 8 measured verticals)
  as a diagnostic, explicitly labelled as something that must not be fed back. That it lands on the
  0.92 chosen a priori is a coincidence worth *not* reading as calibration.
- **`Q_AFORO`, `AREA_AFORO`, `V_MEDIA_AFORO` and `V_ADV` exist only inside Part 7.** They used to sit
  in Part 0 and the ADV curve used to be drawn on the Part 5 transect figure; both are gone.
- **The section is used as the CSV gives it.** The justification is no longer "so it matches the
  published 1.4362 m³/s" but "it is the geometry the dataset describes"; the physical 1.962 m² box is
  drawn beside it and never enters a calculation. Same numbers, honest framing.
- **Every configurable constant sits in an `>>> AJUSTABLE <<<` box at the head of its part**, as in
  the STIV notebook: Part 2 `COLUMNA_GCP`/`FILA_AGUA_*`/`ANCHO_CANAL`, Part 3
  `RESOLUCION`/`VENTANA_PIV`/`COLUMNA_INI`/`COLUMNA_FIN`/`ESQUINAS_AOI`, Part 4 `N_FRAMES`, Part 5
  `PROFUNDIDAD`/`V_CORR`, Part 7 the validation data.
- **fig2 verifies the scale instead of asserting it** — contrast-stretched greyscale zooms *plus* the
  brightness profile along `COLUMNA_GCP`. It shows the upper waterline as a clean step at row 438 and
  the lower one as an ~85 px shadow ramp with no step at all. That ramp is the case's real geometric
  uncertainty and the figure exists so it can be argued about.
- `salidas/config_pyorc.json` freezes the whole configuration and `salidas/perfil_transecto.csv`
  records, vertical by vertical, whether the velocity was measured or filled by `log_interp`.

### Shared configuration with the STIV case

The two SMC notebooks now read **the same numbers for everything that is not method-specific**, so
that comparing LSPIV against STIV measures the algorithm and not the setup. The notebook's own intro
carries this table; keep both in sync:

| Constant | Shared value |
|---|---|
| `FILA_AGUA_SUP`, `FILA_AGUA_INF` | 438 and 1466 → 1028 px → **1.7790 mm/px** |
| `ANCHO_CANAL` | 1.8288 m |
| `COLUMNA_INI`, `COLUMNA_FIN` | 600 and 3400 |
| `N_FRAMES` | 250 |
| Section chainage and depth | straight from `Station_Stage_SileCanal.csv`, **area 1.8026 m²** |
| `V_CORR` (`ALFA` there) | 0.92 |

Not shared, because they are method-specific: the stabilized video (one per case, different script),
`RESOLUCION` and `VENTANA_PIV` (LSPIV only), the AOI row inset of 12/10 px (interrogation windows
must not touch concrete), and STIV's `ANGULO_FLUJO`/`V_ESPERADA`/tensor parameters.

Two things changed when the STIV configuration was adopted (2026-07-29): the scale moved from
436/1480 (1.7517 mm/px) to 438/1466, +1.6% on every velocity; and the section chainage stopped being
regenerated from `PASO_ESTACION = 0.1524` and is read from the CSV verbatim, so the area went
1.7988 → 1.8026 m². `PASO_ESTACION` no longer exists in the notebook.

`FILA_AGUA_INF` was found at **1520** when the rewrite started, contradicting the notebook's own
prose and this file (both of which said 1480) — and 1520 is precisely the "bottom edge of the shadow
band" reading that the Part 2 text warns costs 8% of scale. It is now 1466, from the STIV case.
Independent checks during the rewrite (brightness ramp arithmetic, per-row inter-frame motion) both
put the true waterline nearer **row 1430**; that remains an open question on an `>>> AJUSTABLE <<<`
value, not a settled correction.

## `analisis_USGS_SMC_stiv/` — STIV from scratch, same video, no pyorc

`SMC_STIV_pipeline.ipynb` measures discharge on the **same SMC video** as the pyorc case, but
implements **STIV** (Space-Time Image Velocimetry) directly on OpenCV. pyorc is never imported. It is
the controlled comparison: same video, same reference, different algorithm. Input is
`entradas/SMC_estabilizado_stiv.mkv` (1.1 GB, regenerate with `estabilizar_stiv.py`).

**It deliberately mirrors Ngwerere's shape, not the SMC pyorc one:** Part 0 rutas → 1 video → 2 scale
+ section geometry → 3 STI construction → 4 structure tensor → 4b QC and gap fill → 5 discharge →
6 resources → 7 comparison (and fin). 29 cells. `GUIA_DEL_NOTEBOOK.md` in
that folder explains every part in plain Spanish, including what to look at in each figure and what
is safe to change.

**There are no auto-detectors.** Every case-dependent value is a `>>> AJUSTABLE <<<` constant in a
commented box at the **top of the first code cell of the part that uses it** — Part 2 holds the
waterline rows, channel width, column range and flow angle; Part 3 `V_ESPERADA` and `N_FRAMES`;
Part 4 the three tensor parameters; Part 4b `COH_MIN_ESTACION`; Part 5 `ALFA`; and Part 7
the gauging references, which therefore do not exist as variables before the final cell. Values
taken from the data release are tagged *(obtenido del dataset)* in the comment. The notebook's only
job around them is to *draw* them so they can be checked — fig2 draws the search lines at their real
`ANGULO_FLUJO` tilt, plus contrast-stretched greyscale zooms of the two waterlines, because in colour
the shadowed lower wall is indistinguishable from water. An earlier version measured the waterline
by motion, swept the flow angle for maximum coherence and validated `DS` against a synthetic
translation; all three were
removed as over-fitted to this one video. The values they produced (rows 438/1466, angle −1.0°,
DS=18) are what the constants now hold, so the result barely moved.

It carries its **own copy of `benchmark.py`** (same API as the pyorc one, different docstring), and
Part 6 measures every expensive block. The result is worth knowing before optimising anything:
**building the STI — one single pass over the video — is ~100% of the measured time; the structure
tensor across all 13 stations takes 0.03 s.** 250 4K frames at 150–320 ms each; 38 s warm, up to
80 s with a cold page cache. Peak RSS is **870 MB vs the pyorc notebook's ~14 GB** on the same video —
STIV never holds more than one frame, LSPIV holds the whole projected video.

Design rules that are deliberate and worth not "fixing":

- **The scale comes from two hand-read rows**, 438 and 1466 → 1028 px for 1.8288 m → **1.7790 mm/px**.
  The pyorc notebook now reads the same two rows (it used to read 436/1480, 1.6% coarser), so the two
  cases no longer disagree on scale. Brightness thresholding does *not* work on the lower wall,
  whose shadowed inner face looks like dark water — hence the contrast-stretched greyscale zooms in
  fig2, which are the intended way to verify the two rows.
- **`DS` (the STI sampling step) is derived from `V_ESPERADA`**, not typed directly: `DS = V·Δt/e`
  ≈ 18 px/frame, so streaks land at 45°, where `δu/u = δθ/(sinθ·cosθ)` is minimised. At 1 px/sample
  they would sit at 87°, where the same angular error weighs 19x more. The curve is flat near 45°, so
  a 30% error in `V_ESPERADA` barely matters.
- **The antialias blur is isotropic on purpose.** σ = DS/2 is required before decimating, but being
  2D it also averages ~3.5 cm *across* the line, giving it an effective width that kills small-scale
  turbulence. Filtering only along the line was tested: coherence drops 0.97 → 0.87. Don't "fix" it.
- **The structure tensor runs on 64×64 blocks with 50% overlap**, combined by a coherence-weighted
  median — a global tensor lets one bright patch dictate the answer.
- **The section is read from `Station_Stage_SileCanal.csv`** (`Progresiva`, `Prof`), and the verticals
  with `Prof == 0` are imposed v=0 (zero depth + no-slip), never measured; at the waterline the tensor
  returns garbage (tens of m/s).
- Stations below **coherence 0.70** are rejected and refilled by **plain linear interpolation** over
  the accepted stations plus the imposed zeros at the walls — one `np.interp` call, no parameters.
  There is deliberately **no wall friction model**: an earlier version used the log wall law with
  `K_S = 1 mm` for smooth concrete and it was removed as unnecessary machinery. Stations 1 and 11
  always fail — the wall-adjacent bias, same weakness as the pyorc case. Station 11 measures
  1.40 m/s, faster than mid-channel, which is what the QC is there to catch.

Result: **Q = 1.2221 m³/s vs the 1.4362 m³/s ADV gauging, −14.9%.** The error is not in the tensor:
the profile *shape* is reproduced without being imposed, it tracks the USGS PIVlab profile, and the
failing verticals are exactly the ones coherence rejects on its own. Two things account for the gap.
The larger is the **linear fill**: it hands the two wall stations 0.36 and 0.41 m/s where the ADV
measured 0.63 and 0.74, because the real transverse profile stays high until very close to the
concrete and then drops — a straight line to zero cannot do that. The log-law version reached
1.3168 m³/s (−8.3%) precisely because it modelled that shape; the current number is the honest cost
of filling without a model. The second is **α**: the notebook uses the USGS-standard **0.85**, fixed
before looking at any reference, while the ADV implies **0.93** over the 9 measured verticals. The
Part 7 statistics (bias, RMSE, implied α) are computed on those 9 only — including the filled ones
would measure the fill, not the method. `salidas/config_stiv.json` freezes the whole configuration.

**The comparison happens once, in Part 7, and nothing is retuned afterwards.** That is the point of
the notebook, not an oversight — if α were tuned to match, there would be no validation left. Don't
"improve" the result by changing α, the scale, or the QC threshold after the fact.

### `video_velocidad.py` — the same STIV over the whole 22 s

Case-specific standalone tool (run from the case folder, ~9 min) that repeats the notebook's STIV in
sliding 150-frame windows over **all 672 frames** instead of the notebook's 250, and renders
`salidas/velocidad_tiempo_real.mp4` (73 MB, 671 frames, 1920×844, real-time playback). Per-window
series go to `salidas/velocidad_ventanas.csv`. Same name and same idea as the Boneyard tool, but
**one panel, not two**: the view is nadir, so the scale is already uniform and there is nothing to
rectify — the frame *is* the water plane. It draws only what was asked of it: the 13 search lines,
one arrow per vertical, and the value in m/s, plus a footer with t, the section median and the
instantaneous Q.

- **It duplicates the notebook's constants** (waterline rows, channel width, column range, flow
  angle, `V_ESPERADA`, the three tensor parameters, `COH_MIN_ESTACION`, `ALFA`) — change one, change
  both. It reuses `estabilizar_stiv.py`'s `estimar_transformaciones` by importing it from the
  workspace root, so the chain still has no pyorc anywhere.
- **No 3 GB intermediate video.** The notebook's input `.mkv` only covers 250 frames. Here the
  stabilization is estimated once and then applied as a *coordinate change*, twice over: composed
  into the STI sampling map for measuring, and applied to the line/arrow endpoints for drawing. So
  nothing is ever warped — the output is the original video untouched, with the overlay following
  the canal as the drone drifts. Measured drift over the full video: **46.5 px**, twice the 25.6 px
  of the first 250 frames.
- **One QC constant the notebook does not have**: `V_MAX_FISICA = 3 × V_ESPERADA` = 2.85 m/s.
  Measuring in 105 short windows instead of one long one, station 11 twice returned ~7 m/s *with
  coherence above 0.70* — a standing wave the coherence test cannot tell from a tracer streak. The
  bound comes from the a-priori estimate, not from any reference, and it fired on 2 of 1155
  station-windows. Without it two windows read Q = 2.82 and 2.43 m³/s.

Result over the full video: **Q median 1.4493 m³/s, q05–q95 1.4027–1.4889, range 1.393–1.506** —
against the notebook's 1.4475 on the first 250 frames and the 1.4362 ADV gauging. That the whole
22 s agrees with the first 8 s to 0.1% is the useful outcome: the notebook's window is not a lucky
one. Station-by-station acceptance also matches — 1 and 11 are the wall-adjacent failures, accepted
in 25% and 0% of windows respectively.

## `analisis_boneyard_stiv/` — STIV on an oblique camera with no geometry

`Boneyard_STIV_pipeline.ipynb` (37 cells) measures surface velocity on the USGS Boneyard Creek at
Urbana IP-camera dataset (doi:10.5066/P9VZ6VYM, 4.7 GB, **outside the workspace** at
`C:\Users\Sergio\Desktop\Boneyardcreek`). pyorc is never imported. Structure mirrors the SMC STIV
case: 0 rutas → 1 dataset/triaje → 2 geometría → 3 STI → 4 tensor → 4b QC → 5 perfil → 6 recursos →
7 contraste → 8 vídeo, `fig1_`…`fig8_`.

**It deliberately stops short of discharge, and that is the result, not a failure.** The release
publishes 61 videos plus `GH` and `Q` per video and *nothing else*: no GCPs, no channel width, no
cross-section, no camera config. Without a length there are no metres; without a section there is
no area.

What makes it still worth having is one geometric fact:

> A homography that sends the water plane's true horizon to infinity is, with respect to that
> plane, an **affinity**. An affinity scales all lengths in a given direction by one constant. The
> flow is streamwise everywhere, so **velocity is correct up to a single global constant regardless
> of the assumed focal length.**

So `FOCAL = 640` is cosmetic — it only changes the aspect ratio of the rectified view — and the
only thing that matters is the horizon, which comes from the streamwise vanishing point
`V1 = (653.0, −30.9)`, RANSAC-fitted to the masonry courses of *both* walls (that both sides agree
is the check that it is real). Results are reported in **camera heights per second**, a unit that
is stable against `ESC` and fps and becomes m/s the day a width appears.

Design rules that are deliberate and worth not "fixing":

- **Zero roll is an assumption, not a measurement.** The vertical vanishing point was attempted and
  returned nonsense — what LSD calls "vertical" here is irregular stone edging — so the horizon
  rests on the camera being level under a horizontal walkway. Documented as the case's geometric
  hypothesis.
- **Lens distortion is not corrected.** A plumb-line k1 sweep was tried and *failed*: it scored
  total LSD segment length, and a wild over-correction (k1 = −0.38) smears the periphery into
  perfectly straight radial streaks, so the metric rewarded the artifact. It was dropped in favour
  of the self-validating check — if distortion mattered, the channel would come out bowed in fig3.
  That is a visual check, not a bound.
- **Calibration video ≠ measured video.** Geometry comes from a low-stage video (`20180907-162000`,
  walls exposed); measurement from the highest daylight flow (`20180610-082000`, GH 14.88 ft,
  Q 368 cfs). Legitimate because a horizontal plane's horizon does not depend on its height — only
  the unknown global constant changes.
- **No stabilization, and it was measured, not assumed.** Inter-date drift is ~1.3 px over 18
  months (with a clean ~1 px step between 2017 and 2018); intra-video shake is 0.02–0.06 px median.
  Compare SMC, which needed 25.6 px removed and a 1.1 GB pre-stabilized `.mkv`.
- **The QC filter is temporal contrast, not coherence — and this is the case's real lesson.**
  Stations on the walls return **coherence 0.74–0.76 with velocity exactly 0**, among the best
  scores in the section, because a static structure is a perfectly coherent zero-slope streak. A
  coherence threshold *passes* them. `CONTRASTE_MIN = 1.5` sits in a measured factor-5 gap between
  wall (≤0.94) and water (≥4.56). `COH_MIN` is 0.40, not the SMC 0.70, because the tracer here is
  fine foam.
- **Rejected stations are not filled.** No section to integrate, so filling would only invent data.
  Contrast with the SMC STIV case, where linear fill is most of the −14.9% error.
- **Only the near half is measured** (`YMAX = 2.80`). Near the horizon one image pixel covers so
  much ground that resampling destroys texture — measured, phase-correlation response falls 0.78 →
  0.32. `DS = 5` is derived from the measured 4.7 px/frame so streaks land at 43°, not typed in.
- The specular sky reflection is removed by **per-position temporal normalization** (subtract each
  position's time-mean, divide by its time-std). Parameter-free, and it works because the
  reflection is static in space while the water is not.

Result: **v = 0.2427 camera heights/s** (q05–q95 0.2244–0.2685) over 15 accepted stations of 21,
against a reference of Q = 368 cfs / GH = 14.88 ft that **is never used to tune anything**. Part 7
tabulates what camera height would close the discharge under an assumed rectangular section, and
labels it explicitly as an order-of-magnitude check, not a calibration.

`video_velocidad.py` is a case-specific standalone tool (run from the case folder, ~2 min) that
repeats the same STIV in sliding 96-frame windows over the whole video and renders
`salidas/velocidad_tiempo_real.mp4` (139 MB, 861 frames, 1845×678, real-time playback), plus
`salidas/velocidad_ventanas.csv` with the per-window series. **It duplicates the notebook's geometry
constants** — the notebook's intro carries the shared table; change one, change both.

It was rewritten (2026-08-06) to the same visual language as the SMC STIV tool, keeping the two
views because here they are not redundant: the camera is oblique, so measurement happens in the
rectified panel and the original is what lets you judge that the stations sit where you think.
Both panels now carry the **same overlay** — the 21 search lines, one arrow per station and its
value. The arrow in the original view is not a rotated copy: its tip is projected through `o2i`,
so perspective tilts and foreshortens it on its own. Two things changed besides:

- **It renders in real time.** One output frame per input frame at the original fps, each taking
  the measurement of the window whose centre is nearest, instead of the old one-frame-per-window at
  `fps/PASO`, which played ~3x fast and misrepresented how quick the water is.
- **The instantaneous-profile and time-series plots are gone**, traded for two large video panels.
  The numbers they showed are in `velocidad_ventanas.csv` and in the notebook's own figures.

Section median over the whole video: **0.2428 camera heights/s**, against the notebook's 0.2427 on
its 250-frame window. Station acceptance matches the notebook too — 0, 1, 2, 19 and 20 are rejected
outright by the contrast/coverage test (wall or out of field), 16 of 21 survive.

### `stiv_interactivo.py` — the same STIV with the geometry put in by hand

Added 2026-08-06 after the vanishing-point rectification was judged wrong. It runs the same STIV
but **replaces the whole automatic geometry chain**: no `V1`, no `FOCAL`, no horizon. The user drags
four corners of a quadrilateral that is a real-world rectangle on the water surface, and
`getPerspectiveTransform` does the rest. If the quad is wrong the channel comes out bent in the
rectified panel, which is the check the vanishing-point path never had.

It is a three-step wizard (TAB forward, BACKSPACE back, SPACE pauses), and **the video plays live in
both panels throughout** — on a frozen frame you cannot see whether the rectification distorts the
water's motion, which is the thing being measured. Step 1 the rectification and the real dimensions,
step 2 the section line, step 3 the stations (drawn numbered in both views) and the STI length, DS,
window and QC thresholds. `p` measures one window at the current frame and draws the arrows without
paying for the whole video; it also prints the **median streak angle**, which is how DS gets tuned
(STIV loses precision away from 45°). Every step is gated: steps 2 and 3 cannot move the quad.

- **It produces m/s, not affine units**, because the quad has real dimensions. The starting value is
  the **~6 m** channel width given by hand — the only metric datum this case has. The streamwise
  length must be estimated too even though nobody measured it: it sets the scale *along the flow*,
  which is the direction velocity is measured in. `u` gives up on metres and returns to camera
  heights.
- **Sampling no longer needs a full-frame warp per station**: the STI map is built in rectified
  coordinates once and read with `cv2.remap` off the warped frame, so the STI length is a free
  parameter rather than the height of the rectified canvas.
- The configuration round-trips through `salidas/config_stiv_manual.json`; `--sin-interfaz` reruns
  it with no window. `salidas/config_stiv_manual.json` currently holds a **starting point seeded
  from the old vanishing-point homography** (6.0 × 4.14 m), meant to be dragged, not trusted.
- Same visual language as `video_velocidad.py` for the output video, written to
  `salidas/velocidad_manual.mp4` plus `velocidad_ventanas_manual.csv`.

Smoke-tested through `--sin-interfaz` on 140 frames (19 of 21 stations admissible, median
0.726 m/s under that seed geometry); **the interactive window itself has not been exercised** — it
needs a person at the mouse.

Two things that are measured here and worth reusing: the tensor is **0.1% of the runtime** (same
asymmetry as the SMC STIV case), and the rectification `warpPerspective` is **42% of the read
block** (1.11 s → 1.92 s per 250 frames), which is the only new cost this case introduces.

Known limits, all listed in the notebook's closing section: no discharge, zero roll assumed, no
distortion correction, far field unmeasurable, wall-adjacent stations weakest (the profile maximum
sits next to the left bank, which is physically suspicious and probably wall contamination), and
**only one video processed**. The dataset's real value is the other 49 daylight videos.

### The dataset triage matters

11 of the 61 videos are unusable: at night the camera switches to infrared — greyscale, out of
focus, water drops on the lens. `salidas/triaje_videos.csv` records brightness, saturation and
sharpness per video; saturation is the clean discriminator. **The two highest flows in the whole
release (446 and 470 cfs) are night-time and are lost.** The daylight range is 94 → 368 cfs.

## STIV_desde_cero.ipynb is not part of the pipeline

It reimplements **STIV** (Space-Time Image Velocimetry) from scratch to contrast it with the LSPIV
that pyorc uses: sample a 1D line along the flow direction for every frame, stack those lines into a
space-time image, and recover velocity from the slope of the streaks via the **structure tensor**
(eigenvector of the smaller eigenvalue). pyorc is used *only* for `load_camera_config`,
`project_points` and `unproject_points` — never for the velocity itself.

It uses **relative paths** (`ngwerere/...`), so unlike the pipeline notebooks it must be run from the
workspace root. Its optional last cell cross-validates against `ngwerere/ngwerere_piv.nc`.

It is **not** the same thing as `analisis_USGS_SMC_stiv/`: that one is a full discharge case on the
SMC drone video with its own stabilization, QC and validation against a field gauging, while this is
a tutorial on the Ngwerere river that stops at the velocity and still leans on pyorc for the
projection helpers.

## Staged but not started: RIVeR-STIV and Castor River

Two would-be third cases have data or a stub in the tree but **no working notebook**. Don't assume
from the folders that a pipeline exists.

- **RIVeR-STIV.** `RIVeR-STIV_1.0/RIVeR_Example/` holds a complete case: `GOPR3225_Trim.mp4` (191 MB,
  fixed oblique GoPro), 227 extracted JPGs, `distances.xlsx` (6 measured distances → `crs=None` local
  metres), `Station_Stage.csv` (24 points as `Progresiva,Prof` — chainage/depth, **not** `x,y,z`, so
  Part 5 would need real adapting), and RIVeR's *own* STIV answer for the same video in
  `New_project.rvr` + `CS_0/{discharge,stage,velocity}.png` — a ready-made independent reference.
  There was a `RIVeR-STIV_Example_pipeline.ipynb` (a half-adapted copy of Ngwerere); it and its
  `analisis_*` folder are **gone from the workspace**. Only `GOPR3225_Trim_points.csv` and
  `GOPR3225_Trim_first_frame_annotated.png` in the root survive from it. Starting this case means
  starting from Ngwerere again, not resurrecting anything. Note the data now lives *inside* the app
  bundle, not at the old top-level `RIVeR_Example/`.
- **Castor River.** `Prueba_Castor_River.ipynb` is a copy of the old root Ngwerere notebook with the
  paths swapped to `CastorRiver\20190709\Video4\...` and GCPs read from `GCPuse.csv`. It still fails
  on cell 2, but **no longer because the data is missing**: the HARMONIOUS zip has since been
  downloaded and `CastorRiver/20190709/Video4/` exists at
  `C:\Users\Sergio\Desktop\datasets vision velocimetria\data\` — the notebook just looks for it
  *inside the workspace*, where it never was. Fixing the path is now the whole blocker. It also
  still carries the Ngwerere title and a stale `crs=None,  # UTM zona 35S para Zambia` comment.

## Gotchas

- Both pipeline notebooks resolve everything relative to `cwd`, so they only work when the kernel
  starts in their own directory. Part 0 prints `FALTA` for the missing inputs if it doesn't — that is
  the symptom of launching from elsewhere, not of missing data.
- The SMC case needs its stabilized input to exist before the notebook will run: `entradas/
  SMC_estabilizado.mkv` (1.1 GB, not in any output folder, regenerate with `estabilizar_video.py`).
  The notebook does **not** detect that the video is stale relative to the polygon or frame range
  you meant to process — changing either means re-running the script by hand.
  `entradas/` also holds `SMC_estabilizado_previsualizacion.mp4` (157 MB), the lossy viewing copy,
  sitting right next to the real input. `ARCHIVO_VIDEO` must stay pointed at the `.mkv`.
- The STIV case needs its own stabilized input, `analisis_USGS_SMC_stiv/entradas/
  SMC_estabilizado_stiv.mkv` (1.1 GB). It is a **separate file** from the pyorc case's
  `SMC_estabilizado.mkv` and the two are not interchangeable: different script, different residual
  shake. The notebook takes **1–2 min** end to end; almost all of it is the single pass over the
  video (38 s warm, 80 s with a cold page cache on the 1.1 GB file), the rest is rendering figures
  that embed the 4K frame.
- The SMC video is 272 MB / 4K; stabilization takes ~110 s and the whole notebook ~160 s at a
  ~14 GB memory peak. `salidas/benchmark_recursos.csv` records the per-stage breakdown each run.
- The orphaned `analisis_USGS_SMC_pyorc/salidas/fig1_movimiento_dron.png` (left over from a Part 1b
  that no longer exists) is gone from `salidas/`, and figure numbering now starts at `fig1_` and runs
  contiguously to `fig12_`. Every PNG in that folder is regenerated by a full run.
- `SMC_PIV_results.mat` is USGS PIVlab output for flight **020**, while the processed video is **022** —
  usable for profile *shape*, not point-by-point comparison. Its wall-adjacent velocities sag enough
  that integrating it directly would land ~15% under the gauging.
- `video_test.py` points at `C:\...\test_pyorc\RIVeR_Example\GOPR3225_Trim.mp4`, which is dead twice
  over: that top-level folder is gone and the file now lives under `RIVeR-STIV_1.0\RIVeR_Example\`.
- The Boneyard videos live **outside the workspace** (`C:\Users\Sergio\Desktop\Boneyardcreek`,
  4.7 GB) and the paths to them are absolute on purpose. Several files have corrupt frames, so a
  full run prints a stream of `[h264] error while decoding MB ...` to stderr — non-fatal, ignore it.
- Plot layers must share a `mode` (`"local"` / `"camera"` / geographic). Passing raw UTM coordinates
  to a `mode="local"` axis silently blows up the axis limits.
- Exact reproduction of upstream numbers is not achievable, and is not a bug: pyorc estimates focal
  length by optimisation from the GCPs, so `CameraConfig` varies slightly between runs, and current
  ffpiv rounds `window_size` up to even (25→26, giving a 14 px step instead of 13). Load the repo's
  own `ngwerere.json` if bit-level reproduction is needed.
- The HARMONIOUS videos live **outside the workspace** too (`C:\Users\Sergio\Desktop\datasets vision
  velocimetria\data\`) and their paths are absolute on purpose. Every folder has a `Stabilised/` and
  a `Non-stabilised/` copy of the same footage: **use `Stabilised/`**, because the reference pixel
  coordinates are defined on its first frame.
- **`analisis_bradano_stiv/` figures look black if you forget the contrast stretch.** The Bradano's
  water sits at a mean brightness of 0.12/255; every figure and the output video stretch it on
  purpose. A new figure written without stretching will be a black rectangle, and it is not a bug in
  the data.
- Bradano's temporal-contrast QC is the one that does **not** transfer from Boneyard: the gravel
  bank there has *more* temporal contrast than the water (2.52 vs ≤1.89). The discriminator is
  brightness. Copying Boneyard's `CONTRASTE_MIN` into that case would let station 8 — a static bank
  reading coherence 0.82 at 0.00 m/s — straight through.
- `analisis_arrow_stiv/` reports **zero** accepted stations for its primary video, and that is the
  intended output, not a failed run. If a change ever makes the unseeded video produce velocities,
  something is wrong with the change, not fixed with the case.
- Both HARMONIOUS notebooks read the validation `.xlsx` **twice on purpose**: coordinates in Part 2,
  velocities in Part 7. Merging those two reads into one collapses the discipline the whole
  workspace is built on.

## `analisis_hommerich_stiv/` — metric STIV, the case where the geometry is all there

`video_velocidad.py` (run from the case folder, ~15 s) runs STIV from scratch on OpenCV over the
**original camera video** of the Geul at Hommerich — not the ortho the dataset also ships — and
renders `salidas/velocidad_tiempo_real.mp4` (3.7 MB, 122 frames, 2181×698, real time), plus
`velocidad_ventanas.csv` and `config_stiv_hommerich.json`. pyorc is never imported. **There is no
notebook**: this case is the tool and its `README.md`, which carries the full write-up.

Data lives outside the workspace at `C:\Users\Sergio\Desktop\datasets vision velocimetria\Hommerich`
(paths absolute on purpose). Only three files are used — the video, `cam_config_gcp1.json` and
`cs1_ordered.geojson`; `20241010_081717_ortho.mp4` and `hommerich_frames_*/` are pyorc's own
already-rectified output and are for eyeballing, never as input.

It closes the gap the other two STIV cases leave open. Boneyard is oblique with **no** geometry,
so it stops at affine units; SMC is metric but **nadir**, so there is nothing to rectify. Here the
camera is oblique *and* the dataset ships intrinsics, distortion (k1 = −0.485) and 6 RTK GCPs, so
`solvePnP` (SQPNP + LM, solved in local coordinates because RD New is ~3e5 and conditions badly)
gives the full pose — **0.56 px median reprojection, 2.50 px worst** — and the answer is in m³/s.
Two panels, as in Boneyard, because the rectification is a claim that needs to be visible.

Design rules that are deliberate and worth not "fixing":

- **The rectification is a per-pixel `remap`, not a homography.** A homography cannot carry lens
  distortion and k1 = −0.485 is far too strong to ignore. The world→pixel map is built once with
  `projectPoints` over the whole rectified raster (0.01 m/px, the dataset's own resolution).
- **The raster is section-aligned**, not the dataset's bbox: `u` along a PCA line through the
  wetted section points, `v` along its normal. That makes every vertical a *column* of the raster,
  so its STI is that column read every DS px — no per-station warp.
- **Water plane at z = z_0 + (h_a − h_ref) = 151.385 m.** `h_a = 93.345` comes from the dataset's
  own `process_..._h_a.sh`; the sibling script without `--h_a` puts the water below the thalweg.
- **The flow's *sense* is not imposed**, only its line (the section normal). The sign of the
  tensor slope decides which way is downstream.
- **The section is measured 2.5 m downstream of where it was surveyed** (`DESPLAZAMIENTO_SECCION`,
  overridable with `--desplazamiento`). In its surveyed position the four far-bank verticals saw
  only 42–75% of their search line; 2.5 m down, every line is at coverage 1.00, and 2.5 m is the
  minimum that achieves it. The cost, stated: depths still belong to the surveyed section, so Q
  assumes the channel is prismatic over those 2.5 m. Velocity is unaffected — it is measured where
  it is drawn. It moved Q from 12.94 to 13.68 m³/s (+5.7%), because three far-bank verticals go
  from filled to measured.
- **Lines are cropped to their visible run, not discarded.** Kept even though the displacement
  makes it unnecessary: it is what makes moving the section a choice rather than a requirement.
  Without it 4 verticals with contrast 11–12 were lost and the fill ate 3.2 m of the 12.13 m width.
- **QC is temporal contrast plus coherence**, the Boneyard lesson. Measured contrasts here run
  1.06, 1.14, 2.28, 2.63 | 3.14, 3.81, … and the two on the wrong side of the gap returned 0.06
  and 0.03 m/s next to one reading 0.65. `CONTRASTE_MIN = 3.0` is not load-bearing: 2.0 admits
  them and moves Q by +1.4%.
- `ALFA = 0.85` — the USGS standard *and* the `v_corr` in the dataset's own `hommerich.yml`.
- Arrows are **one second of travel**, a real-world length, so the original panel foreshortens
  them by itself (the tip is projected, not rotated).

Result: 13 of 16 measurable verticals accepted — the 3 rejects fail on *contrast*, not field of
view: they sit on the bank in 21–43 cm of water with no tracer, the same wall-adjacent weakness as
every other case, and no amount of moving the section fixes it. **v surface median 0.943 m/s**,
**Q median 13.68 m³/s** (q05–q95 13.33–13.99). **Nothing validates that number**: the package ships pyorc's log but not
its discharge, so closing the loop means running pyorc with the `cam_config` + `yml` + geojson it
provides, which would then be a controlled LSPIV-vs-STIV comparison on one video. Other limits:
only 4.1 s of footage (26 windows), a 0.5% fps ambiguity (`r_frame_rate` 30 vs `avg_frame_rate`
29.853) that goes straight into velocity, and linear fill at the banks.

## The HARMONIOUS dataset is downloaded

`C:\Users\Sergio\Desktop\datasets vision velocimetria\data\` (outside the workspace, paths absolute
on purpose) holds **13 rivers** from the HARMONIOUS image-velocimetry intercomparison release:
AlpineRiver, CastorRiver, LaMorgeRiver, MurgRiver, RiverArrow, RiverBradano, RiverBrenta,
RiverLaVence, RiverNoce, RiverThalhofen, RiverTiber, SalmonRiver, StJulienTorrent. Two of them are
now live cases (below).

The shape is the same in every folder and worth knowing before opening one: `Non-stabilised/` and
`Stabilised/`, each with `Frames/` (GIFs) and `Video/` (AVI), plus `Reference/` with an `.xlsx` of
validation velocities and a `Readme.txt` that **declares the m/px scale**. The videos are already
**orthorectified**, so there is no geometry to solve — which is what makes these cases cheap, and
also what makes them unable to produce discharge: **no release carries bathymetry**, so every
HARMONIOUS case stops at surface velocity.

The reference `.xlsx` gives pixel coordinates *and* velocities. The convention both live cases
follow is the SMC one: the **coordinates are geometry** and get used in Part 2; the **velocity
column is not opened until Part 7**.

Note the `Readme.txt` says the reference pixel coordinates are referred to the first frame of the
**stabilised** imagery — that is why both cases use the `Stabilised/` video rather than stabilising
the raw one with `estabilizar_stiv.py`. Verified on Arrow: the video's frame 0 matches the `Frames/`
folder's first image to 0.00 px by phase correlation.

## `analisis_bradano_stiv/` — STIV where the dataset already did the geometry

`Bradano_STIV_pipeline.ipynb` (29 cells, 8 parts, `fig1_`…`fig8_`) measures surface velocity on the
Rio Bradano (Basilicata) from a nadir drone video the release ships **already orthorectified and
stabilised**, at a declared 0.009 m/px. pyorc is never imported. 1920×1080, 24 fps, 600 frames
(25 s), all of them used. Runs in ~65 s at a 268 MB peak.

Nothing to rectify, no scale to deduce, no stabilisation to run — which strips the case down to the
method itself and surfaces a different difficulty: **the tracer is sparse**. The water images at a
mean brightness of 0.12/255 and the only visible signal is isolated bright particles, not a
continuous texture.

Design rules that are deliberate and worth not "fixing":

- **The search line is a band of 7 parallel lines, not one line** — the case's only departure from
  the other STIV notebooks, and it is what makes it measurable. Each line's STI is normalised
  *first* and then averaged, so lines contribute structure at equal weight rather than intensity.
  Measured: coherence at the central stations goes 0.47/0.77/0.80/0.71 (one line) → 0.76/0.93/0.94/
  0.90 (24 px band). 24 px and not 40 because the band averages *across* the section, which is the
  direction the profile is being resolved in: 24 px is 22% of the 1 m station spacing.
- **QC is brightness + coherence, not contrast + coherence.** Boneyard's lesson applies (station 8
  sits 9 px from the bank and returns **coherence 0.82 with velocity 0.00** — a coherence threshold
  passes it), but Boneyard's *discriminator* does not: here the gravel bank has the **highest**
  temporal contrast in the frame (2.52 vs 0.03–1.89 on water), because it is bright and takes the
  compression noise. What separates cleanly is brightness — water 0.013–0.42, bank 12.34, a factor
  30. `BRILLO_MAX_AGUA = 5.0` sits in that gap.
- **Stations are the gauging's own 1 m grid**, extended right to cover the wetted width: 9 stations,
  the first 7 coinciding with the validation verticals. That the 7 published verticals sit exactly
  111 px apart = 0.999 m at the declared scale is an independent check on the scale that uses no
  velocity.
- **Rejected stations are not filled** — no section to integrate, so filling would invent data.
  Same rule as Boneyard, opposite of SMC.
- The flow direction is imposed (`ANGULO_FLUJO = -90`, the image vertical); the **sense** is not —
  it comes out of the tensor's sign, and points upstream-in-image, which is what the river does.

Result: **5 of the 7 validation verticals measured, bias −3.1%, RMSE 0.068 m/s, r = +0.996.** The
transverse profile is reproduced including its sharp peak (1.38 vs 1.48 m/s). The 2 misses are the
bank-adjacent verticals — station 0 sits in the left bank's shadow with no particles (coherence
0.24), station 6 likewise (0.53) — the same wall-adjacent weakness as every other case, and the
reference says 0.84 and 0.63 m/s there, so what fails is tracer visibility, not the physics.

`video_velocidad.py` (run from the case folder, ~3.5 min) repeats the same STIV in sliding 150-frame
windows over all 600 frames and renders `salidas/velocidad_tiempo_real.mp4` (61 MB, 600 frames,
1920×770, real time) plus `velocidad_ventanas.csv`. **One panel**, like the SMC tool and unlike
Boneyard/Hommerich: the view is nadir, nothing to rectify. Two things specific to it: the display
**contrast stretch is not cosmetic** (at 0.12/255 the raw video is a black rectangle with arrows on
it), and it uses fixed percentiles from frame 0 so the background does not flicker. Station
acceptance matches the notebook (0, 6, 7, 8 fail; 1–5 pass). It **duplicates the notebook's
constants** — change one, change both.

## `analisis_arrow_stiv/` — the seeding experiment, where the result is a negative

`Arrow_STIV_pipeline.ipynb` (37 cells, 9 parts, `fig1_`…`fig9_`) is **not a measurement case**. It
is a controlled experiment on tracer seeding, and that is why it exists. HARMONIOUS publishes, for
the River Arrow (Warwickshire) from a pole-mounted GoPro, two videos differing **only** in whether
anyone seeded the water: `Arrow_GoPro_Unseeded_Stabilised.avi` and `..._Seeded_...`. Same framing,
same 0.0174 m/px, same 5 fps, 99 and 98 frames. Both are processed with **identical configuration**,
not one constant changed between them. pyorc is never imported. The whole notebook runs in ~50 s,
44 s of which is the Part 7 PIV.

**The unseeded video is not measurable, and that is the deliverable.** Its STI is white noise. Both
quality criteria — inherited from the other cases, not tuned here — reject **100%** of its 49
stations, and neither is marginal about it:

| | unseeded | seeded | threshold |
|---|---|---|---|
| Coherence | median 0.196, **max 0.595** | median 0.927 | 0.70 (same as SMC and Bradano) |
| Temporal contrast | median 0.71, **max 1.43** | median 6.74, min accepted 3.02 | 2.0 (Boneyard's criterion) |

**Part 4c exists to keep that claim from being circular, and should not be deleted as redundant.**
Without it the notebook only shows that *this* configuration finds nothing. 4c tries nine variants
on the unseeded video — `DS` down to 1 (almost no antialias blur), bands of 30 and 60 px (the trick
that rescued Bradano), a DoG spatial high-pass, one STI per whole section (10 verticals averaged,
trading transverse resolution for 10× the signal), and all combined. **Every one returns 0 of 49
stations.** It costs 14 s.

Two things in there are the methodological point and are easy to break:

- **Variants are scored against an internal truth, not just by coherence.** The seeded video
  measured with the notebook's own configuration gives 43 stations at 0.417 m/s median, and each
  variant's unseeded result is correlated against those station by station. This matters because
  raising coherence is trivial — the high-pass takes it 0.196 → 0.452 — but its agreement with truth
  does *not* follow (r = +0.39, and the set ranges −0.12 to +0.45, erratic). Coherence alone would
  have read that as progress. **It uses no validation data**: the arbiter is the other video through
  the same code, so Part 7 remains the only place the gauging opens.
- **The decorrelation curve is the actual explanation**, and it is what makes the negative result
  physical rather than empirical. Peak ensemble correlation vs temporal lag, peak searched over the
  whole window so displacement costs nothing and only the pattern ceasing to exist lowers it:

  | dt | 0.2 s | 0.4 s | 0.8 s | 1.6 s |
  |---|---|---|---|---|
  | seeded | 0.725 | 0.559 | 0.337 | 0.154 |
  | unseeded | **0.055** | 0.072 | 0.042 | 0.031 |

  The seeded pattern has a lifetime around a second. The unseeded one is at noise **at the shortest
  lag the recording allows**, and its curve is flat — it is not a pattern that decays fast, there is
  no pattern in any frame pair. Corollary measured in the same cell: in the unseeded video the
  **static gravel bank varies more over time (σ 8.88) than the water surface does (σ 3.32)**, so most
  of the water's variance is sensor and codec noise.

  What would fix it is acquisition, not code: seeding, or a higher frame rate. The data cannot say
  *how much* higher — the lifetime is below the shortest available lag — and since the water varies
  less than static ground, "no natural texture at all" is the more likely reading, in which case a
  faster camera would not help either.

Design rules that are deliberate and worth not "fixing":

- **One flow direction per cross-section, not one global** — the first case in the workspace to do
  this. The river turns inside the frame: ensemble correlation on the seeded video gives +6° at
  upper-left to +39° at lower-right. The angle is *not* swept for maximum coherence (that would be
  fitting to the data); it is the **normal to each section**, computed from the dataset's own
  endpoint coordinates. The five come out +8.2, +13.3, +16.0, +13.9, +12.8°.
- **`LADO_BLOQUE = 24`, not 64.** With 99 frames, 64-px blocks leave two along the time axis and the
  coherence-weighted median has nothing to take a median of. 24 leaves seven.
- **Lines are cropped to their visible run** (Hommerich's rule) — XS1 and XS5 hug the frame edges
  and run at coverage 0.52–0.81. It costs: all 5 of the seeded video's rejections are in XS5, all by
  coherence (0.53–0.69, just under threshold), none by contrast.
- **The band is 6 px, not Bradano's 24**, because verticals within a section are only ~25 px apart —
  same 24% ratio, different absolute size.
- **Part 7 runs an independent ensemble-PIV as an arbiter**, and this is the part not to remove. On
  the seeded video STIV lands the section mean (0.389 vs 0.417 m/s, −6.7%) but does **not**
  reproduce the transverse profile: r = −0.09. The obvious question is whether that is STIV's fault.
  It is not: a dense ensemble-PIV sharing no code with STIV gives **r = −0.01** against the same
  reference and **r = +0.974, RMSE 0.034 m/s** against STIV. Two unrelated image techniques agree
  with each other to 3 cm/s and disagree with the field data the same way, which points at the
  comparison, not the algorithm — most likely the reference is depth-averaged rather than surface,
  in which case the surface/depth ratio is not constant across the section. **The notebook fits no
  coefficient to close that gap**, on purpose.
- No discharge and no filling of rejected stations, for the usual HARMONIOUS reason.

`video_velocidad.py` (run from the case folder, ~45 s) measures both videos in sliding 48-frame
windows and renders them **side by side** in `salidas/velocidad_tiempo_real.mp4` (16 MB, 98 frames,
1874×1160, real time) plus `velocidad_ventanas.csv`. The two panels here are the two videos, not a
raw/rectified pair — the case is a comparison, so the comparison is the frame. Over 25 windows:
unseeded **0 of 1225** station-windows accepted, seeded 1085 of 1225 with a section median of
0.3991 m/s (q05–q95 0.3933–0.4095), against the notebook's 0.409. It **duplicates the notebook's
constants**.

Only the GoPro pair is processed. The release also carries a UAS seeded/unseeded pair with its own
validation file; a quick ensemble-correlation check says the UAS unseeded has no signal either
(peak locked at (0,0) with 0.20–0.27, a static residual), but it has not been run through the
notebook.

## `analisis_canal_riego_stiv/` — STIV with no geometry and no field data whatsoever

`stiv_canal.py` (run from the case folder, ~95 s) runs STIV from scratch on OpenCV over an
**81 s WhatsApp phone video** of a concrete-lined irrigation canal, handheld from a culvert looking
almost straight down the canal axis. pyorc is never imported. **There is no notebook**: this case is
the tools plus its `README.md`, which carries the full write-up. Data lives outside the workspace at
`C:\Users\Sergio\Desktop\videos\WhatsApp Video 2026-08-16 at 8.07.12 PM.mp4` (7.4 MB, path absolute
on purpose).

It is the **lowest-information case in the workspace**: no GCPs, no measured width, no section, no
bathymetry, no gauging, no EXIF. 1024×576 at **661 kb/s**. Geometry comes only from the vanishing
point of the canal's own banks, so the result is in affine units — Boneyard's pattern — and reads
**v median 0.0590 camera heights/s = 0.0262 canal widths/s, 6 of 15 stations accepted**.

Design rules that are deliberate and worth not "fixing":

- **Morphological top-hat is what makes the video measurable, and it is the case's lesson.** At
  661 kb/s the encoder flattens the low-contrast turbid water and the raw STI is a mosaic of H.264
  macroblocks: ensemble correlation gives 0.95 with the peak **locked at zero shift**, the Arrow
  no-signal signature, and the water's temporal std (0.54–1.06) is *below* that of static concrete
  in shadow (1.2–2.3). A top-hat with a 5 px element isolates the real tracer — loose vegetal
  debris, 2–4 px — and **erases the blocks**, because a macroblock is a flat region and top-hat
  keeps only what is brighter than its immediate surroundings. 5 px sits between debris size and
  the 16 px block. Try this first on any other compressed phone video.
- **The structure tensor needs block selection by signal.** With sparse tracer most STI blocks hold
  no streak, only the static residual — a perfectly coherent zero-slope streak, Boneyard's trap.
  The plain coherence-weighted median returns **0.000 with coherence 0.7 at all 15 stations**,
  including ones whose streaks are obvious by eye. `CUANTIL_SENAL = 0.85` takes the median over
  only the brightest 15 % of blocks, and that number is **measured, not fitted**: 11–21 % of blocks
  actually contain a particle.
- **The band is 11 lines over 0.10 camera heights — 68 % of the station spacing**, far wider than
  Bradano's and Arrow's 22–24 %. Measured: 3 lines give coherence 0.48–0.75 and an erratic bias
  (+5 % to +29 %); 11 lines give 0.65–0.86 and a stable bias; 21 lines add nothing and cost
  transverse resolution.
- **QC is tracer density, two-sided — and neither Boneyard's nor Bradano's discriminator works
  here.** Water with tracer and water without have the *same* brightness and the *same* temporal
  contrast; the difference is only whether a particle passes. Measured populations: no tracer
  0.00001–0.00039 (stations 1–7), tracer 0.00575–0.01969 (8–13), right bank 0.07779 (14). Factor 15
  gap below, factor 4 above. **The upper threshold is load-bearing**: without it station 14 enters
  with coherence 0.67 and a velocity that is wet concrete.
- **QC criteria are evaluated independently, not chained.** Station 0, against the *left* bank, has
  density 0.01023 — squarely in the tracer band, so density does not catch it. It is stopped by
  coherence (0.580 vs 0.60, by a hair) and by `V_MAX_FISICA = 3 × V_ESPERADA`, which catches it by a
  factor 13 (it returns 0.7551). Chaining hid that.
- **Two slope estimators run on every STI.** The block tensor is the one that counts; `cresta_fft`
  (the classic spectral STIV variant — a translating pattern puts all its energy on one line through
  the origin of the (k_s, ω) plane) is diagnostic. Both were validated on a synthetic STI of known
  slope 1.300: FFT 1.297, tensor 1.275. So the +13 % bias below is **not** a broken estimator, and
  the tensor is not biased high by construction.
- **Constant canal width validates nothing — do not cite it as a self-check.** The vanishing point
  is computed as the intersection of the two bank lines, so the homography sends them to parallel
  *by construction*; the measured variation is **1.97e-16**, machine epsilon, for any FOCAL. It is
  an algebraic identity that only catches a coding error in the homography. What does validate the
  geometry is that **the STI streaks come out straight** — with a wrong horizon a particle at
  constant speed would trace a *curved* streak, since it covers more pixels as it approaches. A
  visual check, not a bound, like Boneyard's distortion check. Zero roll is a hypothesis, as in
  Boneyard; the vertical vanishing point was not attempted because this framing has no reliable
  vertical.
- **`FOCAL = 780` is the case's dominant uncertainty, bigger than the algorithm.** It is a
  supposition (WhatsApp strips EXIF; 780 px is a typical ~26 mm phone lens on a 1024 px frame) and
  it sets the deduced tilt, hence the *streamwise* scale — the one velocity is measured along.
  Measured by `--barrer-focal`: **v moves +52 % between F = 600 and F = 1000** (0.0426 → 0.0647
  camera heights/s), or ±9 % over a realistic 700–900 lens range. The trap is that the *width*
  barely moves (8.6 %) and the width-with-distance identity is null for any focal, which makes the
  geometry look pinned down when it is not. Unlike the +13 % arbiter gap this is a **systematic
  bias, not scatter**, and no amount of extra video or better algorithm reduces it — only a real
  measured length, which would also make FOCAL irrelevant.

**The left half of the canal cannot be measured, and that is part of the result.** It holds 4 to 31
top-hat detections against 1,500–16,000 on the right, and PTV closes **zero** tracks there over the
full 81 s: the debris falls from vegetation overhanging the right bank and travels in a band down
that side. Rejected stations are **not filled** — no section to integrate (Boneyard/Bradano rule,
opposite of SMC). So the measured profile is that of the canal's right third, and its maximum
(0.0646 at X = +0.42, with the axis at X = 0) probably is not the section's.

`ptv_arbitro.py` (~110 s) is the independent arbiter, and it exists because there is nothing from
the field to compare against — same discipline as Arrow's Part 7, where an ensemble PIV arbitrates
STIV: **the arbiter uses another algorithm, not validation data.** It fits naturally here because
the tracer is discrete particles, which is what a tracker wants and what a correlation method
suffers. From 4,524,347 detections come 660 tracks and 562 straight moving ones.
**r = +0.984, bias +13.1 %, RMSE 0.0070** over the 6 stations. The profile shape is reproduced
almost exactly and the bias **grows with velocity** (+19 % in the fast core, +3 % at the slow
stations), which points at the two methods averaging different particle populations rather than at
either being wrong. **Nothing was tuned to close it.**

Flow sense was confirmed a third way, without the rectification at all, so it could not inherit its
sign convention: matching blobs in raw image coordinates at a 30-frame lag gives median `dy` of
**−0.57 px** with **59.3 % of 60,702 pairs** rising toward the vanishing point. The water flows away
from the camera. That check is good for the sign only — in a field with thousands of detections the
nearest neighbour a second later is usually a *different*, closer particle, so the magnitude comes
out 17× low. Which is exactly why `ptv_arbitro.py` links frame to frame demanding track continuity.

`video_velocidad.py` (~9 min) repeats the STIV in sliding 360-frame (12 s) windows and renders
`salidas/velocidad_tiempo_real.mp4` (21 MB, 1798×702, 2429 frames, real time) plus
`velocidad_ventanas.csv`. Two panels, as in Boneyard and Hommerich, because the camera is oblique.
Over 138 windows the section median is **0.0598** against the single full-video figure of 0.0590 —
agreement to 1.4 %, so the measurement is not an artifact of one window. The detected debris is
painted yellow on both panels, which makes the video self-explanatory and replaces a
water-referenced contrast stretch that blew out both banks (30 % of pixels saturated) and still left
the water flat.

**This case does not duplicate constants** — the one thing to copy from it into the other five.
`video_velocidad.py` imports geometry, enhancement, tensor and `motivos_rechazo` from
`stiv_canal.py` instead of copying them, so the "change one, change both" hazard the rest of the
workspace carries does not exist here. Only window size, step and visual language are local.

Two performance notes worth reusing: `cv2.applyColorMap` on a 1×1 array costs **1.9 ms** of LUT
setup overhead, and asking for a colour 205 times per frame was **23 of the 31 s** of the drawing
loop — a precomputed 256-entry table took it from 0.52 to 0.14 s per frame. And `cv2.remap` refuses
maps whose flattened length exceeds `SHRT_MAX` (32767), so sampling many stations at once has to be
reshaped into a 2D map rather than one long row.

### `analisis_canal_lejano_stiv/` — how far up the canal STIV reaches

**Not a case — a controlled experiment on the one above**, and the only thing in the workspace that
measures where an STIV AOI has to stop instead of inheriting the limit. `experimento_alcance.py`
(~6 min) **imports** geometry, enhancement, tensor and QC thresholds from
`analisis_canal_riego_stiv/stiv_canal.py` and redefines no parameter of the method; the only things
that vary are which stretch of canal is looked at and with what temporal step. Nothing in the
original folder is touched.

The question needs no field data: it is the same water at 2 and at 6 camera heights, so **it must
give the same velocity**.

- **The far field lies, and lies confidently.** Same configuration, three distance bands: near (the
  case's own, `DS` = 0.23 image px) gives +0.059 … +0.028, 6 of 6 accepted; mid (0.08 px) gives
  −0.69 … +0.88; far (0.04 px) gives +1.86, +1.22, −0.65, +0.94, +0.88, +1.19 — **20× the truth,
  signs disagreeing between neighbouring stations, at coherence 0.97–0.99 and FFT sharpness 9543**
  (good stations score 8–47). This is Boneyard's trap at its most extreme: there, walls scored
  coherence 0.74 at exactly zero; here the far field scores 0.98 at 20× the real speed. Of the
  case's four QC criteria only `V_MAX_FISICA` catches it every time.
- **Temporal decimation proves it is aliasing, not wave celerity.** The factor 20 had a physical
  rival worth excluding: the far water shows no debris at all, only specular cloud reflection and
  ripple, and those travel at `sqrt(g·h)` ≈ 3.1 m/s for h = 1 m against ~0.15 m/s of current — a
  factor 21, almost exactly what is observed. The discriminator needs no depth: `DS` is chosen so
  streaks land at 45°, i.e. `DS` = displacement per frame, which in the far field is 0.04 image px,
  so the STI is sampled 25× below one pixel. Taking 1 frame in N raises the per-step displacement
  and satisfies both conditions. A physical signal would not care: **at N = 20 (0.73 px) the far
  field returns −0.06 to −0.17 with coherence 0.23–0.33.** Sign flipped, magnitude down 20×,
  coherence collapsed. Aliasing, and there is simply no signal up there.
- **The main case's result is not contaminated.** Splitting its band in two: the near half (0.33 px)
  gives **+0.0580 with 6 of 6 accepted**, against +0.0590 for the whole band — **1.7 %**. The far
  half (0.17 px) is **rejected 0 of 6 by the case's own coherence threshold** (0.51–0.59) and its
  velocities already lean high (+0.064 to +0.092). So `Y_MAX = 3.20` is safe though generous, and it
  is now measured rather than inherited from Boneyard.
- **Coherence is not monotonic in sampling quality, which is why it deceives.** 0.75–0.89 at 0.33 px
  (right), 0.51–0.59 at 0.17 px (wrong by +40 %), then back up to 0.97–0.99 at 0.04 px (wrong by
  20×). It dips through the transition and rises again once the artifact dominates cleanly. **The
  only monotonic indicator is `DS / image pixel`**, which is purely geometric and computable before
  processing anything.
- **The transferable rule: require `DS` ≳ 0.2 image px.** Below ~0.1 px the tensor returns garbage
  at coherence near 1. Caveat on the coarse end: `lejos N=40` (1.45 px) and `media N=8` (0.68 px)
  return coherence 0.00 and `nan` because the STI no longer yields 5 blocks, not because the signal
  is absent — the only well-populated coarse test is `lejos N=20`.

- **A different algorithm agrees.** All of the above is STIV arguing with itself, so
  `correlacion_arbitro.py` runs ensemble correlation -- no STI, no tensor, no line band -- on the
  same patches sampled at the image's **native** resolution. The near control's peak walks
  linearly with lag (+3, +6, +13, +25, +34 px at 1 to 13 s, dX = 0 throughout); the far field's
  stays **locked at zero**, with peak exactly equal to the zero-shift value (0.2440 = 0.2440) --
  the same no-signal signature the whole video gave before the top-hat. It is a presence test, not
  a measurement: the control's deduced +0.023 does not match STIV's +0.059 because a wide patch
  is dominated by the densest, slower right side.

The far field of this video is unmeasurable by any route, and that is a property of the recording,
not the algorithm: no tracer up there, and the water advances 0.04 px per frame in a 661 kb/s
stream. Only a closer camera or more resolution would change it.

`video_alcance.py` (~7 min) redoes part 1 in **sliding 360-frame windows** over the whole video and
draws it: `salidas/video_alcance.mp4` (36 MB, 1876×996, 2429 frames, real time) plus
`alcance_ventanas.csv`. It imports the bands, stations and sampling map from
`experimento_alcance.py`, so nothing is redefined. Measuring 138 times instead of once separates a
bias from a chaos, and it turns up one thing the single-shot table cannot:

| band | station-windows accepted | median of per-window section medians | max \|v\| |
|---|---|---|---|
| **near** | **589 of 828** | **+0.0598** | 1.25 |
| mid | 20 of 828 | +0.1248 | 2.98 |
| **far** | **0 of 828** | — | **4.73** |

(That median is the per-window one, the same statistic the case reports over the whole video.
Pooling the 589 accepted station-windows directly gives +0.0575 — a 4 % gap between two ways of
averaging, smaller than the window-to-window spread.)

Near repeats to **1.4 %** of the single full-video figure (its drop to 71 % acceptance is density,
not accuracy — 12 s holds fewer particles than 81 s). Far is rejected in all 828. But **the mid
band leaks 20 of 828 (2.4 %)**: windows where the artifact lands inside the physical bound *with
the right sign*, so it passes all four QC criteria at once. Part 1 reports 0 of 6 there and cannot
see this. It is the argument for not going near `DS = 0.08 px` even with QC.

Two choices in the drawing worth keeping: **arrows are coloured by coherence, not velocity** — the
only way to make the trap visible, since red (the best quality score) lands exactly where the
measurement is absurd — and each arrow is **clipped to its own band** and marked when it clips,
because how much it clips is the measure of the nonsense. The bottom-left time series (simlog,
because +0.059 and +3 share the axis) is the whole experiment in one image: the near curve is a
straight line on the reference while the other two swing between +1 and −1 changing sign.

### `analisis_canal_filtro_adaptado/` — the last attempt on the far field, and what actually kills it

**Not a case — the third and final experiment on `analisis_canal_riego_stiv/`.** The structure
tensor and ensemble correlation had both been ruled out; the one family left was **coherent
integration over the whole residence window** instead of over 64-frame blocks. That is what
`filtro_adaptado.py` does: for each candidate velocity it walks the trajectory `s(t) = s0 + v·t`
and sums the enhanced image along it — track-before-detect, i.e. the Radon transform of the STI —
scoring each projection by `(max − median)/MAD`.

- **The verdict: nothing beyond Y = 3.20, and this time the negative is backed.** Near band
  detects at z = +33 with the time-reversed peak mirroring it exactly (+0.0250 → −0.0250, the
  signature of real advection); mid and far bands never leave the shuffled-frames null band and
  their forward/reverse peaks bear no relation to each other. `fig1_curvas_filtro.png` shows it in
  one look.
- **The controls are the point.** Synthetic streak of known velocity: recovered at +0.0600 from
  +0.0590 with z = +186, still detected when weak, nothing on pure noise. Real positive control on
  narrow X bands: +0.0600 where STIV reads 0.064, +0.0200 where it reads 0.028.
- **The filter measures the MODE of the tracer population, not the section median.** On the wide
  X band it returns +0.0250, not the case's +0.0590, because the max statistic is dominated by
  wherever the particles are densest — the slow right bank. The narrow X ~ 0.86 band returns
  +0.0200, nearly the same, and `analisis_canal_lejano_stiv/`'s ensemble correlation had already
  given +0.023 on its own. fig1's near panel even shows both populations: the dominant peak at
  +0.025 plus a clear shoulder at +0.059. STIV per station does not have this problem because each
  vertical is measured separately.
- **Resolution, not compression, is what erases the far field — and getting this right needed a
  controlled test.** `supervivencia_trazador.py` counts surviving debris in the *near* field (where
  tracer is plentiful) after re-encoding, with no estimator involved: the particle-pixel fraction
  goes **0.03776 → 0.00020 (×190)** from f = 1 to f = 6.5, which is what the far field is
  equivalent to. But that ladder lowers resolution and bitrate together, so it cannot say which one
  bites. `separar_causas.py` crosses them: **shrinking to 158×88 while keeping 661 kb/s — 48 bits
  per pixel, effectively lossless — still loses 111× of the tracer**, and the real far-field
  conditions add only a further factor 1.8 on top. So a better codec would not rescue the far
  field; more pixels on target would. An intermediate write-up in this folder claimed the opposite
  ("the encoder is the culprit"); that came from the ladder while it still had the rescaling bug,
  and this experiment overturns it.
- **In `separar_causas.py` only the survival column is trustworthy.** All four rows come out
  "DETECTA", but the three degraded ones are false positives: peaks at +0.0150, −0.0150 and
  −0.0125, all within 0.003 of the 0.012 dead-zone edge, two of them negative (water running
  backwards) and with margins like 3.37 against a 3.24 ceiling. DC residual leaking past a dead
  zone that is too narrow for such degraded inputs.
- **The `varianza` statistic reports DETECTA in all three bands and it is false.** Its null has
  almost no spread, so any non-zero value yields an enormous z (240–1025), always peaking at the
  dead-zone edge. It is also the second-order statistic, i.e. the equivalent of `cresta_fft`. Kept
  in the output only to document why it is not used.
- **Cite score-vs-ceiling, not z.** Comparing `video_filtro.py` against a standalone
  `filtro_adaptado.py` run on the same data: the score is identical (16.48) but the ceiling and z
  are not (4.37 / z +71 vs 4.82 / z +33), because with only 12 shuffles `nulo_std` is noisy and any
  change in how the rng stream is consumed moves it. z orders candidates *within* one run — which
  is all `veredicto` uses it for — and is not a number to quote across runs.

`video_filtro.py` (~4 min) writes `salidas/video_filtro.mp4` (2.5 MB, 1388×1040, 483 frames, 16 s).
**It is not a video of the river**, deliberately: the finding here is that the far field has nothing
to show, and a panel of still water without arrows cannot distinguish "no signal" from "the program
isn't drawing". So it animates the detector instead — one frame per candidate velocity, three
columns per band (the STI with the candidate's trajectory family drawn on it, the resulting
projection, and the score curve filling in against the null ceiling). The **synthetic positive
control is the top row, in the same frame and through the same code**, so each negative is read
beside a known positive: synthetic +0.0600 at 34.30/3.37 with an exact −0.0600 mirror, near +0.0250
at 16.48/4.37, mid and far under their ceilings with mirrors that bear no relation. Two drawing
choices that are decisions rather than polish: the final hold parks **each row at its own peak**
(the last candidate, +0.15, leaves the coverage mask with almost no points — and that was the frame
that stayed frozen), and the projection panel's vertical scale is **fixed across the sweep**, since
rescaling per frame would make the good candidate's spike look no taller than the bad ones' noise.

Five things went wrong on the way and **every one of them was caught by a control, not by reading
the code** — which is the transferable lesson:

1. **Fourier shifting is circular.** A particle crosses the band in 22 s, not the video's 81, so
   trajectories ran off one edge and reappeared at the other, systematically penalising fast
   candidates. Caught because the positive control returned +0.0150 instead of +0.0590.
2. **Integration time must be equal for all candidates**, or a slow hypothesis dwells longer,
   averages more and wins unfairly.
3. **Average the SCORES across windows, not the projections** — different windows hold different
   particles at different places, so averaging projections averages noise.
4. **Search the peak on the per-velocity z against the null**, not on the raw score, whose baseline
   drifts with `v` because the coverage mask leaves fewer positions at higher speeds
   (extreme-value statistics).
5. **`escalera_honesta.py` re-encoded to 512×288 but never scaled back up**, so the case geometry
   sampled outside the frame and `remap` returned zeros — giving score exactly 0.00 from f = 2,
   which looked like a clean confirmation of the hypothesis. The tracer-survival table exposed it:
   it showed 0.018 particle-pixel fraction exactly where the filter claimed to see nothing. **An
   exact zero where measurable signal exists is a bug, not a finding** — the right conclusion would
   have been reached for the wrong reason.

Also worth recording: the initial bet was that **kurtosis** would be the discriminator, since the
correct velocity concentrates sparse particles into few tall peaks at equal total energy. The
synthetic validation disproved it — with tens of particles over ~170 positions the projection is
not sparse enough, and kurtosis came out the weakest of the three. The max-over-MAD wins.

## `analisis_canal_completo_stiv/` — STIV at its best, and the rest of the canal modelled

Fourth folder on the same phone video, and the first that ends in a **simulation**. Two halves,
neither of which duplicates anything: geometry/enhancement/tensor/QC import from
`analisis_canal_riego_stiv/stiv_canal.py`, the matched filter from
`analisis_canal_filtro_adaptado/filtro_adaptado.py`.

**`stiv_mejorado.py`** (~9 min) runs STIV at 29 stations over all 2429 frames. **12 accepted, all
between X = +0.12 and +0.93, section median +0.0590 — identical to the case's** figure at 15
stations, which is the check that the coarser sampling was not biasing it. What it adds:

- **An error bar per station**, from 138 sliding windows: σ ≈ 0.010 repeatability, plus per-station
  acceptance (65/138 near the axis, 136/138 mid-jet). The model fit later needs those weights.
- **Three independent estimators.** Tensor vs FFT ridge agree to a median 0.0042; the matched
  filter detects in 12 of 12 accepted and agrees to 0.0100 — on a 0.059 velocity. **But it also
  fires in 7 of the 15 tracer-free stations**, where by construction there is nothing. With 12
  shuffles its null ceiling is too low for STIs that poor. So: **corroborator, never a gate.**
- **The wide-band test that closes the left half for good.** Widening the line band to 0.30 with 61
  lines raises tracer density ×2.2–7.5 on the left and it *still* misses the 0.004 threshold. And
  the one station that passes (X = 0.00, ×42.5) is an artifact worth knowing: a 0.30 band centred
  there **reaches X = +0.15, inside the tracer**, so it measures its neighbours' density and then
  returns **+0.0044 with coherence 0.85** — a confident zero, Boneyard's trap in a new disguise.
  Widening the band toward empty water is not merely useless, it is dangerous.

**`simulacion_canal.py`** fits Shiono-Knight (the standard lateral-distribution method) to the
measured 36 % and extrapolates. SKM's shape depends on one dimensionless group `Gamma`, which is
what makes it usable in affine units — g, H, S₀ and f are unknowable here but all enter through it,
and `Gamma ≈ 1.51·(B/H)` under standard λ = 0.07, f = 0.03. Four things worth keeping:

- **The σ for the fit is not the window spread.** That measures repeatability (0.0104) and drives
  χ² through the roof — which says the error bar is wrong, not the model. The systematic part is
  measured, not invented: the **spread between the three estimators at that station** (0.0056).
  Added in quadrature, the fit behaves.
- **A free effective half-width is the finding, not a knob.** With the wall at the visible bank the
  fit is poor (rms 0.0133, χ²red 1.95). Letting the water's hydraulic edge float puts it **0.139
  camera heights inside the visible bank** (6 % of the width per side) and takes χ²red to **0.52**.
  In a lined irrigation canal that is the trapezoidal toe: thin sheet, no velocity.
- **`Gamma` rails at the elliptic limit, so it is not determined from below** — quoting the fitted
  value would be quoting the bound written in the code. What the χ² profile does give is a real
  constraint: **Gamma ≤ 4.10 (2σ) → B/H ≤ 6.2** (λ 0.07) or ≤ 12.8 (λ 0.30). A wide shallow canal
  is ruled out; a normal one is not.
- **The dominant uncertainty is the axis position, which the data cannot fix.** Sweeping the assumed
  axis moves χ²red only 0.47 → 0.91 while the section mean moves **21 %**. Reported as a scan rather
  than letting a free-axis fit rail.

Result: section-mean surface velocity **0.0476** over the full width vs **0.0534** over the
measured part — **keeping only the measured third overestimates by +12 %**, which is the practical
payoff. Over the unmeasured part the SKM model gives 0.0438 and a plain mirror of the measured half
gives 0.0441 — two hypotheses with nothing in common agreeing to 0.7 %, which is the best argument
the extrapolation has. The full envelope of hypotheses spans +36 %.

The PTV arbiter (not used in any fit) sits 18.8 % below the model on average — same sign and order
as the STIV-vs-PTV offset the case already documented — but with one new detail: **PTV measures
0.0223 at X = +0.933, and the fitted hydraulic edge is at +0.963.** So the near-bank decline is
real (PTV reproduces it) but the model makes it sharper than it is.

`video_canal_completo.py` (~7 min) writes `salidas/canal_completo.mp4`: **virtual particles seeded
across the whole width**, advected at the modelled velocity, with a trail that is 1.2 s of travel —
so trail length *is* velocity and the transverse profile reads at a glance. The check is built into
the design: the virtual particles are drawn **over the measured third too**, where real debris shows
in yellow, so the two populations share the screen and must keep pace. Real debris yellow,
simulation blue, unmeasured reach shaded, and the caption repeats it — this is a simulation, not a
measured discharge.

### `analisis_canal_stiv_puro/` — the same canal with nothing modelled

One file, one product: `video_stiv_puro.py` → `salidas/stiv_puro.mp4`. It **measures nothing new** —
`pasada_sti` and `medir_ventanas` are imported from `analisis_canal_riego_stiv/video_velocidad.py`,
so the numbers are the case's own and there is no second version of the truth. It only draws.

It exists as the deliberate counterweight to `analisis_canal_completo_stiv/`. That one ends in a
Shiono-Knight simulation with virtual particles running across the whole canal; it is labelled
correctly, but the image a viewer keeps is a whole canal in motion, two thirds of which is a model.
Here **everything on screen is measured**: no virtual particles, no fitted curve, no filling of
rejected stations. The result is a poorer picture — the canal is measured only in its right third,
with nine holes — and that poverty is the honest answer. Both are worth having; what matters is
that they are told apart at a glance.

Three things in it that are decisions rather than styling:

- **The STI sits under the arrows, with the tensor's fitted slope drawn on it**, and the focused
  station rotates every 4 s and is highlighted in both panels. That is what makes a velocimetry
  video auditable: with arrows alone the number has to be taken on trust; with the STI beside it
  the streak, the fitted line and the resulting arrow are all visible at once.
- **The profile joins two points only if their stations are adjacent.** Skipping over a station
  that failed would draw a line nobody measured — easy to get wrong, because the list of accepted
  stations already comes with no holes in it, and it was wrong in the first draft.
- **Rejected stations are still drawn**, dim with an ×, because where the method fails is part of
  the result.

Configuration is the original one (15 stations, not the 29 of `analisis_canal_completo_stiv/`) —
both because the request was for the original algorithm and because at 29 the arrows crowd.

### `analisis_canal_seccion_completa/` — arrows bank to bank, no on-screen caveat

One file, `video_seccion_completa.py` → `salidas/seccion_completa.mp4`. Same canal, same drawing
language as `analisis_canal_stiv_puro/`, but **every one of the 15 stations gets an arrow** and
nothing on screen separates measured from deduced. That absence of a caveat was **explicitly
requested**; it is not an oversight and not a default to copy into other cases. Read this before
touching or reusing it:

- **Stations 8–13 (X +0.12 to +0.85) are measured** by STIV on real debris, via `pasada_sti` and
  `medir_ventanas` imported from the case.
- **The other nine are deduced**: the transverse *shape* comes from the Shiono-Knight fit in
  `analisis_canal_completo_stiv/`, and the *amplitude* is rescaled window by window from the six
  stations that do measure. Six stations carry all fifteen.
- `salidas/perfil_seccion.csv` has a `medida_directa` 0/1 column and the JSON lists which stations
  are which, so provenance is recoverable even though the video does not show it. `README.md` is
  the only prose record — the video should not circulate without it.

Two things in it worth reusing elsewhere:

- **Filled stations must move, or the eye catches them.** A fixed value leaves nine arrows frozen
  while six flicker. So a single per-window scale factor is applied to the whole section (physically
  right: a section accelerates as a whole) plus a per-station jitter whose parameters are all
  **measured on the residuals of the stations that do measure** — not chosen.
- **Those residuals must be split first, and getting this wrong was visible on screen.** The raw
  scatter (σ 0.219) mixes a **persistent per-station offset** (0.173 — how wrong the model's *shape*
  is at that station, fixed in time; station 13 sits at −0.41, the model overshoots near the bank)
  with the **temporal wobble** (0.136 — the real window-to-window variability). They add in
  quadrature to 0.220, so the split closes. Using the total injects a *shape* error as *temporal*
  noise and makes the nine deduced stations flicker far more than a real one; with only the temporal
  part the transverse profile stops looking like a sawtooth. The clip (5–95 percentiles of the
  wobble) matters too: without it, 138 windows × 9 stations throws up several 3σ spikes, and a real
  profile would not have them because QC rejects those stations.
- **The station-to-station correlation of those residuals is biased and must be corrected before
  use.** It reads +0.07 on the wobble (−0.11 on the raw residual), but removing a common factor
  estimated over `n` stations induces ≈ −1/(n−1) by construction; with n = 6 that is −0.20, so the
  corrected value is ≈ +0.27 and barely smooths. Independently, at 15 stations the 0.10 bands sit
  0.146 apart and do not overlap, so near-zero is what to expect. (At the 29-station spacing of
  `analisis_canal_completo_stiv/` they *would* overlap and the spatial correlation would be real.)

It uses the **rigid-wall** SKM fit, not the better-fitting free-effective-width one, because the
latter puts the water's edge at X = ±0.963 — inside stations 0 and 14 — and would give them
exactly zero, i.e. two zero-length arrows at the ends. Note also that the model is symmetric about
the geometric axis while the measured maximum sits at X ≈ +0.42, so the drawn profile imposes a
symmetry the data do not have.

## `analisis_kurome_directo_stiv/` — STIV on a live stream, in real time

`stiv_directo.py` (or double-click `arrancar.bat`) resolves the HLS stream of the chosen camera
with yt-dlp, opens it with OpenCV and starts measuring at once:
each frame is sampled along 9 search lines, rows are stacked into a sliding 10 s STI, and a worker
thread re-measures every second. Window shows the live video with arrows plus every station's STI
with its fitted slope; `e` drags the quad live, `p` hides the STI panel, `f` fullscreen. Output
appends to `salidas/<camara>/medidas_directo.csv`. `README.md` is the full write-up.

**Two cameras, one method.** Everything camera-specific (URL, quad, assumed dimensions,
`v_esperada`, line length, band width) lives in the `CAMARAS` dict; `elegir_camara()` sets the
module globals from it. The folder keeps the first case's name.

| `--camara` | Stream | View | Result (assumed scale) |
|---|---|---|---|
| `myoshoji` (default) | `huAp4q7lxiQ`, Myoshoji river, Kamitakada 5-6 (Nakano) | looks *along* the concrete channel, water moves away (up in image) | daytime: 6 of 9 stations, section median **0.45 m/s** |
| `kurome` | `loW9744B-Co`, Kurome river, Koma bridge | oblique across, water moves right | night IR: stations 3–5, 0.55–0.74 m/s |

Myoshoji's quad stops just below a small weir: the white water is stationary (correlation locked at
0) and the far end of the lines already samples at **0.23 image px**, just above the ~0.2 px
aliasing limit measured in `analisis_canal_lejano_stiv/`. Its stations 7–8 sit in the right wall's
shadow and are rejected by activity (0 active blocks).

**It has its own `.venv`** (numpy, opencv-python, yt-dlp) because **`pyorc_env` is broken on this
machine** — it has no `Scripts\` (copied from another computer, whose user was `Sergio`, not
`sergi`). The system Python 3.11.9 has no OpenCV either.

- **Both cameras run at 15 fps; YouTube duplicates every frame to 30.** PTS is perfectly regular,
  so the STI is built on the 30 fps PTS grid *without* deduplicating (content-based dedup dropped
  real frames). A synthetic STI with duplicated rows recovers the exact slope, so this is safe.
- **The codec, not the scene, sets the trap here.** YouTube freezes smooth water ("skip" blocks):
  perfectly coherent vertical streaks at v = 0.00, which the first version accepted. Fixed by masking
  the tensor per pixel with activity = |I(t + 1/15 s) − I(t)|: frozen water reads **exactly 0.00**,
  textured water 0.7–5.6; `ACTIVIDAD_MIN = 0.5`.
- `COH_MIN = 0.40` (Boneyard's), chosen *after* seeing night-time IR data (0.3–0.55 on clear
  streaks). STI smoothing stays at σ = 1 row: raising it lowers v 10–15 % on real data but not on
  the synthetic, i.e. coarse near-stationary structure (standing waves) gaining weight.
- **The scale is an assumption at both cameras** (Kurome 15 × 6 m, Myoshoji 10 × 8.8 m — the width was
  measured on an orthophoto on 2026-10-13, 8.8 ± 0.7 m crown to crown; the length is still assumed, a
  camera model gave 9.6 m (7.9–13.4) but failed an independent check against a pedestrian's height —, quads drawn
  by eye; no published widths found for either site) and the screen says so while
  `escala_verificada` is false. Nothing validates any of the numbers.
- Open item: in one short daytime Kurome run, its station 8 (over the near-bank vegetation) passed
  QC at 1.18 m/s, just under `V_MAX_FISICA` = 1.2. Not investigated.
- **Duplicated frames, wall bubbles, `shimoda` (2026-10-13, later).** The fast STI is now built
  from **one row per real camera frame** (the mean of each YouTube duplicate pair; `Geometria.k_real`,
  `dt` = 1/15 s, DS doubles). With duplicates the STI is a staircase and the tensor overestimates
  once streaks exceed ~1.5 samples/row (synthetic: slope 2.5 -> 3.15, +26 %); Kurome by day was
  10-20 % high (0.94 -> 0.85 m/s), Myoshoji day clip 0.52 -> 0.50. By day, a station that fails is
  **retried with the night speck enhancement** (`Buffers` has a second channel; `medir(...,
  buffers_motas)`): Myoshoji stations 6-8 (shadowed water with drifting bubbles by the right wall)
  now measure 0.02-0.05 m/s at the 60 s scale, 9/9 stations after 70 s; console prints R/M/L in
  capitals and the CSV `modo` reads `dia+motas`. Myoshoji lines 6 -> 9 m. New preset `shimoda`
  (`bpL7MAbdoI8`): water flows right-to-left *toward* the bridge, assumed 12 x 5 m, v_esperada 0.6;
  on a rainy day only the near half (stations 4-8, ~1.35 m/s) resolves at 15 fps.
  Preset `akigawa` (`ZRUh9gNk8-g`, Aki river at Todohara) was added on request but **does not
  measure**: heavily compressed stream, codec-frozen water and standing waves keep coherence at
  0.1-0.36 everywhere (tried sub-zones, sampling, speck mode, a temporal high-pass: max 0.37).
  COH_MIN was deliberately not lowered for it.
  **Directional filter** (`filtro_direccional`, per camera, on only for `shimoda`): zeroes the STI
  spectrum quadrants of upstream-moving patterns. Fast water (1-1.5 m/s) with near-regular ripples
  aliased at 15 fps into a cross-hatched STI (real "\\" + stroboscopic "/"), giving opposite signs at
  neighbouring stations; with the filter Shimoda goes from 0-6 to 156-162 accepted station-measures
  in 90 s, median 0.94-1.00 m/s invariant to DS 2-4 px (an artifact would track DS). It imposes the
  flow sense, so it is not global: on Kurome it would lower 0.86 -> 0.66 m/s (closer to an ensemble
  correlation, 0.72), Myoshoji -7-10 %, and on `akigawa` it "measures" ~0.7 m/s that drifts +20 %
  with DS -- not trusted.
- **Validated against reference data (2026-10-13/14), `validacion/`.** Videos with independent
  references are run through **this same code** (`validacion/correr.py` imports `stiv_directo.py`;
  only geometry and per-camera parameters are set, method parameters are the program's). Sile Main
  Canal on the *unstabilised* original: 11/11 verticals, **Q +1.2 %** vs the ADV gauging. Bradano: the
  block activity rule (half the pixels active) measured **1 of 7** on sparse particles over near-black
  water; `FRACCION_ACTIVA_NOCHE = 0.1` gives 5 of 7 (-4.5 %). It is **night-only on purpose**: at 0.1 by
  day, Heiskanen's sun-glare video went from abstaining to 14/20 stations at +36 %, and glints cannot be
  told from good water by saturation (`destellos.py`). Bradano gets it because a grey video is read as
  IR night. Heiskanen (Oulankajoki, Reolink IP camera, ADCP; dataset in `datasets vision velocimetria/`):
  -14 to -18 % on the near third, unexplained; **sun glints at 13 h pass QC at +33 %** - the program has
  no daytime glint defence. Camera mounted sideways: its Hydro-STIV model is for the native frame
  (`CAP_PROP_ORIENTATION_AUTO` = 0) and the mirror ambiguity was resolved by optical-flow alignment,
  not by the ADCP. `validacion/regresion.py <caso>` replays live-stream recordings (FFV1, in the
  git-ignored `validacion/grabaciones/`, remade with `grabar.py`) to check method changes.
- **Switching sources (2026-10-13).** `fuentes.json` lists streams and recorded videos (camera
  name + `url` or `archivo`, optional `modo` defaulting to auto, optional per-camera `ajustes`).
  `arrancar.bat` with no arguments shows a console menu (`--elegir`); in the window `c` = next,
  `1`-`9` = that entry. `main()` loops over `ejecutar()`, which returns the requested index; the
  reader and measurer threads are stopped and drained on every switch (checked: no threads
  accumulate), the window is reused, and a source that fails to open falls back to the previous one.
  Without the file (the Pi) the list is `CAMARAS`. If the CSV is locked (Excel), it writes to a
  dated CSV instead of crashing.
- **Night and slow water (2026-10-13).** At night Myoshoji measured nothing although debris was
  visibly moving: the water ran ~10x slower than at calibration (~0.05 m/s, **0.1 px per real
  frame**, confirmed by long-lag ensemble correlation with no STIV), so the 10 s frame-by-frame STI
  saw near-vertical streaks, frame-to-frame activity was 0 ("sin textura") and lamp-glare sparkles
  read 5–11 m/s. Fix: **three time scales in cascade** (`ESCALAS`: 10 s per frame, 30 s at
  0.133 s/row, 60 s at 0.5 s/row; slow rows are averages) — each station takes the *first* scale
  with |slope| ≥ `P_MIN` 0.3 samples/row, descends only on "too slow"/"no texture", and slower scales
  reject |slope| > `P_MAX` 2.5 as `ambiguo` (possible aliasing) — plus an **automatic night mode**
  (`--modo auto`: IR camera ⇒ saturation exactly 0) with a 9 px top-hat, temporal-median
  subtraction and **glare exclusion** (median brightness > 60; water 4–41, lamps 59–255). Selection
  is by streak angle, never by coherence. Daytime numbers unchanged (test clip identical, all fast
  scale). Live at night: 5–6 of 9 stations, section median 0.056–0.067 m/s, mostly at the 30 s
  scale. The window now shows **two views** (live + rectified plan view, flow left→right, 1 m scale
  bar) and arrows whose duration adapts so the median is ~1 m. The day test clip is stored grey,
  so it needs `--modo dia`; `raspberry/prueba/myoshoji_noche_90s.mp4` is the night recording.

### `raspberry/` — the same tool on a Raspberry Pi 4B, headless

Added 2026-10-12 so the user can deploy the moment the hardware arrives. `raspberry/LEEME.md` is a
from-zero, step-by-step guide (the user has never used a Pi). PC side: `subir_a_raspberry.bat/.ps1`
packs `stiv_directo.py` + `raspberry/` + every `salidas/*/config_stiv_directo.json` into a tgz,
converts text files to LF, scp's it to `~/stiv` and runs `instalar.sh` over `ssh -t`
(`-SinInstalar` = copy + restart only, `-ConfigurarLlave`, `-SobrescribirConfig`);
`traer_resultados.bat/.ps1` pulls `salidas/` into `salidas_raspberry\`. The `.bat` wrappers exist
because this Windows' execution policy is undefined, i.e. Restricted, for `.ps1`. Pi side:
`instalar.sh` (idempotent: apt, venv with **opencv-python-headless**, `stiv.conf` and camera configs
only if absent, systemd unit from a template), `stiv.sh` (prueba/activar/estado/registro/salud...),
`stiv.conf` (holds `STIV_ARGS`; the unit expands it unbraced so systemd word-splits it), and
`prueba/myoshoji_20s.mp4` (20 s re-encoded to H.264 from frames recorded before YouTube blocked this
PC — good for function and speed, **not** for measurement: re-encoding noise passes `ACTIVIDAD_MIN`).

What changed in `stiv_directo.py` for it: `--fuente` (any non-YouTube URL opened directly; RTSP over
TCP via `OPENCV_FFMPEG_CAPTURE_OPTIONS`; 15 s open/read timeouts), `--camara` accepts **new names**
whose URL and per-camera parameters then live in their JSON (`CAMARA_NUEVA`, `fps_camara` None = no
duplicated frames), `--paso-medida`, `--vista-cada` (atomic PNG write), `STIV_COOKIES` for yt-dlp,
grey+blur only on the lines' bounding box (`Geometria.procesar`, **bit-identical**, 6–8x cheaper),
frame queue 600 → 150, and a summary that reports measurement time and queue backlog.

Tested without a Pi, in an **emulated aarch64 Debian 13 container with systemd + sshd**, driving it
with the real `.ps1`: full install from scratch, `stiv.sh prueba` (same numbers as the PC), service
enabled → survives a container reboot, `-SinInstalar` update, `traer_resultados`. And against a
**mediamtx RTSP server** fed the test clip, including an 8 s interruption. Four real bugs came out of
that, all fixed: a PowerShell function named `Ssh` recursing into itself (names are
case-insensitive); `cv2.destroyAllWindows()` raising in headless OpenCV; after a reconnection the
stream's PTS restart at 0 and `t_ult_medida` was not reset, so nothing was measured until the new t
passed the old one — now every discontinuity (reconnection, backwards PTS, >1 s jump) clears the STI
and **re-anchors** the clock so t keeps growing; and the 600-frame queue peaking at 1.3 GB RAM.
**Not tested**: real Pi 4 speed (emulation says nothing), `journalctl`/`vcgencmd`, mDNS, `sudo`
password over `ssh -t`, `-ConfigurarLlave`, a real Hikvision.

That test bench is kept, reproducible, in **`pruebas_docker/`** (deliberately *outside* `raspberry/`,
whose contents all ship to the Pi): `pi_falsa/Dockerfile` (Debian 13 arm64, systemd, dbus, sshd,
user `stiv` with passwordless sudo), `docker-compose.yml` (`stiv-pi-falsa` on `localhost:2222`,
`stiv-rtsp-srv` mediamtx on 8554, `stiv-rtsp-pub` looping the test clip as a fake IP camera), and
`probar_en_docker.ps1/.bat` which brings it up, plants a test key in `pruebas_docker/.llave/` (never
the user's `~/.ssh`), runs the real `subir_a_raspberry.ps1` against it and then `stiv.sh prueba`;
`-Parar`/`-Arrancar` stop and restart the containers keeping everything (the user asked that sessions end with **stop, never delete**); `-Bajar [-BorrarImagenes]` deletes them. Container names are prefixed `stiv-` because this Docker
also holds ~10 unrelated containers of the user's.

## Picking the next dataset

`datasets_prueba_pyorc.xlsx` ranks 17 candidate datasets by how useful they are for *testing pyorc*
given what is already done (sheets: `Ranking`, `Ya procesados`, `Leyenda`; 18 columns each, including
`GCPs`, `Datos de validacion` and a `Notas para pyorc` column that names which existing notebook to
use as the template).

- **#1 Hommerich (Geul, NL)** — zero friction, fetched straight from the library via
  `pyorc.sample_data.get_hommerich_dataset()`, with 6 RTK GCPs and a fully resolved camera config
  including lens distortion. Template is Ngwerere (oblique, ≥4 GCPs), *not* the SMC 2-point nadir
  trick. It is also the only candidate that exercises optical water-level estimation, which neither
  finished notebook uses.
- **#2 Castor River** — closest validation chain to SMC (FlowTracker ADV + ADCP) but on a fixed
  camera; see the stub above. **No longer blocked**: the HARMONIOUS zip has been downloaded and
  `CastorRiver/` now exists under `datasets vision velocimetria\data\`, with two dates
  (`20190410/Video1..3`, `20190709/Video4`) plus a `Reference/` folder each. What remains wrong is
  only the *path* in `Prueba_Castor_River.ipynb`, which still points at a `CastorRiver\` inside the
  workspace that was never created.

Ten of the 17 rows come from that same HARMONIOUS zip, **all of which is now on disk** (13 rivers;
see the section above for the layout). GCP availability is confirmed only for Hommerich — the legend
flags it. Note what the HARMONIOUS releases do *not* have: bathymetry. They are good for testing
velocimetry against reference velocities and useless for testing a discharge chain, which is why
both live HARMONIOUS cases stop at surface velocity.
