# PRD: Project-Level Agent Rules System (`.codexrules`)

**Version:** 2.0  
**Status:** Implemented  
**Author:** Cascade  
**Date:** 2026-02-18  
**Last Updated:** 2026-02-18  

---

## 1. Overview

### 1.1 Problem Statement

The Codex agent currently relies on hardcoded system prompts embedded in `server.py`. This creates several issues:

- **Inflexibility:** Changing agent behavior requires code changes and server restarts
- **No version control:** Prompt changes are buried in application code
- **No project-level customization:** All projects use the same base prompt
- **Repetitive user guidance:** Operators must re-explain domain concepts each session
- **Missing domain expertise:** Agent lacks deep knowledge in PID control, robotics, electrical engineering, and related disciplines

### 1.2 Solution

Implement a `.codexrules` file system—modeled after Windsurf's `.windsurfrules`—that:

1. Lives at the repository root
2. Is automatically loaded on every chat request
3. Contains agent identity, behaviors, and **comprehensive engineering domain knowledge**
4. Supports hot-reload without server restart
5. Layers with per-robot profile instructions

### 1.3 Inspiration: Windsurf's `.windsurfrules`

This implementation mirrors how Windsurf IDE configures its AI assistant (Cascade):

| Windsurf Pattern | UpRight Implementation |
|------------------|------------------------|
| `.windsurfrules` at workspace root | `.codexrules` at repo root |
| Loaded on every chat session | Loaded on every chat request |
| Defines role, behaviors, constraints | Defines role, behaviors, domain expertise |
| Hot-reloads on file change | Hot-reloads via mtime check |
| Layers with user preferences | Layers with robot profile instructions |

### 1.4 Success Criteria

| Metric | Target |
|--------|--------|
| Agent follows rules file directives | 100% of chat requests |
| Hot-reload latency | < 50ms |
| Backward compatibility | Existing profiles still work |
| Zero server restarts needed for rule changes | Yes |
| Agent demonstrates domain expertise in responses | Qualitative review |

---

## 2. User Stories

### 2.1 Operator
> *"As an operator, I want the Codex agent to already know PID tuning theory and our commissioning workflow so I don't have to explain it every session."*

### 2.2 Team Lead
> *"As a team lead, I want to version-control our agent's behavior and domain knowledge so we can review changes and roll back if needed."*

### 2.3 Developer
> *"As a developer, I want to customize the agent's behavior and add domain knowledge without modifying Python code."*

### 2.4 New Team Member
> *"As a new team member, I want to read a single file to understand how our AI assistant is configured and what it knows."*

### 2.5 Engineering Student
> *"As a student, I want the agent to explain the math behind its recommendations so I can learn control theory while tuning."*

---

## 3. Functional Requirements

### 3.1 File Discovery

| Requirement | Description |
|-------------|-------------|
| **FR-1** | System SHALL look for `.codexrules` at repository root |
| **FR-2** | If `.codexrules` does not exist, system SHALL fall back to hardcoded default prompt |
| **FR-3** | File format SHALL be plain text (Markdown recommended for readability) |

### 3.2 Loading Behavior

| Requirement | Description |
|-------------|-------------|
| **FR-4** | System SHALL cache file contents to avoid repeated disk reads |
| **FR-5** | System SHALL reload file if modification time changes |
| **FR-6** | System SHALL log when `.codexrules` is loaded or reloaded |
| **FR-7** | System SHALL handle file read errors gracefully (log warning, use fallback) |

### 3.3 Prompt Construction

| Requirement | Description |
|-------------|-------------|
| **FR-8** | `.codexrules` content SHALL be prepended to the system prompt |
| **FR-9** | Profile-specific `instructions` SHALL be appended after `.codexrules` |
| **FR-10** | Action policy block SHALL be appended last |
| **FR-11** | Sections SHALL be separated by double newlines for LLM readability |

### 3.4 Priority Order

```
1. .codexrules           (project-level defaults)
2. profile.instructions  (per-robot customization)
3. action_block          (apply permissions based on policy)
```

---

## 4. Non-Functional Requirements

| Requirement | Description |
|-------------|-------------|
| **NFR-1** | File read latency SHALL be < 10ms for cached reads |
| **NFR-2** | System SHALL NOT crash if `.codexrules` contains invalid UTF-8 |
| **NFR-3** | Implementation SHALL NOT introduce new dependencies |
| **NFR-4** | Code changes SHALL be minimal and localized to `server.py` |

---

## 5. Technical Design

### 5.1 New Function: `_load_codexrules()`

