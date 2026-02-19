import { useEffect, useMemo, useState } from 'react';
import type {
  CompatReport,
  ConnectProbeReport,
  FirmwareDocsPack,
  OverwatchReport,
  ReadinessCheck,
  RobotValidationReport,
} from '../../api';
import { strings } from '../../strings';

type RobotProfile = {
  profile_id: string;
  label: string;
  chassis: string;
  updated_at: number;
  probe: ConnectProbeReport;
};

type Props = {
  healthPort?: string;
  mode: string;
  angle?: string;
  estopLatched: boolean;
  compatKnown: boolean;
  compatOk: boolean;
  compat: CompatReport | null;
  connectProbe: ConnectProbeReport | null;
  validation: RobotValidationReport | null;
  overwatch: OverwatchReport | null;
  activeProfileId: string | null;
  profileLabel: string;
  setProfileLabel: (value: string) => void;
  chassisClass: string;
  setChassisClass: (value: string) => void;
  profiles: RobotProfile[];
  robotProfile: RobotProfile | null;
  runCompatProbe: () => Promise<CompatReport | null>;
  runConnectWizard: () => Promise<ConnectProbeReport | null>;
  runProfileValidation: () => Promise<void>;
  runOverwatchCheck: () => Promise<OverwatchReport | null>;
  activateProfileIfValid: () => Promise<void>;
  activateProfileByIdIfValid: (profileId: string) => Promise<void>;
  loadProfileById: (profileId: string) => void;
  generateFirmwareDocsPack: () => Promise<FirmwareDocsPack | null>;
  runGenerateUnified: () => Promise<void>;
  onPasteSketch: (text: string) => void;
  sketchPrepared: boolean;
  sketchRevision: string;
  loadAssistantPrompt: (prompt: string) => void;
  goToIde: () => void;
  goToTune: () => void;
  saveRobotProfile: () => void;
  loadSavedRobotProfile: () => void;
  exportRobotProfile: () => Promise<void>;
  exportProfileById: (profileId: string) => Promise<void>;
  importRobotProfile: () => void;
  deleteSavedRobotProfile: () => void;
  deleteProfileById: (profileId: string) => void;
  refreshBridge: () => Promise<void>;
};

