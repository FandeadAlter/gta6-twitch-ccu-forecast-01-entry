# GTA VI Twitch CCU forecast — DESIGN (Step 1)

Kompetisi: `gta6-twitch-ccu-forecast-01`. Deadline entri: 19 Nov 2026 08:00 WIB.
Skor: mean pinball loss skala log atas 23 jam x 5 kuantil; harus mengalahkan
house baseline (~0,387 pada 4 practice case, menurut RULES.txt).
Program: `main.py`, Python 3.13, stdlib only, deterministik, tanpa network,
maks 8 detik per case, output `{"hours": [{"hour": h, "q": [q05..q95]}]}`.

## 1. Fakta yang dibaca dari kit

- `starter/main.py` = baseline house, terverifikasi angka-per-angka terhadap
  output starter pada p00 (jam 2: [18249,67; 21111,05; 23357; 25841,89;
  29893,67] untuk p1 = 23.357): `q_tau(h) = p1 * exp(z_tau * 0,15 * sqrt(h-1))`,
  median datar di p1 untuk semua jam, spread melebar seperti random walk.
- Input case: `known` = print jam 1 (viewers + channels + reads);
  `comparables` = 38 launch (42 di final, termasuk 4 practice launch),
  masing-masing ~17 hari x 24 jam (14 hari sebelum s.d. 3 hari sesudah
  release day), dari SullyGnome (rata-rata viewers per jam).
- Kebenaran jam 2..24 dari ke-4 practice launch TIDAK ada di file `.in`
  (server-side). Backtest lokal = tiap comparable sebagai satu pseudo-case:
  jam 1 sebagai known, jam 2..24 sebagai truth.
- Practice launch (jam-1 print): Wolverine 23.357 (619 ch), RDR2 116.550
  (2.435 ch), God of War Ragnarök 269.517 (2.709 ch), Spider-Man 2 119.087
  (1.784 ch). Keempatnya console-only, unlock rolling midnight local.
  GTA VI: PS5 + Xbox Series, single-player, tanpa PC, unlock rolling
  midnight lokal (NZ 18 Nov 11:00Z, CET 23:00Z, UK 19 Nov 00:00Z,
  US East 05:00Z, US West 08:00Z).

## 2. Temuan bentuk kurva (37 comparable usable; GTA pre-release dibuang — tak punya release day)

### 2.1 Dua rezim, bukan satu kurva

Populasi comparable adalah campuran dua rezim unlock yang bentuknya
sangat berbeda:

| rezim | ciri jam 1 | contoh | viewers jam 19 / jam 1 |
|---|---|---|---|
| Sudah live saat jam 1 (rolling midnight / early access / unlock sebelum 00:00Z) | viewers besar, channels >= ~200 | Elden Ring, Zelda, CoD, Hogwarts | 0,8x – 3,6x (median ~1,9x) |
| Belum unlock saat jam 1 (simultaneous global unlock siang UTC, mis. 14:00Z) | viewers ratusan, channels < ~150 | Silksong (164 viewers, 14 ch), Kingdom Come 2 (414, 9 ch), Helldivers 2 (419, 6 ch), Battlefield 6 (2.470, 87 ch), Baldur's Gate 3 (3.447, 105 ch) | 47x – 1.874x |

Penyebabnya mekanis: pada jam 1 (00:00–01:00 UTC), launch rolling sudah
dinyalakan di NZ + Asia + Eropa + UK; launch simultaneous baru menyala
berjam-jam kemudian, sehingga jam 1-nya hanya baseline pra-rilis.

### 2.2 Bentuk median (rasio terhadap jam 1)

- Semua 37 launch: turun ke 0,73x di jam 4, pulih ~0,9x di jam 8,
  naik ke puncak 2,40x di jam 19–20, turun ke 2,04x di jam 24.
  Simpangan baku log-ratio membengkak 0,30 (jam 2) → 2,17 (jam 19+):
  campuran rezim, bukan ketidakpastian yang sebenarnya.
- Rolling-only (n=12, kata kunci "rolling"/"midnight local" di `unlock`):
  0,89x (jam 2) → 0,72x (jam 4, titik terendah) → 0,97x (jam 6, unlock
  US East) → ~1,0x (jam 7–12) → 1,42x (jam 15) → 1,90x (jam 19) →
  puncak 2,19–2,28x (jam 20–21) → 1,74x (jam 24). SD log-ratio jauh
  lebih kecil dan stabil: 0,15 (jam 2) → 0,62–0,69 (jam 15–24).
