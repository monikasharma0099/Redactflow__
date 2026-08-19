# RedactFlow v2 — Latency Benchmarks

Hardware-dependent; values measured on the generation machine (CPU-only, no GPU).

## Regex detection layer (per document)

- Documents: 60
- Mean: **0.101 ms**
- p95: **0.14 ms**
- Max: 0.227 ms

## Synthetic replacement generation

- Generations: 1000
- Mean: **0.02 ms**
- p95: **0.0499 ms**

## Masking latency (800x600 image, 3 detections)

| Style | Mean (ms) | p95 (ms) |
|---|---|---|
| blur | 1.123 | 2.098 |
| pixelate | 0.277 | 0.324 |
| blackbox | 0.265 | 0.653 |
| redbox | 9.866 | 11.322 |
| whitebox | 0.219 | 0.297 |
| synthetic | 10.785 | 12.121 |
