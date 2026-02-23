import { useEffect, useMemo, useState } from 'react';
import {
  setupAttemptHistory,
  setupCompatTest,
  setupOverwatchCheck,
  setupSmokeCheck,
} from '../../api';
import type {
  CompatReport,
  ConnectProbeReport,
  FirmwareDocsPack,
  OverwatchReport,
  ReadinessCheck,
  RobotValidationReport,
  SetupCompatTestResult,
  SetupValidationAttempt,
  SetupSmokeCheckResult,
  SetupValidationStatus,
} from '../../api';
import { strings } from '../../strings';
import { BOARD_PROFILES } from '../../hardware/boardRegistry';
import { MIRRORED_BOARD_ASSET_PATHS } from '../../hardware/boardAssets';
import { pinNumberFromLabel, resolveBoardProfile } from '../../hardware/boardResolver';
import { validatePinMap } from '../../hardware/pinValidation';

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
  unifiedProfileJson: string;
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
  onHardwareContextChange: (ctx: Record<string, unknown>) => void;
};

type IntakeDraft = {
  label?: string;
  board?: {
    fqbn?: string;
    port?: string;
  };
  hardware?: {
    imu_type?: string;
    motor_driver?: string;
    encoder_feedback?: boolean;
    battery?: string;
  };
  pins?: Record<string, unknown>;
  notes?: string;
};