- Puncak per launch rolling: jam 18–22 pada 9 dari 12 launch; pengecualian
  adalah launch dengan unlock PC simultan global sebelum/saat jam 1
  (Elden Ring puncak 0,95x, Cyberpunk 1,26x di jam 2 — jam 1-nya sudah
  berisi surge PC global). GTA VI tanpa PC di launch → kelompok ini
  kurang relevan; analog terdekat adalah console-only rolling:
  Ghost of Yōtei (puncak 3,62x jam 21), Zelda (2,66x jam 19),
  FFVII Rebirth (2,24x jam 21), The Last of Us II (1,34x jam 20).
- Pencilan dalam rolling: Resident Evil Requiem (jam 19 = 11,57x,
  jam 20 = 12,14x) — unlock PC belakangan mengontaminasi kurvanya;
  layak diturunkan bobotnya, bukan dijadikan ekor distribusi.

### 2.3 Sinyal rezim yang tersedia saat runtime (final h00)

- Channels jam 1: practice 619–2.709; semua launch "belum unlock"
  punya channels jam 1 <= 126. Ambang ~200 channels memisahkan bersih.
- Rasio p1 / baseline pra-rilis (median viewers 72 jam sebelum release
  day): practice 47x–916x; TIDAK bersih sebagai pemisah — launch
  early-access (Hogwarts 1,1x, Diablo IV 1,4x, Starfield 1,4x) sudah
  ramai sebelum release day, tapi mereka tetap rezim "sudah live"
  (kurva datar, bukan ledakan). Channels jam 1 adalah sinyal utama;
  rasio p1/baseline hanya pendukung.

## 3. Hasil backtest Step 1 (`score.py`)

Mean pinball loss (skala log; makin rendah makin baik). Evaluasi
in-sample (tiap launch ikut membentuk kuantilnya sendiri) — jadi angka
v0 bersifat optimistis; Step 2 wajib leave-one-out (lihat §5).

| model | semua (n=37) | rolling (n=12) | simultaneous (n=8) | live ch>=200 (n=28) |
|---|---|---|---|---|
| baseline house | 0,9297 (cov 0,62) | 0,3568 (cov 0,79) | 1,6320 (cov 0,51) | 0,3314 (cov 0,78) |
| v0-all (median + kuantil empiris, n=37) | **0,6782** (cov 0,89) | 0,3491 (cov 0,98) | **1,1120** (cov 0,87) | 0,3573 (cov 0,94) |
| v0-roll (idem, n=12 rolling) | 0,8221 (cov 0,64) | **0,2732** (cov 0,83) | 1,4897 (cov 0,46) | 0,2833 (cov 0,78) |
| v0-live (idem, n=28 live) | 0,8346 (cov 0,69) | 0,2921 (cov 0,88) | 1,5209 (cov 0,58) | **0,2671** (cov 0,86) |

Typical miss (median |log error|) pada subset rolling:
baseline 71,7% → v0-all 55,8% → v0-roll 54,3%.

Per jam (subset rolling): v0-roll menang di hampir semua jam, paling besar
di jam akhir — jam 19: baseline 0,4914 vs v0-roll 0,3166; jam 20: 0,5054
vs 0,3232 — karena median baseline datar di 1,0x sementara kebenaran
median naik ke ~2x. Di jam 2–5 semua model bentuk menang tipis
(mis. jam 4: baseline 0,2643 vs v0-roll 0,1341; penurunan dini hari
adalah pola nyata, bukan noise).

### 3.1 Mengapa v0-all hampir tidak mengalahkan baseline pada populasi yang dinilai

v0-all memang yang terbaik pada campuran semua launch (0,6782 vs 0,9297),
tapi pada subset rolling hanya 0,3491 vs baseline 0,3568: median yang
benar (+~2x di jam akhir) hampir habis dimakan oleh ekor q95 yang absurd
(q95 jam 19 = 336x jam 1, dari launch simultaneous) — coverage 0,98
terlalu lebar; tiap kuantil jauh dari kebenaran membayar pinball di
semua jam. Pelajarannya: **kuantil empiris atas campuran dua rezim
bukanlah kuantil yang jujur untuk satu rezim**. Populasi yang dinilai
(4 practice + final GTA VI) seluruhnya rezim rolling console — kolom
rolling adalah kolom keputusan, kolom semua-launch hanya kejujuran
pelaporan.

