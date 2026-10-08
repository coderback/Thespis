# Load test: 200 engines at once, Postgres

3 rounds each, a scripted model answering in 400 ms with 32 calls at once; each engine waits 1 to 3 s between its calls. One server process, the engines in 4 client processes. 6000 requests in 65.6 s (91 a second); 0 errors.

| Route | Calls | p50 ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- |
| open | 600 | 20 | 47 | 114 |
| observe | 600 | 17 | 34 | 53 |
| update | 600 | 18 | 43 | 76 |
| decide | 600 | 25 | 72 | 97 |
| line (long poll) | 600 | 411 | 478 | 532 |
| react | 600 | 24 | 78 | 124 |
| tick | 600 | 21 | 57 | 169 |
| narrate | 600 | 21 | 47 | 78 |
| snapshot | 600 | 13 | 31 | 42 |
| close | 600 | 12 | 26 | 37 |
| **engine calls (all but the long poll)** | 5400 | 19 | **50** | 91 |

Garrick's line, asked to final: p50 439 ms, p95 518 ms over 600 lines; sources {'llm': 600}.

Gate: no errors and engine calls p95 at most 250 ms: **pass**.
