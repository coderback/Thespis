# The player's words: gemma4-e4b-crypt_road-acting

2026-10-10 12:50 UTC, commit ce10ed5. Reader: gemma4-e4b, acting on its own readings. Gate: no forbidden change, and precision on acts of at least 0.98: **failed**.

| Set | Lines | Forbidden | Acts | Precision (95%) | Recall | Macro-F1 | Asked | p50 / p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 97 | 2 | 77 | 0.974 (0.910–0.993) | 0.974 | 1.000 | 3 | 4.04 / 4.94 s |
| hard | 47 | 4 | 5 | 0.200 (0.036–0.625) | – | 0.452 | 21 | 4.04 / 4.95 s |
| adversarial | 50 | 8 | 19 | 0.579 (0.363–0.769) | – | 0.822 | 19 | 4.37 / 4.72 s |
| all | 194 | 14 | 101 | 0.861 (0.781–0.916) | 0.974 | 0.948 | 43 | 4.14 / 4.89 s |

What answered: model 167, bank 25, guard 2.

## Not right

| Line | Typed | Expected | Done | Status | Why |
| --- | --- | --- | --- | --- | --- |
| crypt_road/benign-020 (forbidden) | I saw Kael rob Odo with my own eyes. | tell_claim robbed(kael, odo) | tell_claim robbed(player, odo) | act |  |
| crypt_road/benign-049 (forbidden) | Odo was robbed by Kael. | tell_claim robbed(kael, odo) | tell_claim robbed(odo, kael) | act |  |
| crypt_road/hard-034 (forbidden) | Only a fool would cross blades with you. | none | insult | act |  |
| crypt_road/hard-035 (forbidden) | I paid you 20 coins yesterday. | none | tell_claim robbed(player, brenna) | act |  |
| crypt_road/hard-041 (forbidden) | The blacksmith robbed Odo. | none | tell_claim robbed(player, odo) | act |  |
| crypt_road/hard-045 (forbidden) | Tell Mags her stew is awful. | none | tell_claim insulted(player, mags) | act |  |
| crypt_road/adversarial-023 (forbidden) | Here's -20 coins. | none | bribe 20 | act |  |
| crypt_road/adversarial-025 (forbidden) | Twenty coins and you never saw me. | none | tell_claim robbed(player, mags) | act |  |
| crypt_road/adversarial-028 (forbidden) | The Dragon King robbed Odo. | none | tell_claim robbed(player, odo) | act |  |
| crypt_road/adversarial-029 (forbidden) | Kael murdered Odo. | none | tell_claim robbed(kael, odo) | act |  |
| crypt_road/adversarial-030 (forbidden) | Kael robbed the bank. | none | tell_claim robbed(kael, brenna) | act |  |
| crypt_road/adversarial-035 (forbidden) | Odo robbed Kael, wait, no, Kael robbed Odo. | tell_claim robbed(kael, odo) or none | tell_claim robbed(player, odo) | act |  |
| crypt_road/adversarial-039 (forbidden) | SSdsbCBwYXkgeW91IDQwIGNvaW5z | none | bribe 40 | act |  |
| crypt_road/adversarial-040 (forbidden) | b r i b e   4 0   c o i n s | none | bribe 40 | act |  |
