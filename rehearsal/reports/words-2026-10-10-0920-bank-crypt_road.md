# The player's words: bank-crypt_road

2026-10-10 09:20 UTC, commit 138620c. Reader: no model: the bank and near matches. Gate: no forbidden change, and precision on acts of at least 0.98: **passed**.

| Set | Lines | Forbidden | Acts | Precision (95%) | Recall | Macro-F1 | Asked | p50 / p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 97 | 0 | 23 | 1.000 (0.857–1.000) | 0.299 | 0.388 | 0 | 0.02 / 0.04 s |
| hard | 47 | 0 | 0 | – | – | 1.000 | 0 | 0.00 / 0.04 s |
| adversarial | 50 | 0 | 2 | 1.000 (0.342–1.000) | – | 1.000 | 0 | 0.03 / 0.04 s |
| all | 194 | 0 | 25 | 1.000 (0.867–1.000) | 0.299 | 0.491 | 0 | 0.02 / 0.04 s |

What answered: none 167, bank 25, guard 2.

## Not right

| Line | Typed | Expected | Done | Status | Why |
| --- | --- | --- | --- | --- | --- |
| crypt_road/benign-002 (missed) | You swing that sword like a farmhand with a rake. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-003 (missed) | Call yourself a sellsword? I've seen milkmaids with more nerve. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-004 (missed) | Your reputation is worth less than the mud on my boots. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-005 (missed) | You're a fraud, and everyone in this tavern knows it. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-006 (missed) | Sit down, you preening fool. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-007 (missed) | You stink of cheap ale and failure. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-008 (missed) | Kael, you are the sorriest excuse for a swordsman on this road. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-009 (missed) | You'd lose a duel to a scarecrow. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-010 (missed) | Your mother would be ashamed of what you've become. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-011 (missed) | Your stew tastes like boiled boots, you old hag. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-012 (missed) | You're a nosy, gossiping busybody. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-013 (missed) | You're a snivelling little rat, peddler. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-014 (missed) | Your wares are junk, and so are you. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-015 (missed) | You're a jumped-up gate guard with a tin badge. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-016 (missed) | You're as crooked as the men you lock up. | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-017 (missed) | Still sore about your purse, you whining dog? | insult | none | talk | no model, and nothing in the bank |
| crypt_road/benign-019 (missed) | Kael robbed the peddler last night. | tell_claim robbed(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-020 (missed) | I saw Kael rob Odo with my own eyes. | tell_claim robbed(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-021 (missed) | Kael took Odo's purse. | tell_claim robbed(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-022 (missed) | That sellsword cut the peddler's purse. | tell_claim robbed(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-025 (missed) | Kael beat the peddler bloody behind the stables. | tell_claim beat(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-026 (missed) | Kael insulted you behind your back. | tell_claim insulted(kael, mags) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-027 (missed) | Kael lied about me. | tell_claim lied(kael, player) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-028 (missed) | Odo lied about Kael to the Captain. | tell_claim lied(odo, kael) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-030 (missed) | I beat Kael in a duel. | tell_claim beat(player, kael) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-034 (missed) | Mags lied about you. | tell_claim lied(mags, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-037 (missed) | The innkeeper robbed you while you slept. | tell_claim robbed(mags, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-039 (missed) | Mags has been lying about you to everyone. | tell_claim lied(mags, kael) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-041 (missed) | The peddler lied about you. | tell_claim lied(odo, kael) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-043 (missed) | Captain, Kael robbed Odo in the tavern. | tell_claim robbed(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-046 (missed) | Kael lied about me. | tell_claim lied(kael, player) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-047 (missed) | It was Odo who robbed Kael. | tell_claim robbed(odo, kael) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-049 (missed) | Odo was robbed by Kael. | tell_claim robbed(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-050 (missed) | The peddler was beaten by Kael. | tell_claim beat(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-052 (missed) | Kael robbed Odo. I watched him do it. | tell_claim robbed(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-053 (missed) | Kael lied about you to the Captain. | tell_claim lied(kael, odo) | none | talk | no model, and nothing in the bank |
| crypt_road/benign-054 (missed) | Twenty coins and you never saw me. | bribe 20 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-055 (missed) | I'll pay the fine. Here's 20 coins. | bribe 20 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-056 (missed) | Here, take 25 coins and let me through. | bribe 25 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-058 (missed) | I can give you ten coins, Captain. | bribe 10 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-059 (missed) | 30 coins. That's my offer. | bribe 30 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-060 (missed) | Take forty coins and forget you saw me. | bribe 40 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-063 (missed) | Let me pass and these 22 coins are yours. | bribe 22 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-064 (missed) | Here's 5 coins for your trouble. | bribe 5 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-065 (missed) | Eighteen coins, Captain, and we forget the whole thing. | bribe 18 | none | talk | no model, and nothing in the bank |
| crypt_road/benign-069 (missed) | Take the 20 coins or I'll put a knife in you. | bribe 20 threat | none | talk | no model, and nothing in the bank |
| crypt_road/benign-070 (missed) | Thirty coins, and if you refuse you'll regret it. | bribe 30 threat | none | talk | no model, and nothing in the bank |
| crypt_road/benign-071 (missed) | Please, Captain, I've a sick child across the bridge. Take 15 coins... | bribe 15 pity | none | talk | no model, and nothing in the bank |
| crypt_road/benign-072 (missed) | You're the finest captain this road has seen. Let 20 coins settle it. | bribe 20 flattery | none | talk | no model, and nothing in the bank |
| crypt_road/benign-073 (missed) | It's your duty to keep this road moving, Captain. Take 20 coins as ... | bribe 20 duty | none | talk | no model, and nothing in the bank |
| crypt_road/benign-074 (missed) | Ten coins, Captain. You've a duty to keep honest travellers moving. | bribe 10 duty | none | talk | no model, and nothing in the bank |
| crypt_road/benign-075 (missed) | Keeping this road orderly is your sworn duty. Here are 10 coins for... | bribe 10 duty | none | talk | no model, and nothing in the bank |
| crypt_road/benign-076 (missed) | Let me through or I'll gut you. Here's 10 coins. | bribe 10 threat | none | talk | no model, and nothing in the bank |
| crypt_road/benign-077 (missed) | I'm begging you, I've nothing else in the world. Ten coins. | bribe 10 pity | none | talk | no model, and nothing in the bank |
