<script lang="ts">
  import { page } from '$app/state';
  import { fetchTTS, getInterviewSession } from '$lib/api';
  import { getTTSCache, getUserRec, recKey, setTTSCache, ttsKey } from '$lib/audioCache';
  import { toastState } from '$lib/toast.svelte';
  import type { InterviewSessionDetail, InterviewQuestionRecord } from '$lib/types';
  import { voiceSettings } from '$lib/voiceSettings.svelte';
  import {
    ArrowLeft,
    CheckCircle2,
    ChevronDown,
    Circle,
    ExternalLink,
    History,
    Mic,
    MicOff,
    Play,
    RefreshCw,
    Volume2,
    X,
  } from '@lucide/svelte';

  const sessionId = $derived(Number(page.params.id));

  let session = $state<InterviewSessionDetail | null>(null);
  let loading = $state(true);

  // Per-question audio state
  let playingAudio = $state<HTMLAudioElement | null>(null);
  let playingKey = $state(''); // which audio item is playing: 'ai-{idx}' | 'user-{idx}'
  let playbackSpeed = $state(1.0);

  // Expanded question accordion
  let expandedIdx = $state<number | null>(0);

  // Drill state (sentence-level)
  let drillSentence = $state<string | null>(null);
  let drillPlaying = $state(false);

  $effect(() => {
    if (sessionId) loadSession();
  });

  async function loadSession() {
    loading = true;
    try {
      session = await getInterviewSession(sessionId);
    } catch {
      toastState.error('Session not found.');
    } finally {
      loading = false;
    }
  }

  function stopAudio() {
    playingAudio?.pause();
    playingAudio = null;
    playingKey = '';
  }

  async function playAI(q: InterviewQuestionRecord, idx: number) {
    if (!q.model_answer) return;
    stopAudio();
    const key = `ai-${idx}`;
    playingKey = key;
    const voice = voiceSettings.current.voice;
    const speed = voiceSettings.current.speed * playbackSpeed;
    const cacheKey = ttsKey(q.model_answer, voice, speed);
    try {
      let blob = await getTTSCache(cacheKey);
      if (!blob) {
        blob = await fetchTTS(q.model_answer, voice, speed);
        setTTSCache(cacheKey, blob);
      }
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      playingAudio = audio;
      audio.onended = () => { URL.revokeObjectURL(url); if (playingKey === key) playingKey = ''; };
      audio.onerror = () => { URL.revokeObjectURL(url); if (playingKey === key) playingKey = ''; };
      await audio.play();
    } catch (e) {
      playingKey = '';
      toastState.error('Audio playback failed.');
    }
  }

  async function playUserRec(idx: number) {
    stopAudio();
    const key = `user-${idx}`;
    playingKey = key;
    const rk = recKey(sessionId, idx);
    try {
      const blob = await getUserRec(rk);
      if (!blob) {
        playingKey = '';
        toastState.error('Recording not found in local storage. It may have been cleared.');
        return;
      }
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      playingAudio = audio;
      audio.onended = () => { URL.revokeObjectURL(url); if (playingKey === key) playingKey = ''; };
      audio.onerror = () => { URL.revokeObjectURL(url); if (playingKey === key) playingKey = ''; };
      await audio.play();
    } catch {
      playingKey = '';
      toastState.error('Could not play recording.');
    }
  }

  async function playDrill(sentence: string) {
    drillPlaying = true;
    const voice = voiceSettings.current.voice;
    const speed = (voiceSettings.current.speed * playbackSpeed) * 0.82;
    const key = ttsKey(sentence, voice, speed);
    try {
      let blob = await getTTSCache(key);
      if (!blob) {
        blob = await fetchTTS(sentence, voice, speed);
        setTTSCache(key, blob);
      }
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => { URL.revokeObjectURL(url); drillPlaying = false; };
      audio.onerror = () => { URL.revokeObjectURL(url); drillPlaying = false; };
      await audio.play();
    } catch {
      drillPlaying = false;
    }
  }

  function splitSentences(text: string): string[] {
    const raw = text.match(/[^.!?…]+[.!?…]+(?:\s|$)?/g) ?? [text];
    return raw.map(s => s.trim()).filter(s => s.length > 8);
  }

  function scoreColor(score: number | null) {
    if (!score) return 'text-muted-foreground';
    if (score >= 80) return 'text-green-600 dark:text-green-400';
    if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-500 dark:text-red-400';
  }

  function scoreBg(score: number | null) {
    if (!score) return 'bg-muted/50 border-border';
    if (score >= 80) return 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800';
    if (score >= 60) return 'bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800';
    return 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800';
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'long', timeStyle: 'short' });
  }

  const avgScore = $derived(
    session?.questions?.filter(q => q.score !== null).length
      ? Math.round(session!.questions.filter(q => q.score !== null).reduce((a, q) => a + (q.score ?? 0), 0) / session!.questions.filter(q => q.score !== null).length)
      : null
  );

  const LENGTH_LABELS: Record<string, string> = { short: 'Short', medium: 'Medium', detailed: 'Detailed' };
