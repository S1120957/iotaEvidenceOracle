# \# Experiment Log

# 

# \## Hardware Specification

# 

# | Field | Value |

# |-------|-------|

# | CPU model | Intel Core i7-1255U (12th Gen) |

# | CPU cores | 10 physical, 12 logical |

# | RAM (GB) | 16 GB (16,850,198,528 bytes) |

# | OS | Microsoft Windows 11 Home |

# | IOTA CLI version | 1.23.0-alpha-02f07149a538 |

# | iota-localnet version | 1.22.1-rc-76c92e911009 |

# | Python version | 3.12 |

# | Date of testnet runs | 02 May 2026 |

# 

# \---

# 

# \## IOTA CLI Version

iota 1.23.0-alpha-02f07149a538





\---



\## Network Environment



All experiments were conducted on the \*\*IOTA public testnet\*\*

(`https://api.testnet.iota.cafe`).



The local devnet (`iota-localnet 1.22.1-rc`) was not used for

experiments due to a known faucet initialisation bug on Windows

(`NoGasCoinAvailable` / `client error (Connect)`) in version 1.22.1-rc.

Testnet was used for both the primary benchmark and the external

validity confirmation runs, consistent with Section V.2 of the paper.



\---



\## Deployed Package IDs (Testnet)



| Package | ID |

|---------|-----|

| Design A | `0x1e84478d9b09ca5b8f7bc0508ad4e80d19628250ec13517680ceae67e9d2b47a` |

| Design B | `0xcde5399d72f19436e5c9b8e6c60be94645ee2e5ec23daeae9bfcadfb44b32174` |



| Object | ID |

|--------|-----|

| Wallet address | `0xd0e7976a242007d7ce49087578e46f93ae9b5bbfd8288240c39691905a5572b3` |

| UpgradeCap A | `0x54b01a3ae130edcd1c56cb394c4be74c8380de564f580c99258cd4e845f490b3` |

| UpgradeCap B | `0x3fb6542a685c8c97efdba58124cb68a5be94017f7b899cd9954a322346d9e103` |



\---



\## Move Unit Test Results



| Package | Tests | Passed | Failed |

|---------|-------|--------|--------|

| design\_a | 9 | 9 | 0 |

| design\_b | 7 | 7 | 0 |

| \*\*Total\*\* | \*\*16\*\* | \*\*16\*\* | \*\*0\*\* |



Run with: `iota move test --path contracts\\design\_a`



\---



\## Smoke Test Results (02 May 2026)



| Test | Result |

|------|--------|

| Design B `create\_slot` (owned object) | PASS |

| Design A `submit\_reading` (shared object, 2 sensors) | PASS |

| Design A `finalize` (after grace interval) | PASS |



\---



\## Run Notes



\### Phase 1 — Baseline sweep (testnet, WINDOWS\_PER\_RUN=50)



| Run date | N | Design | Notes |

|----------|---|--------|-------|

| 02 May 2026 | 2,4,8,16,32 | A | In progress |

| 02 May 2026 | 2,4,8,16,32 | B | In progress |



\### Phase 2 — Fault injection (testnet)



| Run date | Fault | Design | Notes |

|----------|-------|--------|-------|

| TBD | F1,F2,F3 | A,B | Pending baseline completion |



\### Phase 3 — Testnet confirmation



Testnet was used as the primary environment. No separate

confirmation run required.



\---



\## Experiment Parameters



| Parameter | Value |

|-----------|-------|

| N (sensor counts) | 2, 4, 8, 16, 32 |

| WINDOWS\_PER\_RUN | 50 |

| WINDOW\_DURATION\_MS | scales with N (base 10,000ms) |

| GRACE\_INTERVAL\_MS | 2,000 ms |

| MAX\_SPREAD\_MS | scales with N |

| GAS\_BUDGET per tx | 20,000,000 NANOS |



\---



\## Deviations from Protocol



1\. \*\*Localnet replaced by testnet\*\* — `iota-localnet 1.22.1-rc` crashes

&#x20;  on Windows with `NoGasCoinAvailable` due to a known faucet timing

&#x20;  bug. All experiments use the public IOTA testnet instead.

2\. \*\*Sequential writes\*\* — The Python harness submits sensor writes

&#x20;  sequentially (one CLI subprocess per write) rather than concurrently,

&#x20;  because no Python SDK exists for IOTA Rebased. Write latency therefore

&#x20;  reflects single-sensor round-trip time rather than concurrent

&#x20;  throughput. This is noted as a threat to external validity in

&#x20;  Section VII.



\---



\## Reproducibility Checklist



Before submitting the paper, confirm:



\- \[ ] Hardware spec table above is complete ✅

\- \[ ] IOTA CLI version recorded ✅

\- \[ ] Unit tests 16/16 passing ✅

\- \[ ] Smoke test 3/3 passing ✅

\- \[ ] Phase 1 baseline CSV present in harness/results/

\- \[ ] Phase 2 fault injection CSV present in harness/results/

\- \[ ] table1\_testnet.csv matches Table 1 in the paper

\- \[ ] table2\_testnet.csv matches Table 2 in the paper

\- \[ ] Section V.2 hardware spec placeholder replaced with values above

\- \[ ] Section VII threats updated with localnet deviation note

\- \[ ] Conclusion updated with actual findings from CSVs