function normalizeInt(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return Math.trunc(v);
  if (typeof v === 'string') {
    const n = Number.parseInt(v, 10);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function parseIntakeDraft(jsonText: string): IntakeDraft | null {
  try {
    const parsed = JSON.parse(jsonText) as IntakeDraft;
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed;
  } catch {
    return null;
  }
}

function preferredAssetHref(localPath?: string, remoteUrl?: string): string {
  if (localPath && MIRRORED_BOARD_ASSET_PATHS.has(localPath)) return localPath;
  return remoteUrl || '';
}

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
    unifiedProfileJson,
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
    onHardwareContextChange,
  } = props;

  const kalmanMissing = compat?.missing_fields?.filter((f) => f === 'ang' || f === 'raw' || f.includes('gyro')) ?? [];
  const kalmanStandardOk = compatKnown && kalmanMissing.length === 0;
  const connectTone = !compatKnown ? 'unknown' : compatOk ? 'good' : 'bad';
  const kalmanTone = !compatKnown ? 'unknown' : kalmanStandardOk ? 'good' : 'bad';
  const phase1Ready = connectProbe?.phase1_ready ?? connectProbe?.v1_ok ?? false;
  const phase2Ready = connectProbe?.phase2_ready ?? connectProbe?.v2_ready ?? false;
  const readinessTone = !connectProbe ? 'unknown' : phase2Ready ? 'good' : phase1Ready ? 'warn' : 'bad';
  const requiredStatusFields = compat?.required_fields?.length ? compat.required_fields.join(', ') : 'n/a';
  const kalmanEvidence = kalmanMissing.length ? `missing ${kalmanMissing.join(', ')}` : 'ang/raw/gyro present';
  const readinessEvidence = connectProbe?.readiness_checks?.length
    ? connectProbe.readiness_checks.map((c) => `${c.check}:${c.status}`).join(' | ')
    : 'no readiness checks yet';
  const missingPhase2Text = !connectProbe
    ? 'untested'
    : (connectProbe.phase2_missing_fields?.length
        ? connectProbe.phase2_missing_fields.join(', ')
        : (connectProbe.v2_missing_fields?.length
            ? connectProbe.v2_missing_fields.join(', ')
            : (phase2Ready ? 'none' : 'awaiting telemetry')));
  const presentAdvancedText = !connectProbe
    ? 'untested'
    : (connectProbe.phase2_present_fields?.length
        ? connectProbe.phase2_present_fields.join(', ')
        : (connectProbe.v2_present_fields?.length
            ? connectProbe.v2_present_fields.join(', ')
            : (phase2Ready ? 'none' : 'awaiting telemetry')));
  const phase2PresentEvidence = connectProbe?.phase2_present_fields?.length
    ? connectProbe.phase2_present_fields.join(', ')
    : (connectProbe?.v2_present_fields?.length
        ? connectProbe.v2_present_fields.join(', ')
        : (phase2Ready ? 'none' : 'awaiting telemetry'));

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
  const [smokeTestNote, setSmokeTestNote] = useState('');
  const [setupCompatResult, setSetupCompatResult] = useState<SetupCompatTestResult | null>(null);
  const [setupSmokeResult, setSetupSmokeResult] = useState<SetupSmokeCheckResult | null>(null);
  const [attemptHistory, setAttemptHistory] = useState<SetupValidationAttempt[]>([]);
  const [attemptFilter, setAttemptFilter] = useState<'all' | 'compat' | 'smoke' | 'overwatch'>('all');
  const [selectedAttemptId, setSelectedAttemptId] = useState<string>('');
  const [attemptNextCursor, setAttemptNextCursor] = useState('');
  const [attemptHasMore, setAttemptHasMore] = useState(false);
  const [attemptLoading, setAttemptLoading] = useState(false);
  const [setupStage, setSetupStage] = useState<'connect' | 'build' | 'deploy'>('connect');
  const [connectEntryMode, setConnectEntryMode] = useState<'new' | 'existing' | null>(null);
  const [connectWizardStep, setConnectWizardStep] = useState<'detect' | 'profile' | 'activate'>('detect');
  const [connectWizardAdvanced, setConnectWizardAdvanced] = useState(false);
  const [overwatchTestNote, setOverwatchTestNote] = useState('');
  const [pastedSketch, setPastedSketch] = useState('');
  const [selectedProfileId, setSelectedProfileId] = useState(activeProfileId ?? '');
  const [intakeBoard, setIntakeBoard] = useState('arduino:avr:nano');
  const [intakeImu, setIntakeImu] = useState('mpu6050');
  const [intakeMotorDriver, setIntakeMotorDriver] = useState('tb6612fng');
  const [intakeEncoder, setIntakeEncoder] = useState('none');
  const [intakeBattery, setIntakeBattery] = useState('2s_lipo');
  const [intakeNotes, setIntakeNotes] = useState('');
  const [boardModelOverrideId, setBoardModelOverrideId] = useState('');
  const [boardAmbiguityConfirmed, setBoardAmbiguityConfirmed] = useState(false);
  const [intakeAutoFilled, setIntakeAutoFilled] = useState(false);
  const [boardGuideOpen, setBoardGuideOpen] = useState(false);
  const [boardPreviewMode, setBoardPreviewMode] = useState<'layout' | 'pinout' | 'schematic' | 'docs' | 'cad'>('layout');
  const [boardView3d, setBoardView3d] = useState(false);
  const [pinMap, setPinMap] = useState({
    motor_l_pwm: 5,
    motor_l_dir: 4,
    motor_r_pwm: 6,
    motor_r_dir: 7,
    imu_sda: 18,
    imu_scl: 19,
    gate_enable: 8,
    led: 13,
    enc_l_a: -1,
    enc_l_b: -1,
    enc_r_a: -1,
    enc_r_b: -1,
  });
  const [deploymentPulseIndex, setDeploymentPulseIndex] = useState(0);
  const [missionObjective, setMissionObjective] = useState('');
  const [missionEnvironment, setMissionEnvironment] = useState('indoor_flat');
  const [missionPriority, setMissionPriority] = useState('stability');
  const [missionSuccess, setMissionSuccess] = useState('');
  const [manualSketchOverride, setManualSketchOverride] = useState(false);
  const statusTone = (s: SetupValidationStatus | null | undefined): 'good' | 'warn' | 'bad' | 'unknown' => {
    if (!s) return 'unknown';
    if (s === 'pass') return 'good';
    if (s === 'warn') return 'warn';
    return 'bad';
  };
  const intakeLocked = !sketchPrepared;
  const overwatchTone = !overwatch ? 'unknown' : overwatch.overall === 'pass' ? 'good' : overwatch.overall === 'warn' ? 'warn' : 'bad';
  const rigPulseClass = (rigIndex: number, rigTone: 'good' | 'warn' | 'bad' | 'unknown') =>
    deploymentPulseIndex === rigIndex
      ? `setup-rig-pulse-active deployment-pulse-${rigTone}`
      : '';
  const artifactEntries = useMemo(() => Object.entries(docsPack?.artifacts ?? {}), [docsPack?.artifacts]);
  const docsStale = Boolean(docsPack && docsSketchRevision && docsSketchRevision !== sketchRevision);
  const boardResolutionInput = boardModelOverrideId || intakeBoard;
  const boardResolution = useMemo(() => resolveBoardProfile(boardResolutionInput), [boardResolutionInput]);
  const selectedBoardProfile = boardResolution.profile;
  const boardAssets = selectedBoardProfile.assets;
  const docsHref = preferredAssetHref(boardAssets?.localDocsPath, boardAssets?.docsUrl);
  const pinoutHref = preferredAssetHref(boardAssets?.localPinoutPath, boardAssets?.pinoutUrl);
  const schematicHref = preferredAssetHref(boardAssets?.localSchematicPath, boardAssets?.schematicUrl);
  const cadHref = preferredAssetHref(boardAssets?.localCadPath, boardAssets?.cadStepUrl);
  const missionReady = missionObjective.trim().length > 3 && missionSuccess.trim().length > 3;
  const missionBypassReady = sketchPrepared && Boolean(activeProfileId || robotProfile?.profile_id);
  const missionGateReady = missionReady || missionBypassReady;
  const pinValidation = useMemo(() => validatePinMap(selectedBoardProfile, pinMap), [pinMap, selectedBoardProfile]);
  const boardResolutionTone = boardResolution.ambiguous || boardResolution.confidence < 0.55 ? 'warn' : 'good';
  const pinValidationTone = pinValidation.summary.errors > 0 ? 'bad' : pinValidation.summary.warnings > 0 ? 'warn' : 'good';
  const boardResolutionReady =
    (!boardResolution.ambiguous && boardResolution.confidence >= 0.55) ||
    boardAmbiguityConfirmed;
  const generatePrereqs = useMemo(() => {
    const items = [
      {
        id: 'bridge',
        label: 'Bridge connected',
        ok: Boolean(healthPort),
        hint: 'Open bridge/start services, then Refresh.',
      },
      {
        id: 'compat',
        label: 'Compatibility probe passed',
        ok: Boolean(compatKnown && compatOk),
        hint: 'Run Test Connect and fix missing fields/commands.',
      },
      {
        id: 'profile',
        label: 'Robot profile selected',
        ok: Boolean(activeProfileId || robotProfile?.profile_id),
        hint: 'Run Auto-Detect, then Save/Activate profile.',
      },
      {
        id: 'connect',
        label: 'Connect wizard evidence available',
        ok: Boolean(connectProbe),
        hint: 'Run Auto-Detect to populate board/fqbn/port evidence.',
      },
      {
        id: 'board_resolution',
        label: 'Board model confirmed',
        ok: boardResolutionReady,
        hint: 'Select exact board model/fqbn or explicitly confirm ambiguous match.',
      },
      {
        id: 'pin_validation',
        label: 'Pin map passes validation',
        ok: pinValidation.summary.errors === 0,
        hint: 'Fix duplicate or invalid pins before generation/upload.',
      },
    ];
    const readyCount = items.filter((i) => i.ok).length;
    return {
      items,
      readyCount,
      allReady: readyCount === items.length,
    };
  }, [
    activeProfileId,
    boardAmbiguityConfirmed,
    boardResolution.ambiguous,
    boardResolution.confidence,
    boardResolutionReady,
    compatKnown,
    compatOk,
    connectProbe,
    healthPort,
    pinValidation.summary.errors,
    robotProfile?.profile_id,
  ]);
  const generationBlockedReason = useMemo(() => {
    if (generatePrereqs.allReady) return '';
    const firstMissing = generatePrereqs.items.find((item) => !item.ok);
    return firstMissing?.hint ?? 'Complete setup prerequisites before generation.';
  }, [generatePrereqs.allReady, generatePrereqs.items]);
  const compatGateStatus: SetupValidationStatus | null = setupCompatResult?.status ?? (compatKnown ? (compatOk ? 'pass' : 'fail') : null);
  const smokeGateStatus: SetupValidationStatus | null = setupSmokeResult?.status ?? null;
  const tuneUnlocked = (compatGateStatus === 'pass' || compatGateStatus === 'warn') && smokeGateStatus === 'pass';
  const stageOrder: Array<'connect' | 'build' | 'deploy'> = ['connect', 'build', 'deploy'];
  const stageIndex = stageOrder.indexOf(setupStage);
  const canEnterBuild = Boolean(activeProfileId || robotProfile?.profile_id) && missionGateReady;
  const manualOverrideEligible = sketchPrepared && Boolean(activeProfileId || robotProfile?.profile_id) && Boolean(healthPort);
  const manualOverrideActive = manualSketchOverride && manualOverrideEligible;
  const canEnterDeploy = generatePrereqs.allReady || manualOverrideActive;
  const detectComplete = Boolean(connectProbe);
  const profileComplete = Boolean(robotProfile?.profile_id || selectedProfileId);
  const activateComplete = Boolean(activeProfileId);
  const stageBlockedReason =
    setupStage === 'connect'
      ? ''
      : setupStage === 'build'
        ? (
            canEnterBuild
              ? ''
              : (!Boolean(activeProfileId || robotProfile?.profile_id)
                  ? 'Finish and activate robot profile first.'
                  : 'Capture mission brief before parts selection (or continue with uploaded sketch + active profile).')
          )
        : (
            canEnterDeploy
              ? ''
              : 'Complete setup prerequisites and sketch prep before deployment tests (or enable Manual Sketch Override).'
          );
  const canStepBack = stageIndex > 0;
  const canStepNext =
    stageIndex < stageOrder.length - 1 &&
    !((setupStage === 'connect' && !canEnterBuild) || (setupStage === 'build' && !canEnterDeploy));
  const goStageBack = () => setSetupStage(stageOrder[Math.max(0, stageIndex - 1)]);
  const goStageNext = () => setSetupStage(stageOrder[Math.min(stageOrder.length - 1, stageIndex + 1)]);
  const filteredAttempts = useMemo(() => attemptHistory, [attemptHistory]);
  const selectedAttempt = useMemo(
    () => filteredAttempts.find((item) => item.attempt_id === selectedAttemptId) ?? filteredAttempts[0] ?? null,
    [filteredAttempts, selectedAttemptId],
  );
  const flowSteps = useMemo(
    () => ([
      { id: 'mission', label: 'Mission', status: missionGateReady ? 'pass' : 'warn' },
      { id: 'parts', label: 'Parts', status: generatePrereqs.items.find((x) => x.id === 'pin_validation')?.ok ? 'pass' : 'warn' },
      { id: 'sketch', label: 'Sketch', status: sketchPrepared ? 'pass' : 'warn' },
      { id: 'compat', label: 'Compat', status: compatGateStatus ?? 'unknown' },
      { id: 'smoke', label: 'Smoke', status: smokeGateStatus ?? 'unknown' },
      { id: 'tune', label: 'Tune', status: tuneUnlocked ? 'pass' : 'warn' },
    ]),
    [missionGateReady, generatePrereqs.items, sketchPrepared, compatGateStatus, smokeGateStatus, tuneUnlocked],
  );
  const flowStepTarget = (id: string): 'connect' | 'build' | 'deploy' => {
    if (id === 'mission') return 'connect';
    if (id === 'parts' || id === 'sketch') return 'build';
    return 'deploy';
  };
  const flowStepEnabled = (id: string): boolean => {
    if (id === 'mission') return true;
    if (id === 'parts' || id === 'sketch') return canEnterBuild;
    if (id === 'tune') return tuneUnlocked;
    return canEnterDeploy;
  };
  const intakeProfilePreview = useMemo(() => ({
    label: profileLabel || 'new_robot_profile',
    board: {
      fqbn: intakeBoard,
      port: healthPort ?? '',
    },
    hardware: {
      imu_type: intakeImu,
      motor_driver: intakeMotorDriver,
      encoder_feedback: intakeEncoder !== 'none',
      battery: intakeBattery,
    },
    pins: pinMap,
    notes: intakeNotes.trim() || undefined,
  }), [healthPort, intakeBattery, intakeBoard, intakeEncoder, intakeImu, intakeMotorDriver, intakeNotes, pinMap, profileLabel]);
  const hardwareContextPayload = useMemo(
    () => ({
      source: 'setup.hardware_intake',
      label: profileLabel || 'new_robot_profile',
      mission: {
        objective: missionObjective.trim(),
        environment: missionEnvironment,
        priority: missionPriority,
        success_criteria: missionSuccess.trim(),
        ready: missionReady,
      },
      board: {
        selected_fqbn: intakeBoard,
        resolution: {
          confidence: Number(boardResolution.confidence.toFixed(2)),
          ambiguous: boardResolution.ambiguous,
          confirmed: boardResolutionReady,
          reason: boardResolution.reason,
          candidates: boardResolution.candidates,
        },
        resolved_profile: {
          id: selectedBoardProfile.id,
          family: selectedBoardProfile.family,
          label: selectedBoardProfile.label,
          fqbn: selectedBoardProfile.fqbn,
          aliases: selectedBoardProfile.aliases,
          capabilities: selectedBoardProfile.capabilities,
          pin_layout: {
            left: selectedBoardProfile.leftPins,
            right: selectedBoardProfile.rightPins,
          },
        },
      },
      hardware: {
        imu_type: intakeImu,
        motor_driver: intakeMotorDriver,
        encoder_type: intakeEncoder,
        battery: intakeBattery,
      },
      pins: pinMap,
      pin_validation: {
        ok: pinValidation.ok,
        summary: pinValidation.summary,
        issues: pinValidation.issues.slice(0, 20),
      },
      notes: intakeNotes.trim() || '',
      locked: intakeLocked,
      sketch_prepared: sketchPrepared,
    }),
    [
      intakeBattery,
      intakeBoard,
      missionEnvironment,
      missionObjective,
      missionPriority,
      missionReady,
      missionSuccess,
      boardResolution.ambiguous,
      boardResolution.candidates,
      boardResolution.confidence,
      boardResolution.reason,
      boardResolutionReady,
      intakeEncoder,
      intakeImu,
      intakeLocked,
      intakeMotorDriver,
      intakeNotes,
      pinMap,
      pinValidation.issues,
      pinValidation.ok,
      pinValidation.summary,
      profileLabel,
      selectedBoardProfile.aliases,
      selectedBoardProfile.capabilities,
      selectedBoardProfile.family,
      selectedBoardProfile.fqbn,
      selectedBoardProfile.id,
      selectedBoardProfile.label,
      selectedBoardProfile.leftPins,
      selectedBoardProfile.rightPins,
      sketchPrepared,
    ],
  );
  const intakePrompt = useMemo(() => (
    [
      'Use this hardware intake to draft and validate a unified scaffold profile, then generate sketch.',
      '',
      'Constraints:',
      '- keep safety first',
      '- do quick tool-based research to resolve missing context before asking me',
      '- require missing assumptions explicitly',
      '- execute non-destructive implementation steps directly when possible',
      '- return next action in one line',
      '- align recommendations to mission objective and priority',
      '',
      'Mission Brief:',
      JSON.stringify(
        {
          objective: missionObjective.trim(),
          environment: missionEnvironment,
          priority: missionPriority,
          success_criteria: missionSuccess.trim(),
        },
        null,
        2,
      ),
      '',
      'Hardware Intake JSON:',
      JSON.stringify(intakeProfilePreview, null, 2),
    ].join('\n')
  ), [intakeProfilePreview, missionEnvironment, missionObjective, missionPriority, missionSuccess]);

  const renderBoardAssetPreview = (scope: 'compact' | 'modal') => {
    const frameClass = `board-asset-preview board-asset-preview-${scope}`;
    const isPdfMode = boardPreviewMode === 'pinout' || boardPreviewMode === 'schematic';
    const href = boardPreviewMode === 'docs'
      ? docsHref
      : boardPreviewMode === 'pinout'
        ? pinoutHref
        : boardPreviewMode === 'schematic'
          ? schematicHref
          : boardPreviewMode === 'cad'
            ? cadHref
            : '';
    const cadEmbeddable = Boolean(href) && !href.endsWith('.zip');
    return (
      <div className={frameClass}>
        <div className="board-asset-preview-tabs">
          {([
            ['layout', 'Layout'],
            ['pinout', 'Pinout'],
            ['schematic', 'Schematic'],
            ['docs', 'Docs'],
            ['cad', 'CAD'],
          ] as const).map(([id, label]) => (
            <button
              key={`${scope}-${id}`}
              type="button"
              className={`btn-secondary btn-sm ${boardPreviewMode === id ? 'active' : ''}`}
              onClick={() => setBoardPreviewMode(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="board-asset-preview-frame">
          {boardPreviewMode === 'layout' ? (
            <div className={`board-asset-layout-note ${boardView3d ? 'is-3d' : ''}`}>
              <p><strong>{boardView3d ? 'Perspective Layout' : '2D Layout'}</strong></p>
              <p>Use Large Board View for full rail labeling and mapped pin verification.</p>
            </div>
          ) : boardPreviewMode === 'cad' && href && !cadEmbeddable ? (
            <div className="board-asset-layout-note">
              <p><strong>CAD mirrored as archive</strong></p>
              <p>Open/download CAD package and inspect in external CAD viewer.</p>
              <a className="btn-secondary btn-sm board-asset-link" href={href} target="_blank" rel="noreferrer">
                Open CAD Archive
              </a>
            </div>
          ) : href ? (
            isPdfMode ? (
              <object data={href} type="application/pdf" className="board-asset-preview-object">
                <p>Preview unavailable. <a href={href} target="_blank" rel="noreferrer">Open file</a>.</p>
              </object>
            ) : (
              <iframe title={`board-preview-${scope}-${boardPreviewMode}`} src={href} className="board-asset-preview-iframe" />
            )
          ) : (
            <div className="board-asset-layout-note">
              <p><strong>{boardPreviewMode.toUpperCase()} unavailable</strong></p>
              <p>No mirrored/local file or vendor URL for this board asset yet.</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  const detectedIntake = useMemo(() => {
    const draft = parseIntakeDraft(unifiedProfileJson);
    const mcu = (connectProbe?.mcu_guess ?? '').trim().toLowerCase();
    const boardFromMcu = resolveBoardProfile(mcu).profile.fqbn;

    return {
      label: draft?.label?.trim() || '',
      board: draft?.board?.fqbn?.trim() || boardFromMcu,
      imu: draft?.hardware?.imu_type?.trim() || 'mpu6050',
      motorDriver: draft?.hardware?.motor_driver?.trim() || 'tb6612fng',
      encoder: draft?.hardware?.encoder_feedback ? 'quadrature' : 'none',
      battery: draft?.hardware?.battery?.trim() || '2s_lipo',
      notes: draft?.notes?.trim() || '',
      pins: {
        motor_l_pwm: normalizeInt(draft?.pins?.motor_l_pwm, 5),
        motor_l_dir: normalizeInt(draft?.pins?.motor_l_dir, 4),
        motor_r_pwm: normalizeInt(draft?.pins?.motor_r_pwm, 6),
        motor_r_dir: normalizeInt(draft?.pins?.motor_r_dir, 7),
        imu_sda: normalizeInt(draft?.pins?.imu_sda, 18),
        imu_scl: normalizeInt(draft?.pins?.imu_scl, 19),
        gate_enable: normalizeInt(draft?.pins?.gate_enable, 8),
        led: normalizeInt(draft?.pins?.led, 13),
        enc_l_a: normalizeInt(draft?.pins?.enc_l_a, -1),
        enc_l_b: normalizeInt(draft?.pins?.enc_l_b, -1),
        enc_r_a: normalizeInt(draft?.pins?.enc_r_a, -1),
        enc_r_b: normalizeInt(draft?.pins?.enc_r_b, -1),
      },
    };
  }, [connectProbe?.mcu_guess, unifiedProfileJson]);

  const assumptionBoardSync = useMemo(
    () => detectedIntake.board.trim().toLowerCase() === intakeBoard.trim().toLowerCase(),
    [detectedIntake.board, intakeBoard],
  );
  const assumptionPinMismatches = useMemo(() => {
    const keys = Object.keys(pinMap) as Array<keyof typeof pinMap>;
    return keys.filter((key) => pinMap[key] !== detectedIntake.pins[key]);
  }, [detectedIntake.pins, pinMap]);
  const assumptionPinsSync = assumptionPinMismatches.length === 0;

  const assignmentByPin = useMemo(() => {
    const out = new Map<number, string[]>();
    const source: Array<[string, number]> = [
      ['L_PWM', pinMap.motor_l_pwm],
      ['L_DIR', pinMap.motor_l_dir],
      ['R_PWM', pinMap.motor_r_pwm],
      ['R_DIR', pinMap.motor_r_dir],
      ['SDA', pinMap.imu_sda],
      ['SCL', pinMap.imu_scl],
      ['GATE', pinMap.gate_enable],
      ['LED', pinMap.led],
      ['ENC_L_A', pinMap.enc_l_a],
      ['ENC_L_B', pinMap.enc_l_b],
      ['ENC_R_A', pinMap.enc_r_a],
      ['ENC_R_B', pinMap.enc_r_b],
    ];
    source.forEach(([name, pin]) => {
      if (!Number.isFinite(pin) || pin < 0) return;
      const row = out.get(pin) ?? [];
      row.push(name);
      out.set(pin, row);
    });
    return out;
  }, [pinMap.enc_l_a, pinMap.enc_l_b, pinMap.enc_r_a, pinMap.enc_r_b, pinMap.gate_enable, pinMap.imu_scl, pinMap.imu_sda, pinMap.led, pinMap.motor_l_dir, pinMap.motor_l_pwm, pinMap.motor_r_dir, pinMap.motor_r_pwm]);

  const boardPinSummary = useMemo(
    () => [
      ['L_PWM', pinMap.motor_l_pwm],
      ['R_PWM', pinMap.motor_r_pwm],
      ['SDA', pinMap.imu_sda],
      ['SCL', pinMap.imu_scl],
      ['GATE', pinMap.gate_enable],
      ['LED', pinMap.led],
    ],
    [pinMap.gate_enable, pinMap.imu_scl, pinMap.imu_sda, pinMap.led, pinMap.motor_l_pwm, pinMap.motor_r_pwm],
  );

  useEffect(() => {
    if (!sketchPrepared) {
      setIntakeAutoFilled(false);
    }
  }, [sketchPrepared]);

  useEffect(() => {
    if (intakeLocked || intakeAutoFilled) return;
    setIntakeBoard(detectedIntake.board);
    setBoardModelOverrideId('');
    setBoardAmbiguityConfirmed(false);
    setIntakeImu(detectedIntake.imu);
    setIntakeMotorDriver(detectedIntake.motorDriver);
    setIntakeEncoder(detectedIntake.encoder);
    setIntakeBattery(detectedIntake.battery);
    setIntakeNotes(detectedIntake.notes);
    setPinMap(detectedIntake.pins);
    if (!profileLabel && detectedIntake.label) {
      setProfileLabel(detectedIntake.label);
    }
    setIntakeAutoFilled(true);
  }, [detectedIntake, intakeAutoFilled, intakeLocked, profileLabel, setProfileLabel]);

  useEffect(() => {
    onHardwareContextChange(hardwareContextPayload);
  }, [hardwareContextPayload, onHardwareContextChange]);

  useEffect(() => {
    setBoardAmbiguityConfirmed(false);
  }, [intakeBoard, boardModelOverrideId]);

  useEffect(() => {
    setSelectedProfileId(activeProfileId ?? '');
  }, [activeProfileId]);

  useEffect(() => {
    setDeploymentPulseIndex(0);
  }, [connectTone, kalmanTone, readinessTone, overwatchTone]);

  useEffect(() => {
    const delayMs = 3750;
    const timer = window.setTimeout(() => {
      setDeploymentPulseIndex((idx) => (idx + 1) % 5);
    }, delayMs);
    return () => window.clearTimeout(timer);
  }, [deploymentPulseIndex]);

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

  const mergeAttempt = (incoming: SetupValidationAttempt) => {
    setAttemptHistory((prev) => {
      const next = [incoming, ...prev.filter((item) => item.attempt_id !== incoming.attempt_id)];
      return next.slice(0, 40);
    });
    setSelectedAttemptId(incoming.attempt_id);
  };

  const loadAttemptPage = async (mode: 'reset' | 'append') => {
    setAttemptLoading(true);
    try {
      const cursor = mode === 'append' ? attemptNextCursor : '';
      const page = await setupAttemptHistory(12, cursor, attemptFilter);
      if (mode === 'append') {
        setAttemptHistory((prev) => [...prev, ...page.attempts.filter((r) => !prev.some((p) => p.attempt_id === r.attempt_id))]);
      } else {
        setAttemptHistory(page.attempts);
        setSelectedAttemptId(page.attempts[0]?.attempt_id ?? '');
      }
      setAttemptNextCursor(page.nextCursor);
      setAttemptHasMore(page.hasMore);
    } finally {
      setAttemptLoading(false);
    }
  };

  useEffect(() => {
    void loadAttemptPage('reset');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attemptFilter]);

  useEffect(() => {
    if (setupStage === 'deploy' && !canEnterDeploy) {
      setSetupStage(canEnterBuild ? 'build' : 'connect');
      return;
    }
    if (setupStage === 'build' && !canEnterBuild) {
      setSetupStage('connect');
    }
  }, [canEnterBuild, canEnterDeploy, setupStage]);

  useEffect(() => {
    if (!manualOverrideEligible && manualSketchOverride) {
      setManualSketchOverride(false);
    }
  }, [manualOverrideEligible, manualSketchOverride]);

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
            background: '#0b0f15',
            primaryColor: '#121a24',
            primaryTextColor: '#d5deea',
            primaryBorderColor: '#6f8fb1',
            lineColor: '#86abd2',
            secondaryColor: '#101722',
            secondaryTextColor: '#c8d3e1',
            tertiaryColor: '#0d141e',
            tertiaryTextColor: '#c8d3e1',
            edgeLabelBackground: '#121a24',
            clusterBkg: '#101722',
            clusterBorder: '#6f8fb1',
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

  const attemptCtx = {
    sketchRevision,
    profileId: activeProfileId ?? robotProfile?.profile_id ?? '',
    profileLabel: robotProfile?.label ?? profileLabel ?? '',
  };

  const exportAttempts = (kind: 'json' | 'csv') => {
    const rows = filteredAttempts;
    if (!rows.length) return;
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    if (kind === 'json') {
      const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `setup-validation-attempts-${ts}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      return;
    }
    const header = ['attempt_id', 'test_type', 'status', 'created_at', 'profile_id', 'profile_label', 'sketch_revision', 'sketch_hash', 'action_source'];
    const csv = [
      header.join(','),
      ...rows.map((r) =>
        [
          r.attempt_id,
          r.test_type,
          r.status,
          r.created_at,
          r.profile_id ?? '',
          r.profile_label ?? '',
          r.sketch_revision ?? '',
          r.sketch_hash ?? '',
          r.action_source ?? '',
        ]
          .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`)
          .join(','),
      ),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `setup-validation-attempts-${ts}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const exportAttemptDetail = (item: SetupValidationAttempt) => {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const blob = new Blob([JSON.stringify(item, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `setup-attempt-${item.attempt_id}-${ts}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const onTestConnect = async () => {
    const [compatPipeline, compatProbeOut] = await Promise.all([
      setupCompatTest(attemptCtx).catch(() => null),
      runCompatProbe(),
    ]);
    if (compatPipeline) {
      setSetupCompatResult(compatPipeline.compat);
      if (compatPipeline.attempt) mergeAttempt(compatPipeline.attempt);
      setConnectTestNote(`Compat gate: ${compatPipeline.compat.status.toUpperCase()}`);
    } else {
      setConnectTestNote(`Manual test result: ${compatProbeOut?.ok ? 'PASS' : 'FAIL'}`);
    }
  };

  const onTestKalman = async () => {
    const out = await runCompatProbe();
    const compatPipeline = await setupCompatTest(attemptCtx).catch(() => null);
    if (compatPipeline) {
      setSetupCompatResult(compatPipeline.compat);
      if (compatPipeline.attempt) mergeAttempt(compatPipeline.attempt);
    }
    const missing = out?.missing_fields?.filter((f) => f === 'ang' || f === 'raw' || f.includes('gyro')) ?? [];
    setKalmanTestNote(`Manual test result: ${out && missing.length === 0 ? 'PASS' : 'FAIL'}`);
  };

  const onRunSmokeCheck = async () => {
    const smoke = await setupSmokeCheck(attemptCtx).catch(() => null);
    if (!smoke) {
      setSmokeTestNote('Smoke check unavailable');
      return;
    }
    setSetupSmokeResult(smoke.smoke);
    if (smoke.attempt) mergeAttempt(smoke.attempt);
    setSmokeTestNote(`Smoke gate: ${smoke.smoke.status.toUpperCase()}${smoke.smoke.failure_summary ? ` (${smoke.smoke.failure_summary})` : ''}`);
  };

  const onTestReadiness = async () => {
    if (connectProbe) {
      const testedPhase2Ready = connectProbe.phase2_ready ?? connectProbe.v2_ready;
      setReadinessTestNote(`Already tested: ${testedPhase2Ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}`);
      return;
    }
    const out = await runConnectWizard();
    const outPhase2Ready = out?.phase2_ready ?? out?.v2_ready;
    setReadinessTestNote(`Manual test result: ${outPhase2Ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}`);
  };

  const onTestOverwatch = async () => {
    const [out, pipeline] = await Promise.all([
      runOverwatchCheck(),
      setupOverwatchCheck(attemptCtx).catch(() => null),
    ]);
    if (pipeline?.attempt) mergeAttempt(pipeline.attempt);
    const status = pipeline?.overwatch?.status ?? (out ? String(out.overall).toLowerCase() : 'fail');
    if (!out && !pipeline?.overwatch?.overwatch) {
      setOverwatchTestNote(`Manual test result: ${String(status).toUpperCase()}`);
      return;
    }
    const score = out?.score_pct ?? pipeline?.overwatch?.overwatch?.score_pct ?? 0;
    setOverwatchTestNote(`Manual test result: ${String(status).toUpperCase()} (${score}%)`);
  };

  const renderAttemptSummary = (item: SetupValidationAttempt) => {
    const t = String(item.test_type).toLowerCase();
    const r = (item.result ?? {}) as Record<string, unknown>;
    if (t === 'compat') {
      const issues = Array.isArray(r.blocking_issues) ? r.blocking_issues as string[] : [];
      const warns = Array.isArray(r.warnings) ? r.warnings as string[] : [];
      return (
        <div className="setup-attempt-summary">
          <p><strong>Blocking:</strong> {issues.length ? issues.join(', ') : 'none'}</p>
          <p><strong>Warnings:</strong> {warns.length ? warns.join(' | ') : 'none'}</p>
        </div>
      );
    }
    if (t === 'smoke') {
      const checks = Array.isArray(r.checks) ? r.checks as Array<{ id?: string; status?: string }> : [];
      return (
        <div className="setup-attempt-summary">
          <p><strong>Failure Summary:</strong> {String(r.failure_summary ?? 'none')}</p>
          <p><strong>Checks:</strong> {checks.length}</p>
        </div>
      );
    }
    if (t === 'overwatch') {
      const ow = (r.overwatch ?? {}) as Record<string, unknown>;
      const counts = (ow.counts ?? {}) as Record<string, unknown>;
      return (
        <div className="setup-attempt-summary">
          <p><strong>Score:</strong> {String(ow.score_pct ?? 'n/a')}%</p>
          <p><strong>Pass/Warn/Fail:</strong> {String(counts.pass ?? 0)}/{String(counts.warn ?? 0)}/{String(counts.fail ?? 0)}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <section className="setup-workflow-page">
      <h2>Setup Workflow</h2>
      <div className="setup-flow-strip" aria-label="Setup validation flow">
        {flowSteps.map((step, idx) => (
          <button
            key={step.id}
            type="button"
            className={`setup-flow-step tone-${statusTone(step.status as SetupValidationStatus)} ${setupStage === flowStepTarget(step.id) ? 'is-active' : ''}`}
            disabled={!flowStepEnabled(step.id)}
            onClick={() => setSetupStage(flowStepTarget(step.id))}
            title={flowStepEnabled(step.id) ? `Go to ${step.label}` : `Locked: complete previous steps first`}
          >
            <span className="setup-flow-step-index">{idx + 1}</span>
            <span className="setup-flow-step-label">{step.label}</span>
          </button>
        ))}
      </div>
      {stageBlockedReason && <p className="setup-rig-test-note">{stageBlockedReason}</p>}
      <div className="setup-phase-grid">
        <div className={`wizard-box setup-phase-col ${setupStage === 'connect' ? 'is-active' : 'is-hidden'}`}>
          <div className="setup-phase-head">
            <h3>1_CONNECT</h3>
            <span className="workflow-label">detect, validate, save, activate</span>
          </div>

          {validation && (
            <div className="connect-validation-pills">
              <span className={`hud-pill ${validation.ok ? 'good' : 'bad'}`}>Validation {validation.ok ? 'PASS' : 'FAIL'} · {validation.score_pct}%</span>
              <span className="hud-pill unknown">Duration {validation.duration_s}s</span>
              <span className={`hud-pill ${activeProfileId ? 'good' : 'warn'}`}>Active {activeProfileId ?? 'none'}</span>
            </div>
          )}

          <div className="wizard-box connect-wizard-clean">
            <h3>Connect Wizard</h3>
            <p className="wizard-subtitle">Detect hardware, save/select profile, then activate.</p>
            <p className="wizard-profile-summary">
              Active Profile: <strong>{robotProfile?.label ?? 'none selected'}</strong>
            </p>
            <div className="connect-wizard-rail" role="tablist" aria-label="Connect wizard steps">
              <button
                type="button"
                className={`btn-secondary btn-sm ${connectWizardStep === 'detect' ? 'is-active' : ''}`}
                onClick={() => setConnectWizardStep('detect')}
              >
                Detect {detectComplete ? '✓' : ''}
              </button>
              <button
                type="button"
                className={`btn-secondary btn-sm ${connectWizardStep === 'profile' ? 'is-active' : ''}`}
                onClick={() => setConnectWizardStep('profile')}
              >
                Profile {profileComplete ? '✓' : ''}
              </button>
              <button
                type="button"
                className={`btn-secondary btn-sm ${connectWizardStep === 'activate' ? 'is-active' : ''}`}
                onClick={() => setConnectWizardStep('activate')}
              >
                Activate {activateComplete ? '✓' : ''}
              </button>
              <div className="setup-stage-nav-spacer" />
              <span className={`hud-pill ${healthPort ? 'good' : 'bad'}`}>Bridge {healthPort ? 'online' : 'offline'}</span>
            </div>
            <div className="wizard-box mission-brief-box">
              <h4 className="setup-subhead">Mission Brief (recommended before Parts)</h4>
              <p className="setup-subnote">
                Define mission intent first so hardware choices and generated recommendations stay aligned.
              </p>
              <div className="hardware-intake-grid">
                <label className="hardware-intake-notes">
                  Mission Objective
                  <input
                    type="text"
                    value={missionObjective}
                    onChange={(e) => setMissionObjective(e.target.value)}
                    placeholder="ex: stable indoor balance with minimal drift"
                  />
                </label>
                <label>
                  Environment
                  <select value={missionEnvironment} onChange={(e) => setMissionEnvironment(e.target.value)}>
                    <option value="indoor_flat">Indoor flat</option>
                    <option value="indoor_mixed">Indoor mixed floor</option>
                    <option value="outdoor_smooth">Outdoor smooth</option>
                    <option value="outdoor_rough">Outdoor rough</option>
                    <option value="bench_tuning">Bench tuning stand</option>
                  </select>
                </label>
                <label>
                  Priority
                  <select value={missionPriority} onChange={(e) => setMissionPriority(e.target.value)}>
                    <option value="stability">Stability</option>
                    <option value="safety">Safety margin</option>
                    <option value="responsiveness">Response speed</option>
                    <option value="runtime">Runtime efficiency</option>
                    <option value="exploration">Exploration / learning</option>
                  </select>
                </label>
                <label className="hardware-intake-notes">
                  Success Criteria
                  <input
                    type="text"
                    value={missionSuccess}
                    onChange={(e) => setMissionSuccess(e.target.value)}
                    placeholder="ex: no tip events, low drift, stable telemetry"
                  />
                </label>
              </div>
              <div className="hardware-intake-status-row">
                <span className={`hud-pill ${missionGateReady ? 'good' : 'warn'}`}>
                  Mission {missionReady ? 'READY' : missionBypassReady ? 'BYPASSED' : 'MISSING'}
                </span>
              </div>
            </div>

            {connectWizardStep === 'detect' && (
              <div className="wizard-box">
                <h4 className="setup-subhead">Detect Hardware</h4>
                <p className="setup-subnote">Run one probe to capture board, firmware, and component evidence.</p>
                <div className="row">
                  <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void runConnectWizard()}>
                    Run Auto-Detect
                  </button>
                  {detectComplete && (
                    <button className="btn-secondary btn-sm" onClick={() => setConnectWizardStep('profile')}>
                      Next: Profile
                    </button>
                  )}
                </div>
                {connectProbe && (
                  <div className="wizard-results connect-probe-compact">
                    <p><strong>Board:</strong> {connectProbe.mcu_guess || 'unknown'}</p>
                    <p><strong>Profile:</strong> {connectProbe.firmware_profile || 'unknown'}</p>
                    <p><strong>Port:</strong> {connectProbe.port_meta.description ?? connectProbe.port ?? 'n/a'}</p>
                    <p><strong>Confidence:</strong> {connectProbe.confidence_pct}%</p>
                  </div>
                )}
              </div>
            )}

            {connectWizardStep === 'profile' && !connectEntryMode && (
              <div className="setup-entry-choice-grid">
                <button className="setup-entry-choice" onClick={() => setConnectEntryMode('new')}>
                  <strong>New Robot</strong>
                  <span>Create and save from current detection.</span>
                </button>
                <button className="setup-entry-choice" onClick={() => setConnectEntryMode('existing')}>
                  <strong>Select / Load Robot</strong>
                  <span>Load a saved profile.</span>
                </button>
              </div>
            )}

            {connectWizardStep === 'profile' && connectEntryMode === 'new' && (
              <>
                <h4 className="setup-subhead">Create Profile</h4>
                <p className="setup-subnote">Set label/chassis and save.</p>
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
                <div className="row">
                  <button className="btn-secondary btn-sm" onClick={() => setConnectEntryMode(null)}>Back To Choice</button>
                  <button className="btn-secondary btn-sm" disabled={!profileComplete} onClick={() => setConnectWizardStep('activate')}>
                    Next: Activate
                  </button>
                </div>
              </>
            )}

            {connectWizardStep === 'profile' && connectEntryMode === 'existing' && (
              <>
                <h4 className="setup-subhead">Load Existing Profile</h4>
                <p className="setup-subnote">Select and load a saved profile.</p>
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
                <div className="row">
                  <button className="btn-secondary btn-sm" onClick={() => setConnectWizardStep('activate')}>
                    Next: Activate
                  </button>
                </div>
                <div className="row">
                  <button className="btn-secondary btn-sm" onClick={() => setConnectWizardAdvanced((v) => !v)}>
                    {connectWizardAdvanced ? 'Hide Advanced' : 'Show Advanced'}
                  </button>
                </div>
                <div className={`wizard-actions ${connectWizardAdvanced ? '' : 'is-hidden'}`}>
                  <button onClick={loadSavedRobotProfile}>Load Active Saved Profile</button>
                  <button disabled={!selectedProfileId} onClick={() => void exportProfileById(selectedProfileId)}>Export Selected Profile JSON</button>
                  <button onClick={importRobotProfile}>Import Profile JSON</button>
                  <button disabled={!selectedProfileId} onClick={() => deleteProfileById(selectedProfileId)}>Delete Selected Profile</button>
                </div>
                <div className="row">
                  <button className="btn-secondary btn-sm" onClick={() => setConnectEntryMode(null)}>Back To Choice</button>
                </div>
              </>
            )}

            {connectWizardStep === 'activate' && (
              <div className="wizard-box">
                <h4 className="setup-subhead">Activate Profile</h4>
                <p className="setup-subnote">Set one profile active for this session.</p>
                <div className="row">
                  <button className="btn-secondary btn-sm" disabled={!selectedProfileId || !validation?.ok} onClick={() => void activateProfileByIdIfValid(selectedProfileId)}>
                    Set Active
                  </button>
                  <button className="btn-secondary btn-sm" disabled={!activateComplete} onClick={() => setSetupStage('build')}>
                    Continue to Robot Setup
                  </button>
                </div>
              </div>
            )}

            {robotProfile && (
              <p className="wizard-profile-summary">
                Saved Profile: <strong>{robotProfile.label}</strong> · {robotProfile.chassis} · confidence {robotProfile.probe.confidence_pct}%
              </p>
            )}

            {connectProbe && connectWizardStep !== 'detect' && (
              <div className="wizard-results">
                {(() => {
                  const probeComponents = connectProbe.components ?? {
                    imu: false,
                    motor_driver: false,
                    encoder_feedback: false,
                    voltage_telemetry: false,
                  };
                  const probeMissingCommands = Array.isArray(connectProbe.missing_commands)
                    ? connectProbe.missing_commands
                    : [];
                  const probePortLabel = connectProbe.port_meta?.description ?? connectProbe.port ?? 'n/a';
                  return (
                    <>
                <p><strong>Confidence:</strong> {connectProbe.confidence_pct}%</p>
                <p><strong>MCU Guess:</strong> {connectProbe.mcu_guess}</p>
                <p><strong>Firmware Profile:</strong> {connectProbe.firmware_profile}</p>
                <p><strong>USB Device:</strong> {probePortLabel}</p>
                <p>
                  <strong>Components:</strong>{' '}
                  IMU={probeComponents.imu ? 'Y' : 'N'} ·
                  Motor={probeComponents.motor_driver ? 'Y' : 'N'} ·
                  Enc={probeComponents.encoder_feedback ? 'Y' : 'N'} ·
                  Volt={probeComponents.voltage_telemetry ? 'Y' : 'N'}
                </p>
                <p><strong>Missing Commands:</strong> {probeMissingCommands.length ? probeMissingCommands.join(', ') : 'none'}</p>
                    </>
                  );
                })()}
              </div>
            )}
          </div>
          <div className="setup-section-nav">
            <div className="setup-stage-nav-spacer" />
            <button className="btn-secondary btn-sm" disabled={!canStepBack} onClick={goStageBack}>
              Back
            </button>
            <button className="btn-secondary btn-sm" disabled={!canStepNext} onClick={goStageNext}>
              Next
            </button>
          </div>
        </div>

        <div className={`wizard-box setup-phase-col ${setupStage === 'build' ? 'is-active' : 'is-hidden'}`}>
          <div className="setup-phase-head">
            <h3>2_ROBOT SETUP</h3>
            <span className="workflow-label">generate sketch, coach prompts, view docs</span>
          </div>

          <div className="wizard-box">
            <h3>Current Assumed Board + Pin Mapping (Agent Sync)</h3>
            <p className="wizard-subtitle">Compares detected/assumed values against current setup selections so agent and operator stay aligned.</p>
            <div className="hardware-intake-status-row">
              <span className={`hud-pill ${assumptionBoardSync ? 'good' : 'warn'}`}>
                Board {assumptionBoardSync ? 'IN SYNC' : 'MISMATCH'}
              </span>
              <span className={`hud-pill ${assumptionPinsSync ? 'good' : 'warn'}`}>
                Pins {assumptionPinsSync ? 'IN SYNC' : `MISMATCH (${assumptionPinMismatches.length})`}
              </span>
            </div>
            <div className="wizard-results">
              <p><strong>Assumed Board:</strong> {detectedIntake.board}</p>
              <p><strong>Selected Board:</strong> {intakeBoard}</p>
              <p>
                <strong>Assumed Pins:</strong>{' '}
                {Object.entries(detectedIntake.pins).map(([k, v]) => `${k}:${String(v)}`).join(' | ')}
              </p>
              <p>
                <strong>Selected Pins:</strong>{' '}
                {Object.entries(pinMap).map(([k, v]) => `${k}:${String(v)}`).join(' | ')}
              </p>
              {!assumptionPinsSync && (
                <p><strong>Mismatched Keys:</strong> {assumptionPinMismatches.join(', ')}</p>
              )}
            </div>
          </div>

          <div className={`wizard-box ${intakeLocked ? 'is-disabled intake-locked' : ''}`}>
            <h3>Hardware Intake + Pin Guide</h3>
            <p className="wizard-subtitle">Agent fills this from generated profile, then you use it as quick assembly reference.</p>
            {intakeLocked && (
              <p className="setup-rig-test-note">
                Locked until sketch generation finishes.
              </p>
            )}
            <div className="hardware-intake-grid">
              <label>
                Board FQBN
                <select value={selectedBoardProfile.id} disabled={intakeLocked} onChange={(e) => {
                  const picked = BOARD_PROFILES.find((p) => p.id === e.target.value);
                  if (!picked) return;
                  setIntakeBoard(picked.fqbn);
                  setBoardModelOverrideId(picked.id);
                  setBoardAmbiguityConfirmed(false);
                }}>
                  {BOARD_PROFILES.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                IMU Model
                <input type="text" value={intakeImu} disabled={intakeLocked} onChange={(e) => setIntakeImu(e.target.value)} />
              </label>
              <label>
                Motor Driver
                <input type="text" value={intakeMotorDriver} disabled={intakeLocked} onChange={(e) => setIntakeMotorDriver(e.target.value)} />
              </label>
              <label>
                Encoder
                <select value={intakeEncoder} disabled={intakeLocked} onChange={(e) => setIntakeEncoder(e.target.value)}>
                  <option value="none">None</option>
                  <option value="quadrature">Quadrature</option>
                  <option value="single_channel">Single Channel</option>
                </select>
              </label>
              <label>
                Battery
                <input type="text" value={intakeBattery} disabled={intakeLocked} onChange={(e) => setIntakeBattery(e.target.value)} />
              </label>
              <label className="hardware-intake-notes">
                Build Notes
                <input type="text" value={intakeNotes} disabled={intakeLocked} onChange={(e) => setIntakeNotes(e.target.value)} placeholder="motor KV, wheel size, known quirks..." />
              </label>
            </div>

            <div className="hardware-intake-status-row">
              <span className={`hud-pill ${boardResolutionTone}`}>
                Board Resolve {Math.round(boardResolution.confidence * 100)}%{boardResolution.ambiguous ? ' (AMBIGUOUS)' : ''}
              </span>
              <span className={`hud-pill ${pinValidationTone}`}>
                Pin Validation {pinValidation.ok ? 'PASS' : 'CHECK'} · E{pinValidation.summary.errors} W{pinValidation.summary.warnings}
              </span>
            </div>
            {boardResolution.ambiguous && (
              <div className="setup-rig-test-note">
                <p>
                  Ambiguous board match from current value. Top candidates: {boardResolution.candidates.map((c) => `${c.label} (${c.score})`).join(' · ')}
                </p>
                {!boardAmbiguityConfirmed && (
                  <div className="row">
                    <button
                      className="btn-secondary btn-sm btn-intent-discover"
                      disabled={intakeLocked}
                      onClick={() => setBoardAmbiguityConfirmed(true)}
                    >
                      Confirm Selected Board Anyway
                    </button>
                  </div>
                )}
                {boardAmbiguityConfirmed && <p>Board ambiguity explicitly confirmed for this setup draft.</p>}
              </div>
            )}

            <div className={`hardware-board-visual ${intakeLocked ? 'is-locked' : ''}`}>
              <div className="hardware-board-head">
                <strong>{selectedBoardProfile.label}</strong>
                <span className="workflow-label">{intakeLocked ? 'awaiting generated sketch' : 'assembly quick reference'}</span>
              </div>
              <div className="hardware-board-canvas">
                <div className={`hardware-board-model ${boardView3d ? 'is-3d' : ''}`} role="img" aria-label="Detected board pin layout">
                  <span className="board-chip">{intakeImu.toUpperCase()}</span>
                  <span className="board-rail left" />
                  <span className="board-rail right" />
                  <div className="board-pin-column left">
                    {selectedBoardProfile.leftPins.map((label) => {
                      const pinNum = pinNumberFromLabel(label);
                      const assignments = pinNum == null ? [] : assignmentByPin.get(pinNum) ?? [];
                      return (
                        <div className={`board-pin-slot ${assignments.length ? 'mapped' : ''}`} key={`left-${label}`}>
                          <span className="board-pin-label">{label}</span>
                          {assignments.length > 0 && <span className="board-pin-map">{assignments.join('/')}</span>}
                        </div>
                      );
                    })}
                  </div>
                  <div className="board-pin-column right">
                    {selectedBoardProfile.rightPins.map((label) => {
                      const pinNum = pinNumberFromLabel(label);
                      const assignments = pinNum == null ? [] : assignmentByPin.get(pinNum) ?? [];
                      return (
                        <div className={`board-pin-slot ${assignments.length ? 'mapped' : ''}`} key={`right-${label}`}>
                          <span className="board-pin-label">{label}</span>
                          {assignments.length > 0 && <span className="board-pin-map">{assignments.join('/')}</span>}
                        </div>
                      );
                    })}
                  </div>
                </div>
                <div className="hardware-board-sidecar">
                  {renderBoardAssetPreview('compact')}
                  <div className="hardware-pin-badges">
                    {boardPinSummary.map(([label, pin]) => (
                      <span key={label} className="pin-badge">{label}:{String(pin)}</span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="row">
                <button className="btn-secondary btn-sm" disabled={intakeLocked} onClick={() => setBoardGuideOpen(true)}>
                  Open Large Board View
                </button>
                <button className="btn-secondary btn-sm" disabled={intakeLocked} onClick={() => setBoardView3d((v) => !v)}>
                  {boardView3d ? 'Use Flat 2D View' : 'Use Perspective View'}
                </button>
              </div>
              <div className="board-asset-links" aria-label="Board references">
                <span className="workflow-label">Reference Files</span>
                {preferredAssetHref(boardAssets?.localDocsPath, boardAssets?.docsUrl) ? (
                  <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localDocsPath, boardAssets?.docsUrl)} target="_blank" rel="noreferrer">
                    Docs
                  </a>
                ) : (
                  <span className="board-asset-link disabled">Docs n/a</span>
                )}
                {preferredAssetHref(boardAssets?.localPinoutPath, boardAssets?.pinoutUrl) ? (
                  <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localPinoutPath, boardAssets?.pinoutUrl)} target="_blank" rel="noreferrer">
                    Pinout
                  </a>
                ) : (
                  <span className="board-asset-link disabled">Pinout n/a</span>
                )}
                {preferredAssetHref(boardAssets?.localSchematicPath, boardAssets?.schematicUrl) ? (
                  <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localSchematicPath, boardAssets?.schematicUrl)} target="_blank" rel="noreferrer">
                    Schematic
                  </a>
                ) : (
                  <span className="board-asset-link disabled">Schematic n/a</span>
                )}
                {preferredAssetHref(boardAssets?.localCadPath, boardAssets?.cadStepUrl) ? (
                  <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localCadPath, boardAssets?.cadStepUrl)} target="_blank" rel="noreferrer">
                    STEP/CAD
                  </a>
                ) : (
                  <span className="board-asset-link disabled">STEP n/a</span>
                )}
              </div>
              {boardAssets?.notes?.length ? (
                <p className="setup-subnote">
                  {boardAssets.notes.join(' ')}
                </p>
              ) : null}
            </div>

            <div className="pin-guide-grid">
              <div className="pin-guide-block">
                <h4 className="setup-subhead">Required Pins</h4>
                <div className="hardware-intake-grid hardware-intake-grid-pins">
                  {(['motor_l_pwm', 'motor_l_dir', 'motor_r_pwm', 'motor_r_dir', 'imu_sda', 'imu_scl', 'gate_enable', 'led'] as const).map((key) => (
                    <label key={key}>
                      {key}
                      <input
                        type="number"
                        step="1"
                        disabled={intakeLocked}
                        value={pinMap[key]}
                        onChange={(e) => setPinMap((prev) => ({ ...prev, [key]: Number.parseInt(e.target.value || '0', 10) }))}
                      />
                    </label>
                  ))}
                </div>
              </div>
              <div className="pin-guide-block">
                <h4 className="setup-subhead">Optional Encoder Pins</h4>
                <div className="hardware-intake-grid hardware-intake-grid-pins">
                  {(['enc_l_a', 'enc_l_b', 'enc_r_a', 'enc_r_b'] as const).map((key) => (
                    <label key={key}>
                      {key}
                      <input
                        type="number"
                        step="1"
                        disabled={intakeLocked}
                        value={pinMap[key]}
                        onChange={(e) => setPinMap((prev) => ({ ...prev, [key]: Number.parseInt(e.target.value || '-1', 10) }))}
                      />
                    </label>
                  ))}
                </div>
                <p className="setup-subnote">Use <code>-1</code> for unassigned pins.</p>
              </div>
            </div>
            {pinValidation.issues.length > 0 && (
              <div className="wizard-results hardware-validation-results">
                <p><strong>Pin Validation Findings</strong></p>
                <ul className="hardware-validation-list">
                  {pinValidation.issues.slice(0, 6).map((issue, idx) => (
                    <li key={`${issue.code}-${idx}`} className={`hardware-validation-item level-${issue.level}`}>
                      <span className="hardware-validation-code">{issue.level.toUpperCase()}</span>
                      <span>{issue.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="wizard-results">
              <p><strong>Agent Handoff Payload</strong></p>
              <pre className="hardware-intake-preview">{intakeLocked ? 'Awaiting generated sketch…' : JSON.stringify(intakeProfilePreview, null, 2)}</pre>
              <div className="row">
                <button className="btn-secondary btn-sm btn-intent-prompt" disabled={intakeLocked} onClick={() => loadAssistantPrompt(intakePrompt)}>
                  Load Intake Prompt
                </button>
                <button className="btn-secondary btn-sm" disabled={intakeLocked} onClick={() => setProfileLabel(profileLabel || 'new_robot_profile')}>
                  Use As Active Label
                </button>
              </div>
            </div>
          </div>

          <div className="wizard-box">
            <h3>Sketch Generator</h3>
            <p className="wizard-subtitle">Generate scaffold from current unified profile without leaving Setup, or paste your own sketch.</p>
            <div className="setup-prereq-card" role="region" aria-label="Sketch generation prerequisites">
              <div className="setup-prereq-head">
                <strong>Prerequisites</strong>
                <span className={`hud-pill ${generatePrereqs.allReady ? 'good' : 'warn'}`}>
                  {generatePrereqs.readyCount}/{generatePrereqs.items.length} Ready
                </span>
              </div>
              <div className="setup-prereq-list">
                {generatePrereqs.items.map((item) => (
                  <div key={item.id} className="setup-prereq-item">
                    <span className={`setup-prereq-dot ${item.ok ? 'ok' : 'warn'}`} aria-hidden="true" />
                    <span className="setup-prereq-label">{item.label}</span>
                    <span className={`setup-prereq-status ${item.ok ? 'ok' : 'warn'}`}>{item.ok ? 'READY' : 'MISSING'}</span>
                    {!item.ok && <span className="setup-prereq-hint">{item.hint}</span>}
                  </div>
                ))}
              </div>
              <p className="setup-prereq-note">
                If generation still fails, check the status bar message for exact error (profile JSON parse or missing required fields).
              </p>
            </div>
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-build" disabled={!generatePrereqs.allReady} onClick={() => void runGenerateUnified()}>Generate Sketch Here</button>
              <button
                className="btn-secondary btn-sm btn-intent-prompt"
                disabled={!generatePrereqs.allReady}
                onClick={() => loadAssistantPrompt('Generate a unified scaffold now using the confirmed profile, then load the generated main .ino into the editor and tell me the sketch folder path.')}
              >
                Generate Via Agent
              </button>
              <button className="btn-secondary btn-sm btn-intent-nav" onClick={goToIde}>Open IDE Tab</button>
            </div>
            <div className="wizard-results">
              <p><strong>Advanced:</strong> Proceed without full scaffold prerequisites using your uploaded/manual sketch.</p>
              <label className="setup-subnote">
                <input
                  type="checkbox"
                  checked={manualSketchOverride}
                  disabled={!manualOverrideEligible}
                  onChange={(e) => setManualSketchOverride(e.target.checked)}
                />
                {' '}Enable Manual Sketch Override
              </label>
              <p className="setup-subnote">
                Requires: bridge online + active profile + sketch prepared. Missing: {
                  manualOverrideEligible
                    ? 'none'
                    : [
                        !healthPort ? 'bridge' : '',
                        !(activeProfileId || robotProfile?.profile_id) ? 'profile' : '',
                        !sketchPrepared ? 'sketch' : '',
                      ].filter(Boolean).join(', ')
                }.
              </p>
              {manualOverrideActive && (
                <p className="setup-rig-test-note">
                  Manual override active: Setup will allow moving to Deployment without all scaffold prerequisites.
                </p>
              )}
            </div>
            {!generatePrereqs.allReady && <p className="setup-rig-test-note">{generationBlockedReason}</p>}
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

          <details className="wizard-box">
            <summary className="setup-subhead">Prompt Coach (Optional)</summary>
            <h3>Prompt Coach</h3>
            <p className="wizard-subtitle">Use guided prompts in Codex, then continue to IDE and Tuning.</p>
            <div className="wizard-results">
              <p><strong>1. Detect + summarize:</strong> Ask Codex to summarize board/fqbn/port and missing commands.</p>
              <div className="row">
                <button className="btn-secondary btn-sm btn-intent-prompt" onClick={() => loadAssistantPrompt('Summarize the latest connect and compat probe results as board/fqbn/port, missing fields, and missing commands using current tool output. Then give me the next action in one line.')}>Load Step 1 Prompt</button>
              </div>

              <p><strong>2. Prepare scaffold profile:</strong> Ask Codex to draft unified profile JSON using detected hardware.</p>
              <div className="row">
                <button className="btn-secondary btn-sm btn-intent-prompt" onClick={() => loadAssistantPrompt('Draft a unified scaffold profile JSON for this robot using detected board/fqbn/port. Use available tools to verify likely defaults quickly, apply conservative placeholder pin mapping where needed, and list only assumptions that still need my confirmation.')}>Load Step 2 Prompt</button>
              </div>

              <p><strong>3. Tuning handoff:</strong> Ask for first-safe-test recommendations once flashed.</p>
              <div className="row">
                <button className="btn-secondary btn-sm btn-intent-nav" onClick={goToTune}>Go To Tuning Tab</button>
                <button className="btn-secondary btn-sm btn-intent-prompt" onClick={() => loadAssistantPrompt('I am ready for first balance test. Give me a safe 3-step sequence for CAL ZERO, arm/disarm verification, and first PID baseline check. Keep it concise and execution-ready.')}>Load Tuning Prompt</button>
              </div>
            </div>
          </details>

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
          <div className="setup-section-nav">
            <div className="setup-stage-nav-spacer" />
            <button className="btn-secondary btn-sm" disabled={!canStepBack} onClick={goStageBack}>
              Back
            </button>
            <button className="btn-secondary btn-sm" disabled={!canStepNext} onClick={goStageNext}>
              Next
            </button>
          </div>
        </div>

        <div className={`wizard-box setup-phase-col setup-phase-col-deployment ${setupStage === 'deploy' ? 'is-active' : 'is-hidden'}`}>
          <div className="setup-phase-head">
            <h3>3_DEPLOYMENT TEST</h3>
            <span className="workflow-label">connect + kalman + anti-drift readiness</span>
          </div>

          <div className={`wizard-box setup-rig tone-${connectTone} ${rigPulseClass(0, connectTone)}`}>
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

          <div className={`wizard-box setup-rig tone-${kalmanTone} ${rigPulseClass(1, kalmanTone)}`}>
            <div className="setup-rig-head">
              <h3>Kalman Telemetry Standard</h3>
              <span className={`hud-pill ${kalmanTone}`}>{compatKnown ? (kalmanStandardOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</span>
            </div>
            <div className="setup-rig-layout">
              <div className="setup-rig-main">
                <p className="wizard-subtitle">Required IMU fusion contract: accel-angle + gyro-rate to filtered angle telemetry.</p>
                <p className="wizard-profile-summary">Required fields: <strong>ang</strong>, <strong>raw</strong>, <strong>gyro|gyr|gx</strong>.</p>
                <p className="wizard-profile-summary">Control chain: <strong>signal=ang</strong>, <strong>error=set-ang</strong>, <strong>output=out</strong>.</p>
                <p className="wizard-profile-summary">Current check: <strong>{compatKnown ? (kalmanStandardOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</strong></p>
                <div className="row"><button className="btn-secondary btn-sm btn-intent-discover btn-cal-zero" onClick={() => void onTestKalman()}>Test Kalman</button></div>
                {kalmanTestNote && <p className="setup-rig-test-note">{kalmanTestNote}</p>}
              </div>
              <div className="setup-rig-side">
                <p><strong>Filtered angle:</strong> ang</p>
                <p><strong>Raw accel angle:</strong> raw</p>
                <p><strong>Gyro rate:</strong> gyro|gyr|gx</p>
                <p><strong>Innovation:</strong> raw - ang</p>
                <p><strong>Missing:</strong> {kalmanMissing.length > 0 ? kalmanMissing.join(', ') : 'none'}</p>
              </div>
              <div className="setup-rig-ref">
                <p><strong>Evidence / References</strong></p>
                <p><code>contract.telemetry.required</code>: ang, raw, gyro|gyr|gx</p>
                <p><code>detected</code>: {kalmanEvidence}</p>
                <p><code>concept</code>: signal -&gt; error -&gt; output + Kalman innovation</p>
              </div>
            </div>
          </div>

          <div className={`wizard-box setup-rig tone-${statusTone(smokeGateStatus)} ${rigPulseClass(2, statusTone(smokeGateStatus))}`}>
            <div className="setup-rig-head">
              <h3>Smoke Check Gate</h3>
              <span className={`hud-pill ${statusTone(smokeGateStatus)}`}>{smokeGateStatus ? smokeGateStatus.toUpperCase() : 'UNTESTED'}</span>
            </div>
            <div className="setup-rig-layout">
              <div className="setup-rig-main">
                <p className="wizard-subtitle">Minimal runtime viability gate after compat pass.</p>
                <div className="row"><button className="btn-secondary btn-sm btn-intent-discover btn-cal-zero" onClick={() => void onRunSmokeCheck()}>Run Smoke Check</button></div>
                {smokeTestNote && <p className="setup-rig-test-note">{smokeTestNote}</p>}
              </div>
              <div className="setup-rig-side">
                {setupSmokeResult?.checks?.slice(0, 5).map((check) => (
                  <p key={check.id}><strong>{check.id}:</strong> {check.status} · {check.detail}</p>
                ))}
                {!setupSmokeResult && <p><strong>Checks:</strong> run smoke check to populate</p>}
              </div>
              <div className="setup-rig-ref">
                <p><strong>Tune Gate</strong></p>
                <p><code>compat</code>: {compatGateStatus ?? 'unknown'}</p>
                <p><code>smoke</code>: {smokeGateStatus ?? 'unknown'}</p>
                <p><code>tune_unlocked</code>: {tuneUnlocked ? 'true' : 'false'}</p>
              </div>
            </div>
          </div>

          <div className="wizard-box setup-attempt-timeline">
            <div className="setup-rig-head">
              <h3>Validation Timeline</h3>
              <span className="hud-pill unknown">{attemptHistory.length} runs</span>
            </div>
            <div className="setup-attempt-filters">
              {(['all', 'compat', 'smoke', 'overwatch'] as const).map((kind) => (
                <button
                  key={kind}
                  className={`btn-secondary btn-sm ${attemptFilter === kind ? 'is-active' : ''}`}
                  onClick={() => setAttemptFilter(kind)}
                >
                  {kind.toUpperCase()}
                </button>
              ))}
              <button className="btn-secondary btn-sm" onClick={() => exportAttempts('json')}>Export JSON</button>
              <button className="btn-secondary btn-sm" onClick={() => exportAttempts('csv')}>Export CSV</button>
            </div>
            {attemptHistory.length === 0 && (
              <p className="setup-rig-test-note">No validation attempts yet. Run Compat or Smoke to begin timeline.</p>
            )}
            {attemptHistory.length > 0 && (
              <div className="setup-attempt-list">
                {filteredAttempts.map((item: SetupValidationAttempt) => (
                  <div
                    key={item.attempt_id}
                    className={`setup-attempt-item tone-${statusTone(item.status as SetupValidationStatus)} ${selectedAttempt?.attempt_id === item.attempt_id ? 'selected' : ''}`}
                    onClick={() => setSelectedAttemptId(item.attempt_id)}
                  >
                    <div className="setup-attempt-row">
                      <strong>{item.test_type.toUpperCase()}</strong>
                      <span>{String(item.status).toUpperCase()}</span>
                    </div>
                    <div className="setup-attempt-meta">
                      <span>{new Date(item.created_at * 1000).toLocaleTimeString()}</span>
                      <span>{item.profile_label || item.profile_id || 'profile:n/a'}</span>
                      <span>{item.sketch_revision || 'rev:n/a'}</span>
                      <span>{item.sketch_hash ? `hash:${item.sketch_hash}` : 'hash:n/a'}</span>
                    </div>
                    <div className="setup-attempt-actions">
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => {
                          const t = String(item.test_type).toLowerCase();
                          if (t === 'compat') {
                            void onTestConnect();
                          } else if (t === 'smoke') {
                            void onRunSmokeCheck();
                          } else if (t === 'overwatch') {
                            void onTestOverwatch();
                          }
                        }}
                      >
                        Re-run
                      </button>
                    </div>
                  </div>
                ))}
                {attemptHasMore && (
                  <div className="setup-attempt-actions">
                    <button className="btn-secondary btn-sm" disabled={attemptLoading || !attemptHasMore} onClick={() => void loadAttemptPage('append')}>
                      {attemptLoading ? 'Loading...' : 'Load More'}
                    </button>
                  </div>
                )}
              </div>
            )}
            {selectedAttempt && (
              <div className="setup-attempt-detail">
                <div className="setup-attempt-row">
                  <strong>Attempt Detail</strong>
                  <span>{selectedAttempt.attempt_id}</span>
                </div>
                <p className="setup-rig-test-note">
                  Type: {selectedAttempt.test_type} · Status: {String(selectedAttempt.status).toUpperCase()} · Source: {selectedAttempt.action_source}
                </p>
                <p className="setup-rig-test-note">
                  Profile: {selectedAttempt.profile_label || 'n/a'} {selectedAttempt.profile_id ? `(${selectedAttempt.profile_id})` : ''}
                </p>
                {renderAttemptSummary(selectedAttempt)}
                <div className="setup-attempt-actions">
                  <button className="btn-secondary btn-sm" onClick={() => exportAttemptDetail(selectedAttempt)}>
                    Download Attempt
                  </button>
                </div>
                <details>
                  <summary>Raw Result Payload</summary>
                  <pre>{JSON.stringify(selectedAttempt.result ?? {}, null, 2)}</pre>
                </details>
              </div>
            )}
          </div>

          <div className={`wizard-box setup-rig v2-readiness-panel tone-${readinessTone} ${rigPulseClass(3, readinessTone)}`}>
            <div className="setup-rig-head">
              <h3>{strings.v2Readiness.title}</h3>
              <span className={`hud-pill ${readinessTone}`}>{!connectProbe ? 'UNTESTED' : phase2Ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}</span>
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
                <p><strong>{strings.v2Readiness.v1Status}:</strong> {phase1Ready ? strings.v2Readiness.pass : strings.v2Readiness.fail}</p>
                <p><strong>{strings.v2Readiness.v2Status}:</strong> {phase2Ready ? strings.v2Readiness.pass : strings.v2Readiness.warn}</p>
                <p><strong>{strings.v2Readiness.missingFields}:</strong> {missingPhase2Text}</p>
                <p><strong>{strings.v2Readiness.presentFields}:</strong> {presentAdvancedText}</p>
              </div>
              <div className="setup-rig-ref">
                <p><strong>Evidence / References</strong></p>
                <p><code>contract.version</code>: {connectProbe?.contract_version_detected ?? 'unknown'}</p>
                <p><code>phase2.present</code>: {phase2PresentEvidence}</p>
                <p><code>readiness.checks</code>: {readinessEvidence}</p>
              </div>
            </div>
          </div>

          <div className={`wizard-box setup-rig tone-${overwatchTone} ${rigPulseClass(4, overwatchTone)}`}>
            <div className="setup-rig-head">
              <h3>Overwatch Integrity</h3>
              <span className={`hud-pill ${overwatchTone}`}>
                {!overwatch ? 'UNTESTED' : String(overwatch.overall).toUpperCase()}
              </span>
            </div>
            <div className="setup-rig-layout">
              <div className="setup-rig-main">
                <p className="wizard-subtitle">Continuous integrity guard for sketch, docs, telemetry contract, and signal/error/output estimator health.</p>
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
                {overwatch?.checks?.slice(0, 5).map((c) => (
                  <p key={c.id}><code>{c.id}</code>: {c.status} · {c.detail}</p>
                ))}
                {!overwatch && <p><code>status</code>: run overwatch to populate checks</p>}
              </div>
            </div>
          </div>
          <div className="setup-section-nav">
            <div className="setup-stage-nav-spacer" />
            <button className="btn-secondary btn-sm" disabled={!canStepBack} onClick={goStageBack}>
              Back
            </button>
            <button className="btn-secondary btn-sm" disabled={!canStepNext} onClick={goStageNext}>
              Next
            </button>
          </div>
        </div>
      </div>

      <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void refreshBridge()}>
        Refresh
      </button>

      {boardGuideOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Board pin guide" onClick={() => setBoardGuideOpen(false)}>
          <div className="preflight-modal board-guide-modal glass-surface glass-surface-strong" onClick={(e) => e.stopPropagation()}>
            <div className="firmware-docs-head">
              <h3>{selectedBoardProfile.label} Pin Guide</h3>
              <button className="firmware-docs-close" aria-label="Close board guide" onClick={() => setBoardGuideOpen(false)}>
                ×
              </button>
            </div>
            <div className="board-guide-assets">
              {preferredAssetHref(boardAssets?.localDocsPath, boardAssets?.docsUrl) && (
                <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localDocsPath, boardAssets?.docsUrl)} target="_blank" rel="noreferrer">
                  Open Docs
                </a>
              )}
              {preferredAssetHref(boardAssets?.localPinoutPath, boardAssets?.pinoutUrl) && (
                <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localPinoutPath, boardAssets?.pinoutUrl)} target="_blank" rel="noreferrer">
                  Open Pinout
                </a>
              )}
              {preferredAssetHref(boardAssets?.localSchematicPath, boardAssets?.schematicUrl) && (
                <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localSchematicPath, boardAssets?.schematicUrl)} target="_blank" rel="noreferrer">
                  Open Schematic
                </a>
              )}
              {preferredAssetHref(boardAssets?.localCadPath, boardAssets?.cadStepUrl) && (
                <a className="btn-secondary btn-sm board-asset-link" href={preferredAssetHref(boardAssets?.localCadPath, boardAssets?.cadStepUrl)} target="_blank" rel="noreferrer">
                  Open STEP/CAD
                </a>
              )}
            </div>
            {renderBoardAssetPreview('modal')}
            <div className="board-guide-body">
              <div className={`hardware-board-model hardware-board-model-lg ${boardView3d ? 'is-3d' : ''}`} role="img" aria-label="Large board pin layout">
                <span className="board-chip">{intakeImu.toUpperCase()}</span>
                <span className="board-rail left" />
                <span className="board-rail right" />
                <div className="board-pin-column left">
                  {selectedBoardProfile.leftPins.map((label) => {
                    const pinNum = pinNumberFromLabel(label);
                    const assignments = pinNum == null ? [] : assignmentByPin.get(pinNum) ?? [];
                    return (
                      <div className={`board-pin-slot ${assignments.length ? 'mapped' : ''}`} key={`left-lg-${label}`}>
                        <span className="board-pin-label">{label}</span>
                        {assignments.length > 0 && <span className="board-pin-map">{assignments.join('/')}</span>}
                      </div>
                    );
                  })}
                </div>
                <div className="board-pin-column right">
                  {selectedBoardProfile.rightPins.map((label) => {
                    const pinNum = pinNumberFromLabel(label);
                    const assignments = pinNum == null ? [] : assignmentByPin.get(pinNum) ?? [];
                    return (
                      <div className={`board-pin-slot ${assignments.length ? 'mapped' : ''}`} key={`right-lg-${label}`}>
                        <span className="board-pin-label">{label}</span>
                        {assignments.length > 0 && <span className="board-pin-map">{assignments.join('/')}</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {docsOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={strings.firmwareDocs.viewerTitle} onClick={() => setDocsOpen(false)}>
          <div className="preflight-modal firmware-docs-modal glass-surface glass-surface-strong" onClick={(e) => e.stopPropagation()}>
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
