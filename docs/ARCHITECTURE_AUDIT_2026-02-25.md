# UpRight.os Architecture Audit

**Date:** 2026-02-25  
**Auditor:** Cascade  
**Scope:** Full codebase review for state-of-the-art improvements

---

## Executive Summary

UpRight.os is a well-structured robotics control platform with strong foundations in safety, modularity, and observability. The architecture shows evidence of iterative hardening and thoughtful separation of concerns. This audit identifies **improvements**, **removals**, and **additions** to elevate the system to aerospace-grade standards.

---

## 1. Architecture Overview

### Layer Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    UI Layer (React/Vite)                    │
│  ops-console: App.tsx, CodexPanel, WorkbenchPanel          │
├─────────────────────────────────────────────────────────────┤
│                   API Layer (HTTP/SSE)                      │
│  server.py: 15k lines, ThreadingHTTPServer                 │
├─────────────────────────────────────────────────────────────┤
│                 Intelligence Layer                          │
│  codex_agent.py, codex_tools.py, codex_rag.py, tuning_policy│
├─────────────────────────────────────────────────────────────┤
│                   Data Layer (SQLite)                       │
│  codex_db.py: telemetry, checkpoints, embeddings, audit    │
├─────────────────────────────────────────────────────────────┤
│                 Hardware Layer                              │
│  serial_gateway.py: NanoSerialGateway                      │
├─────────────────────────────────────────────────────────────┤
│                 Firmware Layer (Arduino)                    │
│  balance_mvp_v1.ino: PID, Kalman, EEPROM config            │
└─────────────────────────────────────────────────────────────┘
```

### Strengths Observed

| Area | Strength |
|------|----------|
| **Safety** | PreArmSafetyGate, preflight checks, action guards, estop handling |
| **Modularity** | Clean separation: `clean_*.py` modules, provider_router, arm_safety |
| **Observability** | Telemetry logging, tool audit, config history, burst capture |
| **Testing** | 55+ test files, good coverage of critical paths |
| **Documentation** | Extensive PRDs, scorecards, handoff docs, ground rules |
| **Firmware** | Versioned config structs, CRC validation, sanitization |

---

## 2. IMPROVEMENTS (Refactoring Opportunities)

### 2.1 Server.py Decomposition (Critical)

**Current:** `server.py` is **15,350 lines** — a monolith handling routing, business logic, and utilities.

**Recommendation:** Decompose into focused modules:

| New Module | Responsibility | Est. Lines |
|------------|----------------|------------|
| `routes/tuning.py` | `/pid`, `/motion`, `/limits`, `/setpoint` endpoints | ~500 |
| `routes/firmware.py` | Firmware compile/upload/recovery | ~800 |
| `routes/codex.py` | AI chat, tool orchestration | ~600 |
| `routes/profiles.py` | Robot profile management | ~400 |
| `routes/commissioning.py` | Commissioning workflows | ~400 |
| `routes/health.py` | Status, health, diagnostics | ~300 |
| `core/control_state.py` | ControlState class | ~200 |
| `core/request_handler.py` | Base handler, CORS, auth | ~400 |

**Impact:** Easier testing, faster code navigation, reduced merge conflicts.

---

### 2.2 codex_tools.py Size (127KB)

**Current:** Single file with 3,352 lines containing all tool implementations.

**Recommendation:** Split by tool tier:

| New Module | Tools |
|------------|-------|
| `tools/t1_observation.py` | get_probe_results, query_telemetry, query_checkpoints |
| `tools/t2_experimentation.py` | diff_config, analyze_burst, compare_checkpoints |
| `tools/t3_actuation.py` | simulate_pid_response, param_sweep |
| `tools/shared_analysis.py` | FFT, spectral, phase lag utilities |

---

### 2.3 UI App.tsx Consolidation (122KB)

**Current:** `App.tsx` is 2,712 lines with mixed concerns.

**Recommendation:** Extract into feature modules (partially done with `features/`):
- Move remaining inline components to dedicated files
- Extract state management to context providers
- Separate polling logic into hooks (already have `useBridgePolling`)

---

### 2.4 Firmware Config Version Explosion

**Current:** `MotionConfigV2`, `MotionConfigV3`, `RuntimeConfigV11` with manual migration.

**Recommendation:**
- Add schema versioning with automatic migration chain
- Consider Protocol Buffers or FlatBuffers for firmware config
- Single `FirmwareConfig` with version discriminator

---

### 2.5 Duplicate Import Patterns

**Current:** Every module has try/except import blocks:
```python
try:
    from app.bridge.codex_db import CodexDB
