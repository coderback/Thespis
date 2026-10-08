# Load test: 50 engines at once, Postgres

3 rounds each, a scripted model answering in 400 ms with 32 calls at once; each engine calls as fast as it can. One server process, the engines in 4 client processes. 1500 requests in 8.2 s (183 a second); 0 errors.

| Route | Calls | p50 ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- |
| open | 150 | 261 | 360 | 410 |
| observe | 150 | 160 | 265 | 300 |
| update | 150 | 144 | 233 | 257 |
| decide | 150 | 129 | 228 | 255 |
| line (long poll) | 150 | 853 | 1889 | 1958 |
| react | 150 | 94 | 202 | 252 |
| tick | 150 | 99 | 278 | 295 |
| narrate | 150 | 99 | 260 | 283 |
| snapshot | 150 | 87 | 240 | 261 |
| close | 150 | 62 | 199 | 220 |
| **engine calls (all but the long poll)** | 1350 | 111 | **281** | 340 |

Garrick's line, asked to final: p50 979 ms, p95 1961 ms over 150 lines; sources {'llm': 150}.

With no time between calls this measures what one process can take, its capacity: 183 requests a second. It isn't the gate.