### 3.2 Mengapa bentuk ternormalisasi harus mengalahkan persistence

1. Median bergerak jauh dari 1,0x (0,72x → 2,28x) dengan pola yang
   sama di hampir semua launch rolling — baseline yang datar salah
   sistematis, bukan acak: ia meremehkan jam sore/malam hingga ~2x.
2. Ketidakpastian log-ratio pada rezim rolling kecil dan stabil
   (SD ~0,65 di jam akhir, vs 0,15 di jam 2) — spread yang jujur
   jauh lebih sempit daripada spread baseline (sigma 0,15*sqrt(h-1)
   yang di jam 24 memberi q95/q05 = 10,7x, sementara q95/q05
   empiris rolling jam 24 ≈ 6x/0,9x).
3. Pinball loss menghargai kuantil yang jujur: kuantil empiris
   per jam atas distribusi yang tepat adalah peramal optimal untuk
   distribusi itu — tidak ada asumsi distribusi lain yang diperlukan.

## 4. Model final yang diusulkan untuk Step 2

`main.py` saat runtime (hanya stdlib, dari satu file case):

1. **Deteksi rezim dari case itu sendiri** (bukan dari nama game):
   `live = channels_jam1 >= 200` (dan p1 jauh di atas baseline pra-rilis
   sebagai cek pendukung). Jika live → pakai bentuk rolling/live;
   jika tidak live → pakai bentuk campuran/simultaneous (v0-all) sebagai
   pengaman bencana (q95 besar, median naik puluhan kali lipat).
   Untuk final GTA VI, live hampir pasti benar (UK + Eropa sudah unlock
   saat jam 1; channels pra-rilis saja sudah 181 pada 17 Nov).
2. **Median bentuk**: median log-ratio per jam atas subset rolling,
   dengan bobot: console-only rolling dan (di final) ke-4 practice
   launch berbobot tertinggi; launch multiplatform dengan unlock PC
   simultan (Elden Ring, Cyberpunk) dan early-access (Hogwarts) bobot
   rendah; Resident Evil Requiem diturunkan bobotnya (pencilan PC).
   Median dihaluskan lintas jam (mis. median bergerak 3 jam) dengan
   mempertahankan fitur nyata: lembah jam 3–4, lompatan jam 6 (US East),
   puncak jam 19–21.
3. **Spread**: kuantil empiris per jam dari subset yang sama, DENGAN
   regularisasi ekor — n=12 membuat q05/q95 empiris pada dasarnya
   min/maks (RE Requiem mendorong q95 jam 19 ke 6,02x). Kandidat yang
   dibandingkan di Step 2 (evaluasi leave-one-out): (a) kuantil empiris
   mentah; (b) lognormal per jam (median + sigma dari IQR, sigma
   dipotong dan dihaluskan lintas jam); (c) winsorize log-ratio per jam
   pada persentil 10/90 sebelum mengambil kuantil.
   Spread harus tumbuh dari jam 2 (SD ~0,15–0,20) ke jam akhir
   (SD ~0,65), bukan seperti baseline yang tumbuh sebagai sqrt(h-1).
4. **Pengaman format**: q monotonik tak menurun, > 0, <= 1e9,
   23 baris jam 2..24, deterministik (tanpa acak), runtime jauh di
   bawah 8 detik (komputasi atas <= 42 comparable x ~408 titik itu
   trivial; bila perlu, konstanta bentuk dihitung dari case saat runtime,
   bukan di-hardcode — supaya program tetap benar bila case berubah).

## 5. Yang harus dikerjakan di Step 2 (belum dikerjakan)

- Evaluasi **leave-one-out** untuk semua kandidat (median mentah vs
  halus, kuantil empiris vs lognormal vs winsorized, bobot subset) —
  angka Step 1 di atas in-sample dan bias optimistis, terutama v0-roll
  dengan n=12.
- Uji sensitivitas ambang deteksi rezim (channels 100/200/300) dan
  perilaku fallback bila channels null.
- Cek apakah ada sinyal tambahan dalam case yang memprediksi rasio
  puncak di dalam rezim rolling (mis. viewers per channel jam 1,
  baseline pra-rilis, ukuran h1) — bila tidak ada, jangan dipaksakan.