except ImportError:
    from codex_db import CodexDB
```

**Recommendation:** Use a single `imports.py` or fix `PYTHONPATH` setup in all entry points.

---

## 3. REMOVALS (Technical Debt)

### 3.1 Dead/Unused Files

| File | Status | Action |
|------|--------|--------|
| `pcb_preset_sketch_v1.ino` | 0 bytes | Delete |
| `probe_with_motor_tests_v1.ino` | 0 bytes | Delete |
| `esp32_balance_tuner.ino` | 20KB, root level | Move to `generated_firmware/` or delete |
| `tumbller_v06_*` directories | Legacy | Archive or delete if superceded |
| `app_bridge/` (3 items) | Appears to be old bridge code | Audit and remove if unused |

### 3.2 Placeholder Values

| Location | Issue |
|----------|-------|
| `codex_tools.py:2270` | `noise_floor_db: -45` hardcoded placeholder |
| Various | Magic numbers without constants |

### 3.3 Redundant Tests

Review `test_*.py` files for:
- Tests covering deprecated functionality
- Duplicate test coverage across files
- Tests with hardcoded paths that may break

---

## 4. ADDITIONS (State-of-the-Art Enhancements)

### 4.1 Tuning Intelligence System (Already Planned)

16-phase upgrade documented in `TUNING_INTELLIGENCE_PRD.md`:
- Session-based A/B comparison
- Real telemetry metrics
- Neural network tuning model
- Aerospace-grade verification

### 4.2 Telemetry Pipeline Enhancements

| Addition | Value |
|----------|-------|
| **Time-series database** | InfluxDB or TimescaleDB for high-frequency data |
| **Real-time streaming** | WebSocket telemetry stream instead of polling |
| **Anomaly detection** | ML-based drift detection on telemetry |
| **Replay mode** | Full session replay from logged data |

### 4.3 Control System Enhancements

| Addition | Value |
|----------|-------|
| **Adaptive gain scheduling** | Auto-adjust gains based on operating region |
| **Model predictive control (MPC)** | Preview-based control for better disturbance rejection |
| **System identification** | Online parameter estimation for better surrogate models |
| **Loop shaping tools** | Bode/Nyquist visualization in UI |

### 4.4 Safety Enhancements

| Addition | Value |
|----------|-------|
| **Watchdog timer validation** | Firmware watchdog health check |
| **Redundant sensor voting** | Multiple IMU agreement check |
| **Graceful degradation modes** | Defined fallback behaviors |
| **Safety case documentation** | Formal hazard analysis |

### 4.5 DevOps Enhancements

| Addition | Value |
|----------|-------|
| **CI/CD pipeline** | GitHub Actions for test + lint on PR |
| **Firmware release automation** | Versioned binaries with changelogs |
| **Deployment validation** | Automated post-deploy smoke tests |
| **Metrics dashboard** | Grafana for system health visibility |

### 4.6 UI/UX Enhancements

| Addition | Value |
|----------|-------|
| **Tuning Session Panel** | Visual A/B comparison (see PRD Phase 1.5) |
| **3D robot visualization** | Real-time pose rendering |
| **Tuning wizard** | Guided step-by-step tuning flow |
| **Mobile-responsive layout** | Field testing from phone |

---

## 5. Technical Debt Quantification

| Category | Severity | Items | Est. Hours to Fix |
|----------|----------|-------|-------------------|
| Server decomposition | High | 1 | 16-24 |
| codex_tools split | Medium | 1 | 8-12 |
| Dead file cleanup | Low | 5+ | 1-2 |
| Placeholder replacement | Medium | 3+ | 4-8 |
| Import pattern fix | Low | 15+ | 2-4 |
| Test cleanup | Low | Unknown | 4-8 |

---

## 6. Priority Recommendations

### Immediate (This Sprint)

1. **Implement Tuning Intelligence Phase 1** — enables all future tuning improvements
2. **Replace noise_floor_db placeholder** — quick win from Phase 4
3. **Delete dead files** — reduces confusion

### Near-Term (Next 2 Sprints)

4. **Decompose server.py** — enables parallel development
5. **Split codex_tools.py** — improves maintainability
6. **Add WebSocket telemetry** — better real-time UX

### Medium-Term (Next Quarter)

7. **Implement Phases 7-13** — aerospace verification
8. **Add time-series database** — enables advanced analytics
9. **CI/CD pipeline** — automated quality gates

### Long-Term (Roadmap)

10. **Neural network tuning (Phase 14)** — ML-powered recommendations
11. **Model predictive control** — advanced control strategy
12. **3D visualization** — professional UX

---

## 7. SpaceX-Adjacent Gap Analysis

| SpaceX Practice | Current State | Gap |
|-----------------|---------------|-----|
| Formal verification | Manual testing | Add stability margin analysis |
| Monte Carlo validation | None | Add robustness testing |
| Regression test suite | Partial | Add golden trace validation |
| Configuration traceability | Config history exists | Add change request linking |
| Fault injection testing | None | Add systematic fault testing |
| Flight heritage tracking | Checkpoint ratings | Formalize approval workflow |
| Redundant systems | Single IMU | Document single-point failures |
| Telemetry archival | SQLite with 100MB cap | Consider scaled storage |

---

## 8. Files Reviewed

| File | Lines | Notes |
|------|-------|-------|
| `server.py` | 15,350 | Monolith, needs decomposition |
| `codex_tools.py` | 3,352 | Large, needs splitting |
| `codex_db.py` | 793 | Clean, well-structured |
| `codex_agent.py` | 515 | Clean |
| `codex_rag.py` | 572 | Clean |
| `tuning_policy.py` | 248 | Clean, deterministic |
| `serial_gateway.py` | 393 | Clean |
| `surrogate_sim.py` | 298 | Good, could add FOPDT |
| `control_math.py` | 144 | Clean, firmware-parity |
| `trace_replay.py` | 247 | Clean |
| `param_sweep.py` | 323 | Clean |
| `arm_safety.py` | 541 | Clean |
| `provider_router.py` | 145 | Clean |
| `balance_mvp_v1.ino` | 2,090 | Well-structured firmware |
| `App.tsx` | 2,712 | Large, partially decomposed |
| `api.ts` | 1,963 | Clean |
| 55+ test files | ~150K total | Good coverage |

---

## 9. Conclusion

UpRight.os has a **solid foundation** with good safety practices and modularity. The main opportunities are:

1. **Structural**: Decompose large files (server.py, codex_tools.py, App.tsx)
2. **Intelligence**: Implement the 16-phase Tuning Intelligence System
3. **Verification**: Add aerospace-grade proof artifacts
4. **Observability**: Enhanced telemetry and real-time streaming

The proposed Tuning Intelligence PRD addresses many of these gaps. Executing Phases 1-16 will transform the system from "good" to "state-of-the-art."

---

## Appendix: Quick Wins

| Task | Impact | Effort |
|------|--------|--------|
| Delete 0-byte `.ino` files | Clean repo | 5 min |
| Replace `-45 dB` placeholder | Accurate metrics | 2 hours |
| Add `PYTHONPATH` to entry scripts | Remove import try/except | 1 hour |
| Create `.github/workflows/test.yml` | Automated testing | 2 hours |
| Add `pre-commit` hook for ruff | Code quality | 30 min |