export function ConnectPreflightPage(props: Props) {
  const {
    healthPort,
    mode,
    angle,
    estopLatched,
    compatKnown,
    compatOk,
    compat,
    connectProbe,
    validation,
    overwatch,
    activeProfileId,
    profileLabel,
    setProfileLabel,
    chassisClass,
    setChassisClass,
    profiles,
    robotProfile,
    runCompatProbe,
    runConnectWizard,
    runProfileValidation,
    runOverwatchCheck,
    activateProfileIfValid,
    activateProfileByIdIfValid,
    loadProfileById,
    generateFirmwareDocsPack,
    runGenerateUnified,
    onPasteSketch,
    sketchPrepared,
    sketchRevision,
    loadAssistantPrompt,
    goToIde,
    goToTune,
    saveRobotProfile,
    loadSavedRobotProfile,
    exportRobotProfile,
    exportProfileById,
    importRobotProfile,
    deleteSavedRobotProfile,
    deleteProfileById,
    refreshBridge,
  } = props;

  const kalmanMissing = compat?.missing_fields?.filter((f) => f === 'ang' || f === 'raw' || f.includes('gyro')) ?? [];
  const kalmanStandardOk = compatKnown && kalmanMissing.length === 0;
  const connectTone = !compatKnown ? 'unknown' : compatOk ? 'good' : 'bad';
  const kalmanTone = !compatKnown ? 'unknown' : kalmanStandardOk ? 'good' : 'bad';
  const readinessTone = !connectProbe ? 'unknown' : connectProbe.v2_ready ? 'good' : connectProbe.v1_ok ? 'warn' : 'bad';
  const requiredStatusFields = compat?.required_fields?.length ? compat.required_fields.join(', ') : 'n/a';
  const kalmanEvidence = kalmanMissing.length ? `missing ${kalmanMissing.join(', ')}` : 'ang/raw/gyro present';
  const readinessEvidence = connectProbe?.readiness_checks?.length
    ? connectProbe.readiness_checks.map((c) => `${c.check}:${c.status}`).join(' | ')
    : 'no readiness checks yet';

  const [docsPack, setDocsPack] = useState<FirmwareDocsPack | null>(null);
  const [docsSketchRevision, setDocsSketchRevision] = useState('');
  const [docsOpen, setDocsOpen] = useState(false);
  const [activeDoc, setActiveDoc] = useState('');
  const [docsViewMode, setDocsViewMode] = useState<'code' | 'image'>('code');
  const [mermaidSvg, setMermaidSvg] = useState('');
  const [mermaidError, setMermaidError] = useState('');
  const [connectTestNote, setConnectTestNote] = useState('');
  const [kalmanTestNote, setKalmanTestNote] = useState('');
  const [readinessTestNote, setReadinessTestNote] = useState('');
  const [overwatchTestNote, setOverwatchTestNote] = useState('');
  const [pastedSketch, setPastedSketch] = useState('');
  const [selectedProfileId, setSelectedProfileId] = useState(activeProfileId ?? '');
  const overwatchTone = !overwatch ? 'unknown' : overwatch.overall === 'pass' ? 'good' : overwatch.overall === 'warn' ? 'warn' : 'bad';

  const artifactEntries = useMemo(() => Object.entries(docsPack?.artifacts ?? {}), [docsPack?.artifacts]);
  const docsStale = Boolean(docsPack && docsSketchRevision && docsSketchRevision !== sketchRevision);

  useEffect(() => {
    setSelectedProfileId(activeProfileId ?? '');
  }, [activeProfileId]);

  useEffect(() => {
    if (!artifactEntries.length) {
      setActiveDoc('');
      return;
    }
    if (!activeDoc || !artifactEntries.some(([name]) => name === activeDoc)) {
      setActiveDoc(artifactEntries[0][0]);
    }
  }, [activeDoc, artifactEntries]);

  useEffect(() => {
    if (!docsPack || !docsSketchRevision) return;
    if (docsSketchRevision !== sketchRevision) {
      setDocsOpen(false);
      setMermaidSvg('');
      setMermaidError('');
    }
  }, [docsPack, docsSketchRevision, sketchRevision]);

  const activeDocText = artifactEntries.find(([name]) => name === activeDoc)?.[1] ?? '';
  const activeDocIsMermaid = activeDoc.endsWith('.mmd');

  const normalizeMermaid = (src: string): string => {
    let s = src.replace(/\r\n/g, '\n').trim();
    if (!s) return s;
    // Recover one-line dumps by forcing line breaks after diagram directives.
    s = s.replace(/^(flowchart\s+[A-Z]{1,2})\s+/i, '$1\n');
    s = s.replace(/^(graph\s+[A-Z]{1,2})\s+/i, '$1\n');
    s = s.replace(/^(stateDiagram-v2)\s+/i, '$1\n');
    s = s.replace(/^(classDiagram)\s+/i, '$1\n');
    // Older generated docs used unquoted node labels like A[setup()] which can fail parsing.
    // Quote bracket labels unless already quoted.
    if (/^\s*flowchart\b/i.test(s)) {
      s = s.replace(
        /([A-Za-z0-9_]+)\[([^\]\n"]+)\]/g,
        (_m, id: string, label: string) => `${id}["${label.replace(/"/g, '\\"')}"]`,
      );
    }
    return s;
  };

  useEffect(() => {
    let cancelled = false;
    if (!docsOpen || docsViewMode !== 'image' || !activeDocIsMermaid || !activeDocText.trim()) {
      setMermaidSvg('');
      setMermaidError('');
      return () => {
        cancelled = true;
      };
    }

    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'loose',
          theme: 'base',
          themeVariables: {
            background: '#0a1730',
            primaryColor: '#14375f',
            primaryTextColor: '#d3e4f7',
            primaryBorderColor: '#4c88c5',
            lineColor: '#5ea0e3',
            secondaryColor: '#0f2748',
            secondaryTextColor: '#c9def4',
            tertiaryColor: '#0c213d',
            tertiaryTextColor: '#c9def4',
            edgeLabelBackground: '#102847',
            clusterBkg: '#0f2748',
            clusterBorder: '#4c88c5',
            fontFamily: 'IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, monospace',
          },
        });
        const id = `docs_mermaid_${Date.now()}`;
        const out = await mermaid.render(id, normalizeMermaid(activeDocText));
        if (!cancelled) {
          setMermaidSvg(out.svg);
          setMermaidError('');
        }
      } catch (err) {
        if (!cancelled) {
          setMermaidSvg('');
          setMermaidError((err as Error).message || 'Mermaid render failed');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeDocIsMermaid, activeDocText, docsOpen, docsViewMode]);

  const onGenerateDocs = async () => {
    // Force fresh generation path: clear any prior in-memory pack before requesting new artifacts.
    setDocsOpen(false);
    setDocsPack(null);
    setDocsSketchRevision('');
    setActiveDoc('');
    setMermaidSvg('');
    setMermaidError('');
    const out = await generateFirmwareDocsPack();
    if (out) {
      setDocsPack(out);
      setDocsSketchRevision(sketchRevision);
      setDocsOpen(true);
    }
  };

  const onTestConnect = async () => {
    if (compatKnown) {
      setConnectTestNote(`Already tested: ${compatOk ? 'PASS' : 'FAIL'}`);
      return;
    }
    const out = await runCompatProbe();
    setConnectTestNote(`Manual test result: ${out?.ok ? 'PASS' : 'FAIL'}`);
  };

  const onTestKalman = async () => {
    if (compatKnown) {
      setKalmanTestNote(`Already tested: ${kalmanStandardOk ? 'PASS' : 'FAIL'}`);
      return;
    }
    const out = await runCompatProbe();
    const missing = out?.missing_fields?.filter((f) => f === 'ang' || f === 'raw' || f.includes('gyro')) ?? [];
    setKalmanTestNote(`Manual test result: ${out && missing.length === 0 ? 'PASS' : 'FAIL'}`);
  };

  const onTestReadiness = async () => {
    if (connectProbe) {
      setReadinessTestNote(`Already tested: ${connectProbe.v2_ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}`);
      return;
    }
    const out = await runConnectWizard();
    setReadinessTestNote(`Manual test result: ${out?.v2_ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}`);
  };

  const onTestOverwatch = async () => {
    const out = await runOverwatchCheck();
    if (!out) {
      setOverwatchTestNote('Manual test result: FAIL');
      return;
    }
    setOverwatchTestNote(`Manual test result: ${String(out.overall).toUpperCase()} (${out.score_pct}%)`);
  };

  return (
    <section>
      <h2>Setup Workflow</h2>
      <div className="setup-phase-grid">
        <div className="wizard-box setup-phase-col">
          <div className="setup-phase-head">
            <h3>1_CONNECT</h3>
            <span className="workflow-label">detect, validate, save, activate</span>
          </div>

          <div className="row">
            <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void runConnectWizard()}>Run Auto-Detect</button>
            <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void runProfileValidation()}>Run Validation</button>
            <button className="btn-primary btn-sm btn-intent-build" disabled={!validation?.ok} onClick={() => void activateProfileIfValid()}>Activate Profile</button>
          </div>

          {validation && (
            <div className="compat-box">
              <p><strong>Validation:</strong> {validation.ok ? 'PASS' : 'FAIL'} ({validation.score_pct}%)</p>
              <p><strong>Duration:</strong> {validation.duration_s}s</p>
              <p><strong>Active Profile:</strong> {activeProfileId ?? 'none'}</p>
            </div>
          )}

          <div className="wizard-box">
            <h3>Connect Wizard</h3>
            <p className="wizard-subtitle">
              Profiles define this robot's identity and hardware baseline for scaffold generation + deployment checks.
            </p>
            <p className="wizard-profile-summary">
              Active Profile: <strong>{robotProfile?.label ?? 'none selected'}</strong>
            </p>

            <h4 className="setup-subhead">1) Detect + Fingerprint</h4>
            <p className="setup-subnote">Probe the connected device and gather board/firmware/component evidence.</p>
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void runConnectWizard()}>
                Run Auto-Detect
              </button>
            </div>

            <h4 className="setup-subhead">2) Define Profile</h4>
            <p className="setup-subnote">Set robot label/chassis and save as local profile.</p>
            <div className="wizard-profile-inputs">
              <label>
                Robot Label
                <input type="text" value={profileLabel} onChange={(e) => setProfileLabel(e.target.value)} />
              </label>
              <label>
                Chassis Class
                <select value={chassisClass} onChange={(e) => setChassisClass(e.target.value)}>
                  <option value="2wd_inverted_pendulum">2WD Inverted Pendulum</option>
                  <option value="2wd_diff_drive">2WD Differential Drive</option>
                  <option value="custom">Custom</option>
                </select>
              </label>
              <button onClick={saveRobotProfile}>Save Local Profile</button>
            </div>

            <h4 className="setup-subhead">3) Manage Profile Files</h4>
            <p className="setup-subnote">Load active saved profile, export/share JSON, import JSON, or delete active profile.</p>
            <div className="wizard-profile-picker">
              <label>
                Saved Profiles
                <select value={selectedProfileId} onChange={(e) => setSelectedProfileId(e.target.value)}>
                  <option value="">Select profile...</option>
                  {profiles.map((p) => (
                    <option key={p.profile_id} value={p.profile_id}>
                      {p.label} ({p.chassis})
                    </option>
                  ))}
                </select>
              </label>
              <div className="row">
                <button className="btn-secondary btn-sm" disabled={!selectedProfileId} onClick={() => loadProfileById(selectedProfileId)}>
                  Load Selected
                </button>
                <button className="btn-secondary btn-sm" disabled={!selectedProfileId || !validation?.ok} onClick={() => void activateProfileByIdIfValid(selectedProfileId)}>
                  Set Active
                </button>
              </div>
            </div>
            <div className="wizard-actions">
              <button onClick={loadSavedRobotProfile}>Load Active Saved Profile</button>
              <button disabled={!selectedProfileId} onClick={() => void exportProfileById(selectedProfileId)}>Export Selected Profile JSON</button>
              <button onClick={importRobotProfile}>Import Profile JSON</button>
              <button disabled={!selectedProfileId} onClick={() => deleteProfileById(selectedProfileId)}>Delete Selected Profile</button>
            </div>

            {robotProfile && (
              <p className="wizard-profile-summary">
                Saved Profile: <strong>{robotProfile.label}</strong> · {robotProfile.chassis} · confidence {robotProfile.probe.confidence_pct}%
              </p>
            )}

            {connectProbe && (
              <div className="wizard-results">
                <p><strong>Confidence:</strong> {connectProbe.confidence_pct}%</p>
                <p><strong>MCU Guess:</strong> {connectProbe.mcu_guess}</p>
                <p><strong>Firmware Profile:</strong> {connectProbe.firmware_profile}</p>
                <p><strong>USB Device:</strong> {connectProbe.port_meta.description ?? connectProbe.port}</p>
                <p>
                  <strong>Components:</strong>{' '}
                  IMU={connectProbe.components.imu ? 'Y' : 'N'} ·
                  Motor={connectProbe.components.motor_driver ? 'Y' : 'N'} ·
                  Enc={connectProbe.components.encoder_feedback ? 'Y' : 'N'} ·
                  Volt={connectProbe.components.voltage_telemetry ? 'Y' : 'N'}
                </p>
                <p><strong>Missing Commands:</strong> {connectProbe.missing_commands.length ? connectProbe.missing_commands.join(', ') : 'none'}</p>
              </div>
            )}
          </div>
        </div>

        <div className="wizard-box setup-phase-col">
          <div className="setup-phase-head">
            <h3>2_NEW ROBOT SETUP</h3>
            <span className="workflow-label">generate sketch, coach prompts, view docs</span>
          </div>

          <div className="wizard-box">
            <h3>Sketch Generator</h3>
            <p className="wizard-subtitle">Generate scaffold from current unified profile without leaving Setup, or paste your own sketch.</p>
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-build" onClick={() => void runGenerateUnified()}>Generate Sketch Here</button>
              <button className="btn-secondary btn-sm btn-intent-prompt" onClick={() => loadAssistantPrompt('Generate a unified scaffold now using the confirmed profile, then load the generated main .ino into the editor and tell me the sketch folder path.')}>Generate Via Agent</button>
              <button className="btn-secondary btn-sm btn-intent-nav" onClick={goToIde}>Open IDE Tab</button>
            </div>
            <textarea
              className="setup-sketch-paste"
              value={pastedSketch}
              onChange={(e) => setPastedSketch(e.target.value)}
              placeholder="Paste your sketch here..."
            />
            <div className="row">
              <button className="btn-secondary btn-sm" onClick={() => onPasteSketch(pastedSketch)}>Use Pasted Sketch</button>
            </div>
          </div>

          <div className="wizard-box">
            <h3>Prompt Coach</h3>
            <p className="wizard-subtitle">Use guided prompts in Codex, then continue to IDE and Tuning.</p>
            <div className="wizard-results">
              <p><strong>1. Detect + summarize:</strong> Ask Codex to summarize board/fqbn/port and missing commands.</p>
              <div className="row">
                <button className="btn-secondary btn-sm btn-intent-prompt" onClick={() => loadAssistantPrompt('Summarize the latest connect and compat probe results as board/fqbn/port, missing fields, and missing commands. Then give me the next action in one line.')}>Load Step 1 Prompt</button>
              </div>

              <p><strong>2. Prepare scaffold profile:</strong> Ask Codex to draft unified profile JSON using detected hardware.</p>
              <div className="row">
                <button className="btn-secondary btn-sm btn-intent-prompt" onClick={() => loadAssistantPrompt('Draft a unified scaffold profile JSON for this robot using detected board/fqbn/port. Include conservative placeholder pin mapping and list assumptions I must confirm.')}>Load Step 2 Prompt</button>
              </div>

              <p><strong>3. Tuning handoff:</strong> Ask for first-safe-test recommendations once flashed.</p>
              <div className="row">
                <button className="btn-secondary btn-sm btn-intent-nav" onClick={goToTune}>Go To Tuning Tab</button>
                <button className="btn-secondary btn-sm btn-intent-prompt" onClick={() => loadAssistantPrompt('I am ready for first balance test. Give me a safe 3-step sequence for CAL ZERO, arm/disarm verification, and first PID baseline check.')}>Load Tuning Prompt</button>
              </div>
            </div>
          </div>

          <div className={`wizard-box ${sketchPrepared ? '' : 'is-disabled'}`}>
            <h3>{strings.firmwareDocs.title}</h3>
            <p className="wizard-subtitle">{strings.firmwareDocs.subtitle}</p>
            <p className="wizard-profile-summary">{strings.firmwareDocs.contractNote}</p>
            {!sketchPrepared && (
              <p className="setup-rig-test-note">Generate or paste a sketch first. Docs are locked until sketch is prepped for IDE.</p>
            )}
            {sketchPrepared && docsPack && docsSketchRevision && docsSketchRevision !== sketchRevision && (
              <p className="setup-rig-test-note">Sketch changed. Regenerate docs pack to view updated architecture docs.</p>
            )}
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-discover" disabled={!sketchPrepared} onClick={() => void onGenerateDocs()}>
                {strings.firmwareDocs.generate}
              </button>
              <button className="btn-secondary btn-sm" disabled={!sketchPrepared || !docsPack || docsStale} onClick={() => setDocsOpen(true)}>
                {strings.firmwareDocs.view}
              </button>
            </div>
          </div>
        </div>

        <div className="wizard-box setup-phase-col">
          <div className="setup-phase-head">
            <h3>3_DEPLOYMENT TEST</h3>
            <span className="workflow-label">connect + kalman + anti-drift readiness</span>
          </div>

          <div className={`wizard-box setup-rig tone-${connectTone}`}>
            <div className="setup-rig-head">
              <h3>Connect</h3>
              <span className={`hud-pill ${connectTone}`}>{compatKnown ? (compatOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</span>
            </div>
            <div className="setup-rig-layout">
              <div className="setup-rig-main">
                <p className="indicator-line"><span className="indicator-label">Bridge Port:</span> <span className="indicator-value">{healthPort ?? 'n/a'}</span></p>
                <p className="indicator-line"><span className="indicator-label">Mode:</span> <span className="indicator-value">{mode}</span></p>
                <p className="indicator-line"><span className="indicator-label">Angle:</span> <span className="indicator-value">{angle ?? 'n/a'}</span></p>
                <p className="indicator-line"><span className="indicator-label">E-Stop Latched:</span> <span className="indicator-value">{estopLatched ? 'YES' : 'NO'}</span></p>
                <p className="indicator-line"><span className="indicator-label">Compatibility:</span> <span className="indicator-value">{compatKnown ? (compatOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</span></p>
                <div className="row"><button className="btn-secondary btn-sm btn-intent-discover btn-cal-zero" onClick={() => void onTestConnect()}>Test Connect</button></div>
                {connectTestNote && <p className="setup-rig-test-note">{connectTestNote}</p>}
              </div>
              <div className="setup-rig-side">
                <p><strong>Profile:</strong> {compat?.profile ?? 'unknown'}</p>
                <p><strong>Firmware ID:</strong> {compat?.firmware_id ?? 'n/a'}</p>
                <p><strong>Missing fields:</strong> {compat?.missing_fields?.length ? compat.missing_fields.join(', ') : 'none'}</p>
                <p><strong>Missing commands:</strong> {compat?.missing_commands?.length ? compat.missing_commands.join(', ') : 'none'}</p>
                <p><strong>Warnings:</strong> {compat?.warnings?.length ? compat.warnings.join(' | ') : 'none'}</p>
              </div>
              <div className="setup-rig-ref">
                <p><strong>Evidence / References</strong></p>
                <p><code>contract.status.required</code>: {requiredStatusFields}</p>
                <p><code>contract.commands.missing</code>: {compat?.missing_commands?.length ? compat.missing_commands.join(', ') : 'none'}</p>
                <p><code>concept</code>: bridge probe/compat + probe/connect</p>
              </div>
            </div>
          </div>

          <div className={`wizard-box setup-rig tone-${kalmanTone}`}>
            <div className="setup-rig-head">
              <h3>Kalman Telemetry Standard</h3>
              <span className={`hud-pill ${kalmanTone}`}>{compatKnown ? (kalmanStandardOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</span>
            </div>
            <div className="setup-rig-layout">
              <div className="setup-rig-main">
                <p className="wizard-subtitle">Required IMU fusion contract: accel-angle + gyro-rate to filtered angle telemetry.</p>
                <p className="wizard-profile-summary">Required fields: <strong>ang</strong>, <strong>raw</strong>, <strong>gyro|gyr|gx</strong>.</p>
                <p className="wizard-profile-summary">Current check: <strong>{compatKnown ? (kalmanStandardOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</strong></p>
                <div className="row"><button className="btn-secondary btn-sm btn-intent-discover btn-cal-zero" onClick={() => void onTestKalman()}>Test Kalman</button></div>
                {kalmanTestNote && <p className="setup-rig-test-note">{kalmanTestNote}</p>}
              </div>
              <div className="setup-rig-side">
                <p><strong>Filtered angle:</strong> ang</p>
                <p><strong>Raw accel angle:</strong> raw</p>
                <p><strong>Gyro rate:</strong> gyro|gyr|gx</p>
                <p><strong>Missing:</strong> {kalmanMissing.length > 0 ? kalmanMissing.join(', ') : 'none'}</p>
              </div>
              <div className="setup-rig-ref">
                <p><strong>Evidence / References</strong></p>
                <p><code>contract.telemetry.required</code>: ang, raw, gyro|gyr|gx</p>
                <p><code>detected</code>: {kalmanEvidence}</p>
                <p><code>concept</code>: accel-angle + gyro-rate fusion</p>
              </div>
            </div>
          </div>

          <div className={`wizard-box setup-rig v2-readiness-panel tone-${readinessTone}`}>
            <div className="setup-rig-head">
              <h3>{strings.v2Readiness.title}</h3>
              <span className={`hud-pill ${readinessTone}`}>{!connectProbe ? 'UNTESTED' : connectProbe.v2_ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}</span>
            </div>
            <div className="setup-rig-layout">
              <div className="setup-rig-main">
                <p className="wizard-subtitle">{strings.v2Readiness.subtitle}</p>
                <div className="row"><button className="btn-secondary btn-sm btn-intent-discover btn-cal-zero" onClick={() => void onTestReadiness()}>Test Readiness</button></div>
                {readinessTestNote && <p className="setup-rig-test-note">{readinessTestNote}</p>}
                {connectProbe?.readiness_checks && connectProbe.readiness_checks.length > 0 && (
                  <details className="readiness-checks-details">
                    <summary>{strings.v2Readiness.checksTitle}</summary>
                    <ul className="readiness-checks-list">
                      {connectProbe.readiness_checks.map((check: ReadinessCheck, idx: number) => (
                        <li key={idx} className={`readiness-check-item check-${check.status}`}>
                          <span className="check-name">{(strings.v2Readiness.checkLabels as Record<string, string>)[check.check] ?? check.check}</span>
                          <span className={`check-status status-${check.status}`}>{check.status.toUpperCase()}</span>
                          <span className="check-detail">{check.detail}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
              <div className="setup-rig-side">
                <p><strong>{strings.v2Readiness.v1Status}:</strong> {connectProbe?.v1_ok ? strings.v2Readiness.pass : strings.v2Readiness.fail}</p>
                <p><strong>{strings.v2Readiness.v2Status}:</strong> {connectProbe?.v2_ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}</p>
                <p><strong>{strings.v2Readiness.missingFields}:</strong> {connectProbe?.v2_missing_fields?.length ? connectProbe.v2_missing_fields.join(', ') : 'none'}</p>
                <p><strong>{strings.v2Readiness.presentFields}:</strong> {connectProbe?.v2_present_fields?.length ? connectProbe.v2_present_fields.join(', ') : 'none'}</p>
              </div>
              <div className="setup-rig-ref">
                <p><strong>Evidence / References</strong></p>
                <p><code>contract.version</code>: {connectProbe?.contract_version_detected ?? 'unknown'}</p>
                <p><code>v2.present</code>: {connectProbe?.v2_present_fields?.length ? connectProbe.v2_present_fields.join(', ') : 'none'}</p>
                <p><code>readiness.checks</code>: {readinessEvidence}</p>
              </div>
            </div>
          </div>

          <div className={`wizard-box setup-rig tone-${overwatchTone}`}>
            <div className="setup-rig-head">
              <h3>Overwatch Integrity</h3>
              <span className={`hud-pill ${overwatchTone}`}>
                {!overwatch ? 'UNTESTED' : String(overwatch.overall).toUpperCase()}
              </span>
            </div>
            <div className="setup-rig-layout">
              <div className="setup-rig-main">
                <p className="wizard-subtitle">Continuous integrity guard for sketch, docs, telemetry contract, and deployment readiness.</p>
                <p className="wizard-profile-summary">
                  Current score: <strong>{overwatch ? `${overwatch.score_pct}%` : 'n/a'}</strong>
                </p>
                <div className="row">
                  <button className="btn-secondary btn-sm btn-intent-discover btn-cal-zero" onClick={() => void onTestOverwatch()}>
                    Run Overwatch
                  </button>
                </div>
                {overwatchTestNote && <p className="setup-rig-test-note">{overwatchTestNote}</p>}
              </div>
              <div className="setup-rig-side">
                <p><strong>Pass/Warn/Fail:</strong> {overwatch ? `${overwatch.counts.pass}/${overwatch.counts.warn}/${overwatch.counts.fail}` : 'n/a'}</p>
                <p><strong>Contract:</strong> {overwatch?.contract_version_detected ?? 'unknown'}</p>
                <p><strong>Docs Fresh:</strong> {overwatch?.docs?.fresh ? 'YES' : overwatch ? 'NO' : 'n/a'}</p>
                <p><strong>Connect Confidence:</strong> {overwatch?.connect_confidence_pct ?? 0}%</p>
              </div>
              <div className="setup-rig-ref">
                <p><strong>Evidence / References</strong></p>
                {overwatch?.checks?.slice(0, 3).map((c) => (
                  <p key={c.id}><code>{c.id}</code>: {c.status} · {c.detail}</p>
                ))}
                {!overwatch && <p><code>status</code>: run overwatch to populate checks</p>}
              </div>
            </div>
          </div>
        </div>
      </div>

      <button onClick={() => void refreshBridge()}>Refresh</button>

      {docsOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={strings.firmwareDocs.viewerTitle} onClick={() => setDocsOpen(false)}>
          <div className="preflight-modal firmware-docs-modal" onClick={(e) => e.stopPropagation()}>
            <div className="firmware-docs-head">
              <h3>{strings.firmwareDocs.viewerTitle}</h3>
              <button className="firmware-docs-close" aria-label={strings.firmwareDocs.closeViewer} onClick={() => setDocsOpen(false)}>
                ×
              </button>
            </div>
            <div className="firmware-docs-toolbar">
              <span className="firmware-docs-toolbar-label">View Mode</span>
              <div className="firmware-docs-view-toggle">
                <button className={`btn-secondary btn-sm ${docsViewMode === 'code' ? 'active' : ''}`} onClick={() => setDocsViewMode('code')}>
                  Code View
                </button>
                <button className={`btn-secondary btn-sm ${docsViewMode === 'image' ? 'active' : ''}`} onClick={() => setDocsViewMode('image')}>
                  Image View
                </button>
              </div>
            </div>
            {!artifactEntries.length ? (
              <p className="wizard-subtitle">{strings.firmwareDocs.noDocs}</p>
            ) : (
              <div className="firmware-docs-shell">
                <nav className="firmware-docs-list" aria-label="Docs artifacts">
                  {artifactEntries.map(([name]) => (
                    <button
                      key={name}
                      className={`btn-secondary btn-sm ${activeDoc === name ? 'active' : ''}`}
                      onClick={() => setActiveDoc(name)}
                    >
                      {name}
                    </button>
                  ))}
                </nav>
                <section className="firmware-docs-viewer" aria-label={activeDoc}>
                  {docsViewMode === 'code' && <pre>{activeDocText}</pre>}
                  {docsViewMode === 'image' && !activeDocIsMermaid && (
                    <p className="wizard-subtitle firmware-docs-empty">Image view is available for Mermaid `.mmd` files only.</p>
                  )}
                  {docsViewMode === 'image' && activeDocIsMermaid && mermaidError && (
                    <p className="wizard-subtitle firmware-docs-empty">Render error: {mermaidError}</p>
                  )}
                  {docsViewMode === 'image' && activeDocIsMermaid && !mermaidError && mermaidSvg && (
                    <div className="firmware-docs-image" dangerouslySetInnerHTML={{ __html: mermaidSvg }} />
                  )}
                </section>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