- Tulis `main.py` (bukan di Step 1), lalu uji: format output, byte
  deterministik pada 2 run, runtime, dan skor backtest LOO vs baseline.

## 6. File Step 1

- `score.py` — scorer pinball skala log + harness backtest (baseline,
  v0-all, v0-roll, v0-live; matriks loss model x subset; per jam;
  statistik bentuk). Jalankan: `python3 score.py`.
- `DESIGN.md` — file ini.

## 7. Step 2 — implementasi main.py dan evaluasi leave-one-out

### 7.1 Yang dibangun

- `main.py` — entry program (stdlib only, deterministik, tanpa network).
  Membaca `MAKEFUN_INPUT_DIR`/`MAKEFUN_OUTPUT_DIR` seperti starter,
  memproses tiap `*.in`, menulis `*.out`.
- `eval_loo.py` — harness evaluasi LOO (alat dev, bukan bagian entri):
  tiap comparable usable (37) di-held-out sebagai pseudo-case, diramal
  oleh `main.forecast_case()` dari comparables sisanya saja.
- Ketersediaan field (dicek, bukan ditebak): `unlock` dan `platforms`
  ada di semua 38 comparable; `hourly[].channels` ada di jam 1 semua
  launch usable. Pseudo-comparable GTA VI pra-rilis terbuang otomatis
  oleh filter "punya jam 1 + >= 20 jam release day" (ia belum punya
  release day). Semua 38 comparable identik di p00–p03 (asserted).

### 7.2 Aturan yang diimplementasikan (dihitung saat runtime dari case)

- Deteksi rezim: `channels jam 1 >= 200` = live (celah bersih 126 vs 210);
  bila channels null, fallback `viewers jam 1 >= 10.000`.
- Pool live = unlock mengandung "rolling"/"midnight local" ATAU
  (console-only DAN live di jam 1); bobot console-only x3; trim bentuk:
  launch dengan jarak rata-rata |log-ratio − median| > 1,0 atas jam 2..24
  bobotnya x0,25 (di data kit tepat satu launch kena: Resident Evil
  Requiem, jarak 1,33; berikutnya 0,65 — tanpa menyebut nama game).
- Pool tidak-live = semua comparable, bobot 1, tanpa trim.
- Median log-ratio dihaluskan (moving average 3 jam); spread kandidat
  (a) raw, (b) lognormal (median + sigma dari IQR/1,349, sigma
  dihaluskan, floor 0,05 cap 1,5), (c) winsorized (clip di q10/q90).
- **Koreksi saat implementasi — spread per rezim.** Uji asap fallback
  tidak-live menemukan cacat: pool semua-comparable itu bimodal
  (klaster rolling ~1x dan klaster simultaneous 50–1000x), sehingga fit
  lognormal menghancurkan ekor atasnya: untuk Silksong (jam 1 = 164,
  kebenaran jam 19 = 307.362) lognormal memberi q95 = 2.423. Karena itu
  fallback tidak-live SELALU memakai kuantil empiris mentah ("raw"),
  apa pun nilai SPREAD. Setelah perbaikan, q95 jam 19 Silksong = 40.526
  dan loss-nya 2,72 vs baseline 3,94.

### 7.3 Hasil LOO (mean pinball loss; in-sample Step 1 TIDAK dipakai lagi)

| model (spread rezim live) | rolling (n=12) | semua (n=37) |
|---|---|---|
| baseline house | 0,3568 (cov 0,79; miss 71,7%) | 0,9297 (cov 0,62) |
| v0-roll LOO (Step 1, tanpa bobot/halusan/trim) | 0,3304 (cov 0,78; miss 65,7%) | 0,8406 |
| raw | 0,3119 (cov 0,74; miss 59,2%) | 0,6670 (cov 0,70) |
| **lognormal (dipilih)** | **0,3015 (cov 0,81; miss 59,2%)** | **0,6608 (cov 0,76)** |
| winsorized | 0,3194 (cov 0,64; miss 59,2%) | 0,6743 (cov 0,62) |
| lognormal-R1 (pool keyword-only, n=12) | 0,3188 (cov 0,85; miss 65,2%) | 0,8385 |