```python
_codexrules_cache: Dict[str, Any] = {"content": None, "mtime": 0.0}

def _load_codexrules(repo_root: pathlib.Path) -> str:
    """
    Load .codexrules from repo root if it exists.
    Caches content and reloads only if file modified.
    """
    global _codexrules_cache
    rules_path = repo_root / ".codexrules"
    if not rules_path.exists():
        return ""
    try:
        mtime = rules_path.stat().st_mtime
        if _codexrules_cache["mtime"] == mtime and _codexrules_cache["content"] is not None:
            return str(_codexrules_cache["content"])
        content = rules_path.read_text(encoding="utf-8").strip()
        _codexrules_cache = {"content": content, "mtime": mtime}
        logger.info(f"Loaded .codexrules ({len(content)} chars)")
        return content
    except Exception as e:
        logger.warning(f"Failed to load .codexrules: {e}")
        return ""
```

### 5.2 Modified Function: `_resolve_system_prompt()`

```python
def _resolve_system_prompt(
    profile: Dict[str, Any],
    *,
    allow_apply: bool,
    repo_root: Optional[pathlib.Path] = None
) -> str:
    # 1. Load project-level rules
    codexrules = ""
    if repo_root:
        codexrules = _load_codexrules(repo_root)
    
    # 2. Fallback if no rules file
    if not codexrules:
        codexrules = HARDCODED_DEFAULT_PROMPT
    
    # 3. Per-robot instructions
    custom = str(profile.get("instructions", "") or "").strip()
    
    # 4. Action policy
    action_block = build_action_block(allow_apply, profile)
    
    # 5. Combine with clear separation
    return "\n\n".join(x for x in [codexrules, custom, action_block] if x).strip()
```

### 5.3 Call Sites Updated

All 3 invocations of `_resolve_system_prompt()` now pass `repo_root=firmware.repo_root`.

---

## 6. File Format Specification

### 6.1 Recommended Structure

```markdown
# CODEX AGENT RULES & BEHAVIORS (v1)
# ROLE: [Agent role description]

## 1. CORE IDENTITY
[Who the agent is, what it does]

## 2. BEHAVIOR & PROCESS
[How the agent should act]

## 3. DOMAIN KNOWLEDGE
[Technical concepts the agent should know]

## 4. WORKFLOW GUIDANCE
[Standard procedures]

## 5. ERROR HANDLING
[How to handle common failures]

## 6. DOCUMENTATION AWARENESS
[What docs the agent can reference]

## 7. INTERACTION STYLE
[Tone, voice, communication patterns]
```

### 6.2 Guidelines

- Use Markdown for human readability (agent ignores formatting)
- Keep total length under 4000 tokens for optimal LLM performance
- Use concrete examples where helpful
- Avoid ambiguous language

---

## 7. Implementation Status

| Component | Status | Location |
|-----------|--------|----------|
| `.codexrules` file | ✅ Created | `/Users/jvke/Documents/UpRight.os/.codexrules` |
| `_load_codexrules()` function | ✅ Implemented | `server.py:2010-2029` |
| `_resolve_system_prompt()` update | ✅ Implemented | `server.py:2032-2078` |
| Call site updates (3 locations) | ✅ Completed | `server.py:3392, 3466, 3651` |
| Syntax validation | ✅ Passed | `py_compile` |

---

## 8. Future Enhancements

### 8.1 Phase 2 Candidates

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| Per-robot rules | Support `{robot_id}.codexrules` overrides | Medium |
| Include directive | `#include common_rules.md` for shared sections | Low |
| UI editor | Edit `.codexrules` from ops-console | Medium |
| Validation endpoint | `/api/codexrules/validate` to lint rules | Low |
| Metrics | Track which rules are frequently relevant | Low |

### 8.2 Schema Validation

Consider adding optional YAML frontmatter for structured metadata:

```yaml
---
version: 1
min_model: gpt-4
max_tokens: 3500
---
# CODEX AGENT RULES...
```

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Overly long rules file | Prompt truncation, slower responses | Document 4000 token guideline |
| Conflicting rules | Unpredictable agent behavior | Establish clear priority order |
| File permissions issues | Agent can't load rules | Graceful fallback to default |
| Hot-reload race condition | Stale rules served | mtime-based cache invalidation |

---

## 10. Testing Checklist

- [ ] Agent uses `.codexrules` content when file exists
- [ ] Agent falls back to default when file missing
- [ ] Agent reloads after file edit (no restart)
- [ ] Profile instructions layer correctly on top
- [ ] File read errors logged, don't crash server
- [ ] Cache works (no repeated reads for unchanged file)

---

## 11. Domain Expertise Requirements

The Codex agent must be an expert in the following engineering disciplines:

### 11.1 PID Control Systems

| Topic | Knowledge Required |
|-------|-------------------|
| **Fundamentals** | P, I, D terms; transfer functions; error signal processing |
| **Tuning Methods** | Ziegler-Nichols (ultimate gain & step response), Cohen-Coon, manual tuning, relay auto-tune |
| **Balancing Specifics** | Cascade control, complementary filters, sample rates, anti-windup |
| **Mathematical Notation** | `u = Kp*e + Ki*∫e*dt + Kd*de/dt` |

