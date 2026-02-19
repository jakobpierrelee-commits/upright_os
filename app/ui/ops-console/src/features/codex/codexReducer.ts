import type { AiHistoryItem, AiProfile, AiStatus, AiThreadSummary, AuthUser } from '../../api';

export type AuthMode = 'login' | 'register';

export type CodexState = {
  ai: AiStatus;
  aiHistory: AiHistoryItem[];
  aiThreads: AiThreadSummary[];
  aiActiveThreadId: string | null;
  aiProfiles: AiProfile[];
  aiActiveProfileId: string | null;
  aiProfileLabelInput: string;
  aiProfileDescriptionInput: string;
  aiProfileInstructionsInput: string;
  aiProfileAllowAutoApplyInput: boolean;
  aiInput: string;
  aiBusy: boolean;
  authMode: AuthMode;
  authBusy: boolean;
  authEmail: string;
  authPassword: string;
  authAlert: { tone: 'error' | 'ok'; text: string } | null;
  authUser: AuthUser | null;
  openAiKeyInput: string;
  openAiModelInput: string;
};

type CodexAction =
  | { type: 'set_ai'; payload: AiStatus }
  | { type: 'set_ai_history'; payload: AiHistoryItem[] }
  | { type: 'set_ai_threads'; payload: AiThreadSummary[] }
  | { type: 'set_ai_active_thread'; payload: string | null }
  | { type: 'set_ai_profiles'; payload: AiProfile[] }
  | { type: 'set_ai_active_profile'; payload: string | null }
  | { type: 'set_ai_profile_label_input'; payload: string }
  | { type: 'set_ai_profile_description_input'; payload: string }
  | { type: 'set_ai_profile_instructions_input'; payload: string }
  | { type: 'set_ai_profile_allow_auto_apply_input'; payload: boolean }
  | { type: 'set_ai_input'; payload: string }
  | { type: 'set_ai_busy'; payload: boolean }
  | { type: 'set_auth_mode'; payload: AuthMode }
  | { type: 'set_auth_busy'; payload: boolean }
  | { type: 'set_auth_email'; payload: string }
  | { type: 'set_auth_password'; payload: string }
  | { type: 'set_auth_alert'; payload: { tone: 'error' | 'ok'; text: string } | null }
  | { type: 'set_auth_user'; payload: AuthUser | null }
  | { type: 'patch_auth_user'; payload: Partial<AuthUser> }
  | { type: 'set_openai_key_input'; payload: string }
  | { type: 'set_openai_model_input'; payload: string };

export const initialCodexState: CodexState = {
  ai: { configured: false, model: 'unknown', history_len: 0 },
  aiHistory: [],
  aiThreads: [],
  aiActiveThreadId: null,
  aiProfiles: [],
  aiActiveProfileId: null,
  aiProfileLabelInput: '',
  aiProfileDescriptionInput: '',
  aiProfileInstructionsInput: '',
  aiProfileAllowAutoApplyInput: true,
  aiInput: '',
  aiBusy: false,
  authMode: 'login',
  authBusy: false,
  authEmail: '',
  authPassword: '',
  authAlert: null,
  authUser: null,
  openAiKeyInput: '',
  openAiModelInput: 'gpt-5-mini',
};

export function codexReducer(state: CodexState, action: CodexAction): CodexState {
  switch (action.type) {
    case 'set_ai':
      return { ...state, ai: action.payload };
    case 'set_ai_history':
      return { ...state, aiHistory: action.payload };
    case 'set_ai_threads':
      return { ...state, aiThreads: action.payload };
    case 'set_ai_active_thread':
      return { ...state, aiActiveThreadId: action.payload };
    case 'set_ai_profiles':
      return { ...state, aiProfiles: action.payload };
    case 'set_ai_active_profile':
      return { ...state, aiActiveProfileId: action.payload };
    case 'set_ai_profile_label_input':
      return { ...state, aiProfileLabelInput: action.payload };
    case 'set_ai_profile_description_input':
      return { ...state, aiProfileDescriptionInput: action.payload };
    case 'set_ai_profile_instructions_input':
      return { ...state, aiProfileInstructionsInput: action.payload };
    case 'set_ai_profile_allow_auto_apply_input':
      return { ...state, aiProfileAllowAutoApplyInput: action.payload };
    case 'set_ai_input':
      return { ...state, aiInput: action.payload };
    case 'set_ai_busy':
      return { ...state, aiBusy: action.payload };
    case 'set_auth_mode':
      return { ...state, authMode: action.payload };
    case 'set_auth_busy':
      return { ...state, authBusy: action.payload };
    case 'set_auth_email':
      return { ...state, authEmail: action.payload };
    case 'set_auth_password':
      return { ...state, authPassword: action.payload };
    case 'set_auth_alert':
      return { ...state, authAlert: action.payload };
    case 'set_auth_user':
      return { ...state, authUser: action.payload };
    case 'patch_auth_user':
      if (!state.authUser) return state;
      return { ...state, authUser: { ...state.authUser, ...action.payload } };
    case 'set_openai_key_input':
      return { ...state, openAiKeyInput: action.payload };
    case 'set_openai_model_input':
      return { ...state, openAiModelInput: action.payload };
    default:
      return state;
  }
}