Kandidat terpilih: **lognormal untuk rezim live + raw untuk fallback
tidak-live** (`SPREAD = "lognormal"` di main.py). Alasan: terbaik di
kedua kolom (rolling 0,3015 dan semua 0,6608), coverage 0,81 paling
dekat ke 0,90 yang jujur di antara kandidat yang menang, dan typical
miss pooled 59,2% vs baseline 71,7%. Pool R2 (keyword + console-only
live, n=16) mengalahkan R1 (keyword-only) di kedua kolom, jadi perluasan
pool dipertahankan.

Per jam (LOO, subset rolling, lognormal vs baseline): menang besar di
jam 3–5 (mis. jam 4: 0,1557 vs 0,2643) dan jam 15–24 (jam 20: 0,3582 vs
0,5054; jam 19: 0,3522 vs 0,4914); kalah tipis di jam 2 (0,1103 vs
0,0958 — median hasil halusan tertarik ke lembah jam 3) dan jam 6–13
(±0,01–0,02, praktis seri — di sana median kedua model sama-sama ~1,0x
dan spread lognormal sedikit lebih lebar).

### 7.4 Kejujuran: di mana model kalah

- Per launch (LOO rolling): kalah dari baseline pada ELDEN RING
  (0,3276 vs 0,2108) dan Cyberpunk 2077 (0,3832 vs 0,2299) — keduanya
  launch datar karena unlock PC simultan global sudah masuk di jam 1.
  GTA VI tanpa PC di launch, jadi kedua analog ini paling tidak relevan;
  model menang besar pada analog console (Yōtei 0,2788 vs 0,4734;
  Zelda 0,1702 vs 0,3087; CoD BO6 0,1450 vs 0,2620; MHW 0,2974 vs
  0,4273; FFVII Rebirth 0,1440 vs 0,1734). Kalah tipis juga pada
  Hogwarts (0,2922 vs 0,2881) dan TLOU2 (0,2652 vs 0,2470).
- Margin antar kandidat spread kecil (lognormal vs raw: 0,0104 pada
  n=12) — pemilihan lognormal didukung juga oleh coverage yang lebih
  baik, bukan hanya selisih loss.
- LOO tetap bukan practice score: kebenaran 4 practice launch tidak
  tersedia lokal; angka di atas adalah atas comparable, bukan atas
  Wolverine/RDR2/GoW/SM2.

### 7.5 Validasi format + determinisme + runtime (4 practice case)

- Output: tepat 23 baris jam 2..24, q monotonik tak menurun, semua
  > 0 dan <= 1e9, ukuran 1.447–1.567 byte (batas 65.536) — semua lolos.
- Determinisme: dua run penuh byte-identical (`diff -r` bersih).
- Runtime per case (single-case, termasuk start Python): 83–93 ms
  (batas 8.000 ms).
- Sanity bentuk (p00, p1 = 23.357): median tersirat 0,76x (jam 2) →
  0,71x (jam 3–4) → 2,21x puncak (jam 21) → 1,96x (jam 24);
  q95/q05 jam 20 = 5,55x.

### 7.6 File Step 2

- `main.py` — entri (SPREAD default "lognormal"; fallback tidak-live
  selalu "raw").
- `eval_loo.py` — harness LOO + uji asap fallback. Jalankan:
  `python3 eval_loo.py`.

### 7.7 Kalibrasi conformal (perubahan pasca-Step 2, 2026-11-17)

Eksperimen LOO offline (`~/workspace/makefun/gta-loo-exp/RESULTS.md`,
Exp. 1) menemukan spread live sistematis ~30% terlalu sempit
(coverage 0,808 vs nominal 0,90). Diterapkan: pengali sigma tetap
`SIGMA_MULT = 1,30` pada cabang lognormal rezim live saja
(satu baris di `spread_log_quantiles`); fallback tidak-live tidak
diubah; pengali per-target dan koreksi CQR aditif ditolak, begitu pula
shrinkage hierarkis (Exp. 2, ditolak di semua bobot).

Verifikasi dengan `eval_loo.py` atas `main.py` yang sudah diubah
(mereproduksi angka eksperimen dengan tepat):
rolling lognormal 0,3015 → **0,2978**, coverage 0,81 → **0,90**;
semua launch 0,6608 → **0,6564**, coverage 0,76 → 0,85.
Typical miss tidak berubah (59,2%) — median tidak disentuh, sesuai
harapan. Format output dicek ulang: 4 practice case tetap valid
(1.436–1.560 byte).

