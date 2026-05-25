// Persistent voice preference — reads/writes localStorage.
// Reactive via Svelte 5 runes so any component can $derived from it.

export type OpenAIVoice = 'onyx' | 'echo' | 'fable' | 'alloy' | 'nova' | 'shimmer';

export interface VoicePreference {
  voice: OpenAIVoice;
  speed: number;
}

const STORAGE_KEY = 'hireforge_voice';
const DEFAULT: VoicePreference = { voice: 'onyx', speed: 0.92 };

function load(): VoicePreference {
  if (typeof localStorage === 'undefined') return DEFAULT;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT;
    const parsed = JSON.parse(raw) as Partial<VoicePreference>;
    return {
      voice: (parsed.voice ?? DEFAULT.voice) as OpenAIVoice,
      speed: parsed.speed ?? DEFAULT.speed,
    };
  } catch {
    return DEFAULT;
  }
}

function createVoiceSettings() {
  let pref = $state<VoicePreference>(load());

  function save(next: VoicePreference) {
    pref = next;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    }
  }

  return {
    get current() { return pref; },
    setVoice(v: OpenAIVoice) { save({ ...pref, voice: v }); },
    setSpeed(s: number) { save({ ...pref, speed: s }); },
    reset() { save(DEFAULT); },
  };
}

export const voiceSettings = createVoiceSettings();

export const VOICE_OPTIONS: { value: OpenAIVoice; label: string; gender: string; description: string }[] = [
  { value: 'onyx',    label: 'Onyx',    gender: 'Male',    description: 'Deep & authoritative (default)' },
  { value: 'echo',    label: 'Echo',    gender: 'Male',    description: 'Clear & resonant' },
  { value: 'fable',   label: 'Fable',   gender: 'Male',    description: 'Warm & expressive' },
  { value: 'alloy',   label: 'Alloy',   gender: 'Neutral', description: 'Balanced & natural' },
  { value: 'nova',    label: 'Nova',    gender: 'Female',  description: 'Bright & confident' },
  { value: 'shimmer', label: 'Shimmer', gender: 'Female',  description: 'Soft & conversational' },
];

export const SPEED_PRESETS: { value: number; label: string }[] = [
  { value: 0.75, label: 'Slow' },
  { value: 0.92, label: 'Natural' },
  { value: 1.1,  label: 'Fast' },
  { value: 1.25, label: 'Very fast' },
];
