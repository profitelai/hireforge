<script lang="ts">
	import { activeProfile } from '$lib/activeProfile.svelte';
	import { listApplications, getCvHistory, getCoverLetterHistory, listInterviewSessions } from '$lib/api';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { profiles } from '$lib/profiles.svelte';
	import {
		ArrowRight, BarChart3, Briefcase, CheckCircle2, FileText,
		Globe, Lock, Mail, Mic, Sparkles, Star, TrendingUp, User,
	} from '@lucide/svelte';

	let { data } = $props();
	const isOnboarded = $derived(data.isOnboarded);
	const profile = $derived(activeProfile.current);
	const activeProfileItem = $derived(profiles.all.find(p => p.id === activeProfile.current?.id));
	const isActiveEmpty = $derived(activeProfileItem != null && !activeProfileItem.has_content);

	// ── Stats state ──────────────────────────────────────────────────────────
	interface Stats {
		applications: number;
		interviewing: number;
		offers: number;
		cvsGenerated: number;
		clsGenerated: number;
		interviewTotal: number;
		interviewEN: number;
		interviewFR: number;
		avgScoreEN: number | null;
		avgScoreFR: number | null;
		avgScoreAll: number | null;
		bestScore: number | null;
	}

	let stats = $state<Stats | null>(null);
	let statsLoading = $state(true);

	$effect(() => {
		const ap = activeProfile.current;
		statsLoading = true;
		stats = null;

		const profileId = ap?.id;

		Promise.all([
			listApplications({ profile_id: profileId, limit: 1 }).catch(() => ({ items: [], total: 0 })),
			listApplications({ profile_id: profileId, status: 'interviewing', limit: 1 }).catch(() => ({ items: [], total: 0 })),
			listApplications({ profile_id: profileId, status: 'offer', limit: 1 }).catch(() => ({ items: [], total: 0 })),
			getCvHistory({ profile_id: profileId, limit: 1 }).catch(() => ({ items: [], total: 0 })),
			getCoverLetterHistory({ profile_id: profileId, limit: 1 }).catch(() => ({ items: [], total: 0 })),
			listInterviewSessions({ profile_id: profileId, limit: 200 }).catch(() => ({ items: [], total: 0 })),
		]).then(([apps, interviewing, offers, cvs, cls, sessions]) => {
			const allSessions = sessions.items ?? [];
			const enSessions = allSessions.filter(s => s.language === 'EN' && s.overall_score !== null);
			const frSessions = allSessions.filter(s => s.language === 'FR' && s.overall_score !== null);
			const allScored = allSessions.filter(s => s.overall_score !== null);

			const avg = (arr: typeof allScored) =>
				arr.length ? Math.round(arr.reduce((a, s) => a + (s.overall_score ?? 0), 0) / arr.length) : null;
			const best = (arr: typeof allScored) =>
				arr.length ? Math.max(...arr.map(s => s.overall_score ?? 0)) : null;

			stats = {
				applications: apps.total,
				interviewing: interviewing.total,
				offers: offers.total,
				cvsGenerated: cvs.total,
				clsGenerated: cls.total,
				interviewTotal: allSessions.length,
				interviewEN: allSessions.filter(s => s.language === 'EN').length,
				interviewFR: allSessions.filter(s => s.language === 'FR').length,
				avgScoreEN: avg(enSessions),
				avgScoreFR: avg(frSessions),
				avgScoreAll: avg(allScored),
				bestScore: best(allScored),
			};
		}).finally(() => { statsLoading = false; });
	});

	function scoreColor(score: number | null) {
		if (!score) return 'text-muted-foreground';
		if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
		if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
		return 'text-red-500 dark:text-red-400';
	}

	const cards = [
		{ href: '/profile',      title: 'Profile Setup',       description: 'Manage your personal info, experience, and skills.',              action: 'Edit Profile',    icon: User,      step: 1, color: 'text-blue-500',   bg: 'bg-blue-500/10'   },
		{ href: '/import',       title: 'Import CV',           description: 'Quickly populate your profile from an existing PDF or DOCX.',    action: 'Import Data',     icon: FileText,  step: 2, color: 'text-purple-500', bg: 'bg-purple-500/10' },
		{ href: '/generate',     title: 'Generate CV',         description: 'Get an ATS-optimized CV with AI-enhanced bullet points.',        action: 'Generate ATS CV', icon: Sparkles,  step: 3, color: 'text-amber-500',  bg: 'bg-amber-500/10'  },
		{ href: '/cover-letter', title: 'Cover Letter',        description: 'Write a tailored cover letter from a job description.',          action: 'Write Letter',    icon: Mail,      step: 4, color: 'text-emerald-500',bg: 'bg-emerald-500/10'},
		{ href: '/smart-apply',  title: 'Smart Apply',         description: 'Paste a job URL and generate tailored CV + cover letter.',       action: 'Apply Now',       icon: Briefcase, step: 5, color: 'text-cyan-500',   bg: 'bg-cyan-500/10'   },
		{ href: '/tracker',      title: 'Application Tracker', description: 'Track your job applications across different stages.',           action: 'Track Jobs',      icon: Briefcase, step: 6, color: 'text-rose-500',   bg: 'bg-rose-500/10'   },
		{ href: '/usage',        title: 'LLM Usage',           description: 'View AI usage statistics and logs.',                            action: 'View Stats',      icon: BarChart3, step: 7, color: 'text-orange-500', bg: 'bg-orange-500/10' },
	];

	const displayedCards = $derived(
		cards
			.filter(card => !(isOnboarded && card.title === 'Import CV'))
			.map((card, index) => ({ ...card, displayStep: index + 1 }))
	);