### 11.2 Robotics & Dynamics

| Topic | Knowledge Required |
|-------|-------------------|
| **Inverted Pendulum** | Equations of motion, linearization, natural frequency, stability analysis |
| **Moment of Inertia** | Point mass, rod formulas, parallel axis theorem |
| **Torque & Force** | Motor torque constants, wheel dynamics, reaction torque |

### 11.3 Calculus & Signal Processing

| Topic | Knowledge Required |
|-------|-------------------|
| **Differentiation** | Numerical methods, filtering, derivative kick mitigation |
| **Integration** | Euler, trapezoidal, windup prevention |
| **Filtering** | Low-pass IIR, moving average, complementary filters |

### 11.4 Sensors & Measurement

| Topic | Knowledge Required |
|-------|-------------------|
| **IMU** | Accelerometer vs gyroscope, sensor fusion, calibration |
| **Encoders** | Quadrature encoding, CPR, velocity estimation |
| **Voltage Sensing** | Dividers, ADC, battery protection |

### 11.5 Trigonometry & Geometry

| Topic | Knowledge Required |
|-------|-------------------|
| **Angle Math** | Degrees/radians, atan2, small angle approximation |
| **Identities** | Pythagorean, angular velocity |
| **Transforms** | Body-to-world, Euler angles |

### 11.6 Electrical Engineering

| Topic | Knowledge Required |
|-------|-------------------|
| **Motor Drivers** | H-bridge, PWM, braking modes, dead time |
| **Power** | Ohm's law, motor power, stall current, back-EMF |
| **Microcontrollers** | ADC resolution, PWM frequency, interrupt latency |

---

## 12. Expected Benefits

### 12.1 Consistency Across Sessions
- Agent behaves identically every time, regardless of conversation history
- No "drift" where agent forgets constraints or role
- Same tuning philosophy applied uniformly

### 12.2 Reduced Prompt Engineering
- Operators focus on requests, not coaching the AI
- No need to repeat domain concepts each session
- Expert behavior out of the box

### 12.3 Version-Controlled Behavior
- `.codexrules` tracked in git
- Changes reviewable via PR
- Audit trail for agent behavior changes

### 12.4 Domain Knowledge Persistence
- Formulas and tuning heuristics always available
- Safety rules enforced consistently
- No re-explaining protocols or modes

### 12.5 Hot-Reload Without Restart
- Edit file, save, next chat uses new rules
- Rapid iteration on agent behavior
- No downtime for updates

### 12.6 Layered Customization
```
.codexrules           → Project-wide defaults + domain expertise
profile.instructions  → Per-robot overrides (e.g., specific gains, limits)
```

### 12.7 Onboarding & Documentation
- New team members read `.codexrules` to understand agent capabilities
- Self-documenting—the rules file IS the spec
- Reduces tribal knowledge

---

## 13. Appendix: `.codexrules` Structure (v2)

See `/Users/jvke/Documents/UpRight.os/.codexrules` for the full implementation.

### Section Overview

| Section | Purpose |
|---------|---------|
| **1. Core Identity** | Who the agent is, what disciplines it masters |
| **2. Behavior & Process** | Decision-making style, safety rules, output format |
| **3. PID Control Systems Expertise** | Fundamentals, tuning methods, balancing specifics |
| **4. Robotics & Dynamics** | Inverted pendulum model, inertia, torque |
| **5. Calculus & Signal Processing** | Differentiation, integration, filtering |
| **6. Sensors & Measurement** | IMU, encoders, voltage sensing |
| **7. Trigonometry & Geometry** | Angle math, identities, transforms |
| **8. Electrical Engineering** | Motor drivers, power, microcontrollers |
| **9. Tuning Guidance (Practical)** | Step-by-step process, troubleshooting |
| **10. Commissioning Workflow** | 5-step onboarding process |
| **11. Error Handling** | Common failures and remediation |
| **12. Documentation Awareness** | References to docs/oracle/ |
| **13. Interaction Style** | Tone, teaching approach, honesty |

### Token Budget

- Current `.codexrules` size: ~5500 tokens
- Recommended max: 6000 tokens (leaves room for context + profile instructions)
- If exceeding budget, extract rarely-used reference material to RAG docs

---

## 14. Conversation Context

This PRD was developed through a conversation covering:

1. **Initial Question:** How does Windsurf know what to do when launched?
2. **Pattern Recognition:** User identified `.windsurfrules` as the mechanism
3. **Alignment Request:** User wanted their UpRight IDE to work the same way
4. **Implementation:** Created `.codexrules` and modified `_resolve_system_prompt()`
5. **Domain Expansion:** User requested comprehensive engineering expertise
6. **PRD Creation:** Documented the full implementation for Codex review

The implementation mirrors Windsurf's pattern while adding domain-specific engineering knowledge appropriate for a robotics tuning platform.