</script>

<div class="max-w-3xl space-y-6 pb-20">
  <!-- Back nav -->
  <div class="flex items-center gap-3">
    <a href="/interview/sessions" class="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
      <ArrowLeft class="w-4 h-4" />
      All sessions
    </a>
  </div>

  {#if loading}
    <div class="space-y-4">
      {#each [1,2,3] as _}
        <div class="rounded-xl border border-border bg-card h-28 animate-pulse"></div>
      {/each}
    </div>

  {:else if !session}
    <div class="flex flex-col items-center justify-center py-20 gap-3 text-center">
      <History class="w-10 h-10 text-muted-foreground/40" />
      <p class="text-sm font-medium text-muted-foreground">Session not found.</p>
      <a href="/interview/sessions" class="text-xs text-primary underline">Back to sessions</a>
    </div>

  {:else}
    <!-- Session header -->
    <div class="rounded-xl border border-border bg-card p-5 space-y-4">
      <div class="flex items-start gap-4">
        <!-- Score ring -->
        <div class="w-16 h-16 rounded-full border-2 flex flex-col items-center justify-center shrink-0
          {avgScore !== null
            ? avgScore >= 80 ? 'border-green-400' : avgScore >= 60 ? 'border-yellow-400' : 'border-red-400'
            : 'border-border'}">
          {#if avgScore !== null}
            <span class="text-xl font-bold leading-none {scoreColor(avgScore)}">{avgScore}</span>
            <span class="text-[9px] text-muted-foreground">/100</span>
          {:else}
            <Circle class="w-6 h-6 text-muted-foreground/40" />
          {/if}
        </div>

        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <h1 class="text-xl font-bold">Interview Session</h1>
            <span class="text-[10px] px-1.5 py-0.5 rounded-full font-semibold
              {session.language === 'FR'
                ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300'
                : 'bg-muted text-muted-foreground'}">{session.language === 'FR' ? '🇫🇷 French' : '🇬🇧 English'}</span>
            {#if session.answer_length}
              <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">{LENGTH_LABELS[session.answer_length] ?? session.answer_length} answers</span>
            {/if}
          </div>
          <p class="text-xs text-muted-foreground mt-1">{formatDate(session.created_at)} · {session.question_count} questions</p>
          {#if session.application}
            <a href="/pipeline/{session.application.id}" class="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-1">
              <ExternalLink class="w-3 h-3" />
              {session.application.role_title} @ {session.application.company_name}
            </a>
          {/if}
        </div>
      </div>

      <!-- Playback speed control -->
      <div class="flex items-center gap-3 pt-2 border-t border-border/50">
        <span class="text-xs text-muted-foreground shrink-0">AI voice speed:</span>
        <div class="flex gap-1.5">
          {#each [{ v: 0.75, label: 'Slow' }, { v: 1.0, label: 'Normal' }, { v: 1.2, label: 'Fast' }] as opt}
            <button
              onclick={() => playbackSpeed = opt.v}
              class="px-2.5 py-1 rounded-md text-xs font-semibold border transition-all
                {playbackSpeed === opt.v
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:border-primary/40'}"
            >{opt.label}</button>
          {/each}
        </div>
        {#if playingKey}
          <button
            onclick={stopAudio}
            class="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border text-xs font-medium text-muted-foreground hover:bg-accent transition-colors"
          >
            <MicOff class="w-3 h-3" />
            Stop
          </button>
        {/if}
      </div>
    </div>

    <!-- Score breakdown -->
    {#if session.questions.length > 0}
      <div class="rounded-xl border border-border bg-card p-4">
        <h2 class="text-sm font-semibold mb-3">Score by Question</h2>
        <div class="flex items-end gap-2 h-16">
          {#each session.questions as q, i}
            <div class="flex-1 flex flex-col items-center gap-1">
              <div
                class="w-full rounded-sm {q.score !== null
                  ? q.score >= 80 ? 'bg-green-400' : q.score >= 60 ? 'bg-yellow-400' : 'bg-red-400'
                  : 'bg-muted'}"
                style="height: {q.score !== null ? Math.max(4, (q.score / 100) * 44) : 4}px"
              ></div>
              <span class="text-[9px] text-muted-foreground">Q{i+1}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Sentence drill overlay -->
    {#if drillSentence}
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onclick={() => drillSentence = null}>
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-md p-6 space-y-4" onclick={(e) => e.stopPropagation()}>
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold">Sentence Drill</h3>
            <button onclick={() => drillSentence = null} class="text-muted-foreground hover:text-foreground">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="bg-muted/50 rounded-lg p-3 text-sm leading-relaxed">{drillSentence}</div>
          <div class="flex gap-2">
            <button
              onclick={() => drillSentence && playDrill(drillSentence)}
              disabled={drillPlaying}
              class="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors disabled:opacity-50"
            >
              <Volume2 class="w-4 h-4" />
              {drillPlaying ? 'Playing…' : 'Listen'}
            </button>
            <a
              href="/interview?drill=1"
              class="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Mic class="w-4 h-4" />
              Practice it
            </a>
          </div>
          <p class="text-[11px] text-muted-foreground text-center">Click "Listen" to hear it slowly, then go to Interview Practice to record yourself saying it.</p>
        </div>
      </div>
    {/if}

    <!-- Q&A accordion -->
    <div class="space-y-3">
      <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Questions & Answers</h2>
      {#each session.questions as q, i}
        <div class="rounded-xl border {expandedIdx === i ? 'border-primary/30' : 'border-border'} bg-card overflow-hidden transition-colors">
          <!-- Header row (always visible) -->
          <button
            onclick={() => expandedIdx = expandedIdx === i ? null : i}
            class="w-full flex items-center gap-3 p-4 text-left hover:bg-accent/30 transition-colors"
          >
            <!-- Score circle -->
            <div class="w-9 h-9 rounded-full border flex items-center justify-center shrink-0
              {q.score !== null
                ? q.score >= 80 ? 'border-green-400 bg-green-50 dark:bg-green-950/30' : q.score >= 60 ? 'border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30' : 'border-red-400 bg-red-50 dark:bg-red-950/30'
                : 'border-border bg-muted/30'}">
              {#if q.score !== null}
                <span class="text-xs font-bold {scoreColor(q.score)}">{q.score}</span>
              {:else}
                <Circle class="w-3.5 h-3.5 text-muted-foreground/40" />
              {/if}
            </div>

            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium leading-snug truncate">{q.question_text}</p>
              <p class="text-[10px] text-muted-foreground mt-0.5">
                Q{i+1}
                {#if q.user_answer}· answered{/if}
                {#if q.grammar_errors?.length} · {q.grammar_errors.length} grammar note{q.grammar_errors.length !== 1 ? 's' : ''}{/if}
              </p>
            </div>

            <ChevronDown class="w-4 h-4 text-muted-foreground shrink-0 transition-transform {expandedIdx === i ? 'rotate-180' : ''}" />
          </button>

          <!-- Expanded content -->
          {#if expandedIdx === i}
            <div class="border-t border-border/50 p-4 space-y-4">

              <!-- Question full text -->
              <div class="space-y-1.5">
                <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Question</p>
                <p class="text-sm leading-relaxed">{q.question_text}</p>
                <button
                  onclick={() => q.model_answer && playAI(q, i)}
                  disabled={!!playingKey}
                  class="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary disabled:opacity-50 transition-colors mt-1"
                >
                  <Volume2 class="w-3.5 h-3.5" />
                  {playingKey === `ai-${i}` ? 'Playing…' : 'Hear question (TTS)'}
                </button>
              </div>

              <!-- AI model answer -->
              {#if q.model_answer}
                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Model Answer</p>
                    <div class="flex items-center gap-2">
                      <button
                        onclick={() => playAI(q, i)}
                        disabled={!!playingKey}
                        class="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border text-xs font-medium hover:bg-accent transition-colors disabled:opacity-50"
                      >
                        <Play class="w-3 h-3" />
                        {playingKey === `ai-${i}` ? 'Playing…' : 'Listen'}
                      </button>
                    </div>
                  </div>
                  <div class="bg-muted/40 rounded-lg p-3 text-sm leading-relaxed">
                    {#each splitSentences(q.model_answer) as sentence}
                      <span
                        class="inline cursor-pointer hover:bg-primary/10 hover:text-primary rounded px-0.5 transition-colors"
                        title="Click to drill this sentence"
                        onclick={() => drillSentence = sentence}
                      >{sentence} </span>
                    {/each}
                  </div>
                  <p class="text-[10px] text-muted-foreground">💡 Click any sentence to open the drill panel</p>
                </div>
              {/if}

              <!-- User answer -->
              {#if q.user_answer}
                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Your Answer</p>
                    <button
                      onclick={() => playUserRec(i)}
                      disabled={!!playingKey}
                      class="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border text-xs font-medium hover:bg-accent transition-colors disabled:opacity-50"
                    >
                      <Mic class="w-3 h-3" />
                      {playingKey === `user-${i}` ? 'Playing…' : 'Play recording'}
                    </button>
                  </div>
                  <div class="bg-primary/5 border border-primary/20 rounded-lg p-3 text-sm leading-relaxed">{q.user_answer}</div>
                </div>
              {:else}
                <p class="text-xs text-muted-foreground italic">No answer recorded for this question.</p>
              {/if}

              <!-- Evaluation -->
              {#if q.score !== null}
                <div class="rounded-lg border {scoreBg(q.score)} p-3 space-y-3">
                  <div class="flex items-center justify-between">
                    <p class="text-xs font-bold uppercase tracking-wide {scoreColor(q.score)}">Score: {q.score}/100</p>
                  </div>
                  {#if q.feedback}
                    <p class="text-sm">{q.feedback}</p>
                  {/if}
                  {#if q.strengths?.length}
                    <div class="space-y-1">
                      <p class="text-xs font-semibold text-green-700 dark:text-green-400">Strengths</p>
                      {#each q.strengths as s}
                        <p class="text-xs text-muted-foreground flex items-start gap-1.5"><CheckCircle2 class="w-3 h-3 mt-0.5 text-green-500 shrink-0" />{s}</p>
                      {/each}
                    </div>
                  {/if}
                  {#if q.improvements?.length}
                    <div class="space-y-1">
                      <p class="text-xs font-semibold text-yellow-700 dark:text-yellow-400">To improve</p>
                      {#each q.improvements as imp}
                        <p class="text-xs text-muted-foreground flex items-start gap-1.5"><Circle class="w-3 h-3 mt-0.5 text-yellow-500 shrink-0" />{imp}</p>
                      {/each}
                    </div>
                  {/if}
                  {#if q.grammar_errors?.length}
                    <div class="space-y-1">
                      <p class="text-xs font-semibold text-red-600 dark:text-red-400">Grammar / Language notes</p>
                      {#each q.grammar_errors as err}
                        <p class="text-xs text-muted-foreground font-mono bg-background rounded px-1.5 py-0.5">{err}</p>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/if}

              <!-- Improved answer with sentence drill -->
              {#if q.improved_answer}
                <div class="space-y-2">
                  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Improved Answer</p>
                  <div class="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-3 text-sm leading-relaxed">
                    {#each splitSentences(q.improved_answer) as sentence}
                      <span
                        class="inline cursor-pointer hover:bg-emerald-200/50 dark:hover:bg-emerald-700/30 rounded px-0.5 transition-colors"
                        title="Click to drill this sentence"
                        onclick={() => drillSentence = sentence}
                      >{sentence} </span>
                    {/each}
                  </div>
                  <p class="text-[10px] text-muted-foreground">💡 Click any sentence in the improved answer to drill it</p>
                </div>
              {/if}

            </div>
          {/if}
        </div>
      {/each}
    </div>

    <!-- Repeat session link -->
    <div class="flex items-center gap-3 pt-2">
      <a
        href="/interview"
        class="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors"
      >
        <RefreshCw class="w-4 h-4" />
        Practice Again
      </a>
      <a href="/interview/sessions" class="text-sm text-muted-foreground hover:text-foreground transition-colors">
        ← All sessions
      </a>
    </div>
  {/if}
</div>