</script>

<svelte:head>
  <title>HireForge — AI Resume Builder with ATS Score & Interview Prep</title>
  <meta name="description" content="Build ATS-optimized resumes, write tailored cover letters, and practice job interviews with AI. HireForge is free, open-source, and self-hosted — your data stays private." />
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "HireForge",
    "applicationCategory": "BusinessApplication",
    "operatingSystem": "Web",
    "description": "AI-powered resume builder with ATS scoring, cover letter generator, interview preparation, and job application tracker. Open-source and self-hosted.",
    "url": "https://jobs.bizlocal.ca/",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "USD"
    },
    "featureList": [
      "ATS-Optimized Resume Builder",
      "AI Cover Letter Generator",
      "Interview Practice with AI Scoring",
      "Job Application Tracker",
      "Smart Apply — paste a job URL and get tailored CV + cover letter"
    ]
  }
  <\/script>
<\/svelte:head>

<div class="flex flex-col gap-6">
	<!-- Hero -->
	<div class="relative overflow-hidden rounded-3xl bg-linear-to-br from-primary/10 via-background to-secondary/10 p-8 sm:p-10 border shadow-sm flex-shrink-0">
		<div class="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-8">
			<div class="max-w-2xl text-left">
				<div class="inline-flex items-center rounded-full border bg-background/50 px-3 py-1 text-xs font-semibold mb-6 backdrop-blur-sm uppercase tracking-widest text-muted-foreground/80">
					<Sparkles class="mr-2 h-3.5 w-3.5 text-primary" />
					AI Application Toolkit
				</div>
				<h1 class="text-3xl sm:text-4xl md:text-5xl font-black tracking-tight mb-4 text-foreground leading-[1.1]">
					{#if isOnboarded === undefined}
						<Skeleton class="h-12 w-80 rounded-xl" />
					{:else if isOnboarded && (profile?.name || profile?.label)}
						Ready for the next role, <span class="text-transparent bg-clip-text bg-linear-to-r from-primary to-purple-500">{profile.name || profile.label}</span>?
					{:else}
						Welcome to <span class="text-transparent bg-clip-text bg-linear-to-r from-primary to-purple-500">HireForge</span>
					{/if}
				</h1>
				<p class="text-base md:text-lg text-muted-foreground leading-relaxed max-w-xl">
					{#if isOnboarded}
						Your profile is ready. Use our AI tools to tailor your application for any job in seconds.
					{:else}
						Your self-hosted, local-first CV and cover letter generator. Keep your data private.
					{/if}
				</p>
			</div>
			<div class="flex flex-wrap gap-4">
				{#if !isOnboarded}
					<Button href="/onboarding" size="lg" class="rounded-full shadow-lg px-8 py-6 text-base font-bold">
						Get Started <ArrowRight class="ml-2 h-5 w-5" />
					</Button>
				{:else}
					<Button href="/generate" size="lg" class="rounded-full shadow-lg px-8 py-6 text-base font-bold">
						<Sparkles class="mr-2 h-5 w-5" /> Generate CV
					</Button>
				{/if}
			</div>
		</div>
		<div class="absolute -right-20 -top-20 h-80 w-80 rounded-full bg-primary/15 blur-[100px] pointer-events-none"></div>
		<div class="absolute -bottom-32 left-1/2 h-60 w-96 -translate-x-1/2 rounded-full bg-purple-500/10 blur-[100px] pointer-events-none"></div>
	</div>

	<!-- Stats Dashboard -->
	{#if isOnboarded}
		<div class="space-y-3">
			<h2 class="text-base font-semibold tracking-tight flex items-center gap-2">
				<TrendingUp class="w-4 h-4 text-primary" />
				Your Progress
			</h2>

			<!-- Row 1: Applications & Docs -->
			<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
				<!-- Jobs Applied -->
				<a href="/tracker" class="group rounded-xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-accent/40 transition-all">
					<div class="flex items-center gap-2 mb-2">
						<div class="p-1.5 rounded-md bg-rose-500/10">
							<Briefcase class="w-3.5 h-3.5 text-rose-500" />
						</div>
						<span class="text-xs text-muted-foreground font-medium">Applied</span>
					</div>
					{#if statsLoading}
						<Skeleton class="h-8 w-12 rounded-md" />
					{:else}
						<p class="text-3xl font-black text-foreground leading-none">{stats?.applications ?? 0}</p>
						{#if (stats?.interviewing ?? 0) > 0 || (stats?.offers ?? 0) > 0}
							<p class="text-[10px] text-muted-foreground mt-1">
								{#if (stats?.offers ?? 0) > 0}<span class="text-emerald-500 font-semibold">{stats?.offers} offer{(stats?.offers ?? 0) !== 1 ? 's' : ''}</span>{/if}
								{#if (stats?.interviewing ?? 0) > 0}{(stats?.offers ?? 0) > 0 ? ' · ' : ''}<span class="text-blue-500 font-semibold">{stats?.interviewing} interviewing</span>{/if}
							</p>
						{:else}
							<p class="text-[10px] text-muted-foreground mt-1">jobs tracked</p>
						{/if}
					{/if}
				</a>

				<!-- CVs Generated -->
				<a href="/history" class="group rounded-xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-accent/40 transition-all">
					<div class="flex items-center gap-2 mb-2">
						<div class="p-1.5 rounded-md bg-amber-500/10">
							<FileText class="w-3.5 h-3.5 text-amber-500" />
						</div>
						<span class="text-xs text-muted-foreground font-medium">Resumes</span>
					</div>
					{#if statsLoading}
						<Skeleton class="h-8 w-12 rounded-md" />
					{:else}
						<p class="text-3xl font-black text-foreground leading-none">{stats?.cvsGenerated ?? 0}</p>
						<p class="text-[10px] text-muted-foreground mt-1">CVs generated</p>
					{/if}
				</a>

				<!-- Cover Letters -->
				<a href="/history" class="group rounded-xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-accent/40 transition-all">
					<div class="flex items-center gap-2 mb-2">
						<div class="p-1.5 rounded-md bg-emerald-500/10">
							<Mail class="w-3.5 h-3.5 text-emerald-500" />
						</div>
						<span class="text-xs text-muted-foreground font-medium">Cover Letters</span>
					</div>
					{#if statsLoading}
						<Skeleton class="h-8 w-12 rounded-md" />
					{:else}
						<p class="text-3xl font-black text-foreground leading-none">{stats?.clsGenerated ?? 0}</p>
						<p class="text-[10px] text-muted-foreground mt-1">letters generated</p>
					{/if}
				</a>

				<!-- Best Interview Score -->
				<a href="/interview/sessions" class="group rounded-xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-accent/40 transition-all">
					<div class="flex items-center gap-2 mb-2">
						<div class="p-1.5 rounded-md bg-yellow-500/10">
							<Star class="w-3.5 h-3.5 text-yellow-500" />
						</div>
						<span class="text-xs text-muted-foreground font-medium">Best Score</span>
					</div>
					{#if statsLoading}
						<Skeleton class="h-8 w-16 rounded-md" />
					{:else if stats?.bestScore}
						<p class="text-3xl font-black leading-none {scoreColor(stats.bestScore)}">{stats.bestScore}<span class="text-sm font-semibold text-muted-foreground">/100</span></p>
						<p class="text-[10px] text-muted-foreground mt-1">interview practice</p>
					{:else}
						<p class="text-3xl font-black text-muted-foreground/40 leading-none">—</p>
						<p class="text-[10px] text-muted-foreground mt-1">no scored sessions</p>
					{/if}
				</a>
			</div>

			<!-- Row 2: Interview breakdown -->
			<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
				<!-- Total practice sessions -->
				<a href="/interview/sessions" class="group rounded-xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-accent/40 transition-all flex items-center gap-4">
					<div class="p-2.5 rounded-xl bg-primary/10 shrink-0">
						<Mic class="w-5 h-5 text-primary" />
					</div>
					<div>
						{#if statsLoading}
							<Skeleton class="h-7 w-16 rounded-md mb-1" />
							<Skeleton class="h-3 w-24 rounded" />
						{:else}
							<p class="text-2xl font-black text-foreground leading-none">{stats?.interviewTotal ?? 0}</p>
							<p class="text-xs text-muted-foreground mt-0.5">interview sessions total</p>
						{/if}
					</div>
				</a>

				<!-- English practice -->
				<a href="/interview/sessions" class="group rounded-xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-accent/40 transition-all">
					<div class="flex items-center justify-between mb-2">
						<div class="flex items-center gap-2">
							<span class="text-base">🇬🇧</span>
							<span class="text-xs font-semibold text-muted-foreground">English Practice</span>
						</div>
						{#if !statsLoading && stats?.avgScoreEN}
							<span class="text-xs font-bold px-2 py-0.5 rounded-full {stats.avgScoreEN >= 80 ? 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400' : stats.avgScoreEN >= 60 ? 'bg-yellow-100 dark:bg-yellow-950/40 text-yellow-700 dark:text-yellow-400' : 'bg-red-100 dark:bg-red-950/40 text-red-600 dark:text-red-400'}">
								avg {stats.avgScoreEN}/100
							</span>
						{/if}
					</div>
					{#if statsLoading}
						<Skeleton class="h-7 w-10 rounded-md" />
					{:else}
						<div class="flex items-end gap-3">
							<p class="text-2xl font-black text-foreground leading-none">{stats?.interviewEN ?? 0}</p>
							<p class="text-xs text-muted-foreground mb-0.5">session{(stats?.interviewEN ?? 0) !== 1 ? 's' : ''}</p>
						</div>
						{#if !stats?.avgScoreEN}
							<p class="text-[10px] text-muted-foreground mt-1">no scored sessions yet</p>
						{/if}
					{/if}
				</a>

				<!-- French practice -->
				<a href="/interview/sessions" class="group rounded-xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-accent/40 transition-all">
					<div class="flex items-center justify-between mb-2">
						<div class="flex items-center gap-2">
							<span class="text-base">🇫🇷</span>
							<span class="text-xs font-semibold text-muted-foreground">French Practice</span>
						</div>
						{#if !statsLoading && stats?.avgScoreFR}
							<span class="text-xs font-bold px-2 py-0.5 rounded-full {stats.avgScoreFR >= 80 ? 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400' : stats.avgScoreFR >= 60 ? 'bg-yellow-100 dark:bg-yellow-950/40 text-yellow-700 dark:text-yellow-400' : 'bg-red-100 dark:bg-red-950/40 text-red-600 dark:text-red-400'}">
								avg {stats.avgScoreFR}/100
							</span>
						{/if}
					</div>
					{#if statsLoading}
						<Skeleton class="h-7 w-10 rounded-md" />
					{:else}
						<div class="flex items-end gap-3">
							<p class="text-2xl font-black text-foreground leading-none">{stats?.interviewFR ?? 0}</p>
							<p class="text-xs text-muted-foreground mb-0.5">session{(stats?.interviewFR ?? 0) !== 1 ? 's' : ''}</p>
						</div>
						{#if !stats?.avgScoreFR}
							<p class="text-[10px] text-muted-foreground mt-1">no scored sessions yet</p>
						{/if}
					{/if}
				</a>
			</div>
		</div>
	{/if}

	<!-- Quick Navigation -->
	<div class="flex flex-col">
		<h2 class="text-base font-semibold tracking-tight mb-3 flex items-center gap-2 flex-shrink-0">
			<ArrowRight class="w-4 h-4 text-primary" />
			Quick Navigation
		</h2>
		<div class="rounded-xl border border-border/60 overflow-hidden bg-card/20">
			{#each displayedCards as card, i}
				{@const isRestricted = !isOnboarded && card.step > 2}
				<a
					href={isRestricted ? undefined : card.href}
					class="flex items-center gap-4 px-4 py-3.5 group transition-colors
						   {isRestricted ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:bg-accent/60'}
						   {i < displayedCards.length - 1 ? 'border-b border-border/40' : ''}"
				>
					<div class="flex items-center justify-center w-9 h-9 rounded-lg {card.bg} {card.color} shrink-0 transition-transform duration-200 group-hover:scale-105">
						<card.icon class="w-4 h-4" />
					</div>
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-1.5">
							<span class="text-sm font-semibold group-hover:text-primary transition-colors">{card.title}</span>
							{#if isRestricted}
								<Lock class="w-3 h-3 text-muted-foreground shrink-0" />
							{/if}
							{#if isOnboarded && isActiveEmpty && (card.href === '/generate' || card.href === '/cover-letter')}
								<span class="text-[10px] text-yellow-500 font-medium">⚠ Empty</span>
							{/if}
						</div>
						<p class="text-xs text-muted-foreground truncate">
							{isRestricted ? 'Complete setup first to unlock.' : card.description}
						</p>
					</div>
					{#if !isRestricted}
						<ArrowRight class="w-4 h-4 text-muted-foreground/30 group-hover:text-primary group-hover:translate-x-0.5 transition-all shrink-0" />
					{/if}
				</a>
			{/each}
		</div>
	</div>
</div>
