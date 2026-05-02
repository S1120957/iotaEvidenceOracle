# Experiment Log

Fill this file before running any experiments.
This file is the source for the hardware specification in the paper
(Section V.2, `% TODO: fill hardware spec before submission`).

---

## Hardware Specification

| Field | Value |
|-------|-------|
| CPU model | |
| CPU cores | |
| RAM (GB) | |
| OS | |
| IOTA CLI version | |
| IOTA SDK version (Python) | |
| Python version | |
| Date of localnet runs | |
| Date of testnet runs | |

---

## IOTA CLI Version

After installing the CLI, run:
```
iota --version
```
Paste the output here:

```
[paste here]
```

---

## Run Notes

### Phase 1 — Baseline (localnet)

| Run date | N | Design | Notes |
|----------|---|--------|-------|
| | | | |

### Phase 2 — Fault injection (localnet)

| Run date | Fault | Design | Notes |
|----------|-------|--------|-------|
| | | | |

### Phase 3 — Testnet confirmation

| Run date | N | Design | Testnet epoch | Notes |
|----------|---|--------|---------------|-------|
| | | | | |

---

## Deviations from Protocol

List any deviation from the methodology described in the paper here.
If there are none, write "None."

---

## Reproducibility Checklist

Before submitting the paper, confirm:

- [ ] Hardware spec table above is complete
- [ ] IOTA CLI version recorded
- [ ] All three phases completed and CSV files present in harness/results/
- [ ] table1_localnet.csv matches Table 1 in the paper
- [ ] table2_localnet.csv matches Table 2 in the paper
- [ ] false_valid_pct = 0 for F1 scenario in both designs
- [ ] % TODO comment in paper Section V.2 has been replaced with actual spec
- [ ] Conclusion section updated with actual findings
