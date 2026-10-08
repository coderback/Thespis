# Load test: 200 engines at once, SQLite

3 rounds each, a scripted model answering in 400 ms with 32 calls at once; each engine waits 1 to 3 s between its calls. One server process, the engines in 4 client processes. 6000 requests in 64.1 s (94 a second); 0 errors.

| Route | Calls | p50 ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- |
| open | 600 | 13 | 29 | 67 |
| observe | 600 | 13 | 27 | 38 |
| update | 600 | 13 | 32 | 55 |
| decide | 600 | 17 | 43 | 71 |
| line (long poll) | 600 | 405 | 484 | 545 |
| react | 600 | 16 | 37 | 49 |
| tick | 600 | 14 | 29 | 41 |
| narrate | 600 | 14 | 28 | 37 |
| snapshot | 600 | 10 | 22 | 29 |
| close | 600 | 9 | 19 | 30 |
| **engine calls (all but the long poll)** | 5400 | 13 | **31** | 49 |

Garrick's line, asked to final: p50 425 ms, p95 502 ms over 600 lines; sources {'llm': 600}.

Gate: no errors and engine calls p95 at most 250 ms: **pass**.
