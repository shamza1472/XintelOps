// XIntelOps Intelligence Engine — Supabase Edge Function
// Runs every 3 hours (PKT: 00:00 / 03:00 / 06:00 / 09:00 / 12:00 / 15:00 / 18:00 / 21:00)
// Pipeline: Source Fetch → Verification → Analysis → Content Strategy → Journalist → Supabase → Resend Email

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
const RESEND_API_URL = 'https://api.resend.com/emails'
const RECIPIENT_EMAIL = 'hmz1472@gmail.com'

// ─── Journalist Roster ─────────────────────────────────────────────────────

const JOURNALIST_ROSTER: Record<number, { category: string; focus: string; journalists: Array<{ name: string; handle: string; outlet: string }> }> = {
  0: { // Sunday — Category A (Global / Foreign Policy)
    category: 'A', focus: 'Global / Foreign Policy',
    journalists: [
      { name: 'Robin Wright', handle: 'robinwrightdc', outlet: 'New Yorker / Wilson Center' },
      { name: 'James Stavridis', handle: 'stavridisj', outlet: 'Bloomberg / Tufts' },
      { name: 'Michael Hirsh', handle: 'michaelphirsh', outlet: 'Politico' },
      { name: 'Ryan Hass', handle: 'Ryan_Hass', outlet: 'Brookings' },
      { name: 'Elise Labott', handle: 'eliselabott', outlet: 'CNN' },
      { name: 'Farida Rustamova', handle: 'frutmn', outlet: 'Independent Russia analyst' },
    ]
  },
  1: { // Monday — Category A (Global / Foreign Policy)
    category: 'A', focus: 'Global / Foreign Policy',
    journalists: [
      { name: 'Robin Wright', handle: 'robinwrightdc', outlet: 'New Yorker / Wilson Center' },
      { name: 'James Stavridis', handle: 'stavridisj', outlet: 'Bloomberg / Tufts' },
      { name: 'Michael Hirsh', handle: 'michaelphirsh', outlet: 'Politico' },
      { name: 'Ryan Hass', handle: 'Ryan_Hass', outlet: 'Brookings' },
      { name: 'Elise Labott', handle: 'eliselabott', outlet: 'CNN' },
      { name: 'Farida Rustamova', handle: 'frutmn', outlet: 'Independent Russia analyst' },
    ]
  },
  2: { // Tuesday — Category B (Middle East & Gulf)
    category: 'B', focus: 'Middle East & Gulf',
    journalists: [
      { name: 'Hassan Hassan', handle: 'hxhassan', outlet: 'Newlines Magazine' },
      { name: 'Borzou Daragahi', handle: 'borzou', outlet: 'The Independent' },
      { name: 'Vivian Nereim', handle: 'vnereim', outlet: 'Bloomberg' },
      { name: 'Anchal Vohra', handle: 'anchalvohra', outlet: 'Foreign Policy / Al Jazeera' },
      { name: 'Bilal Saab', handle: 'BilalYSaab', outlet: 'MEI' },
      { name: 'Riad Kahwaji', handle: 'riiadkahwaji', outlet: 'INEGMA' },
    ]
  },
  3: { // Wednesday — Category C (Defense & Military Affairs)
    category: 'C', focus: 'Defense & Military Affairs',
    journalists: [
      { name: 'Thomas Gibbons-Neff', handle: 'tgibbonsneff', outlet: 'New York Times' },
      { name: 'Jack Watling', handle: 'jackwatling1', outlet: 'RUSI' },
      { name: 'Mick Ryan', handle: 'WarInTheFuture', outlet: 'Fmr Australian Army MG' },
      { name: 'Shashank Joshi', handle: 'shashj', outlet: 'The Economist' },
      { name: 'Alex Gatopoulos', handle: 'alexgatopoulos', outlet: 'Al Jazeera' },
      { name: 'David Axe', handle: 'daxe', outlet: 'Forbes / War Is Boring' },
    ]
  },
  4: { // Thursday — Category D (Indo-Pacific & East Asia)
    category: 'D', focus: 'Indo-Pacific & East Asia',
    journalists: [
      { name: 'Bonny Lin', handle: 'BonnyLin2', outlet: 'CSIS' },
      { name: 'Oriana Skylar Mastro', handle: 'osmastro', outlet: 'Stanford / AEI' },
      { name: 'Blake Herzinger', handle: 'BDHerzinger', outlet: 'FDD' },
      { name: 'Raymond Kuo', handle: 'raymond_kuo', outlet: 'RAND' },
      { name: 'Minnie Chan', handle: 'MinnieChanSCMP', outlet: 'SCMP' },
      { name: 'Ankit Panda', handle: 'nktpanda', outlet: 'Carnegie / The Signal' },
    ]
  },
  5: { // Friday — Category E (Eastern Europe / Ukraine-Russia)
    category: 'E', focus: 'Eastern Europe / Ukraine-Russia',
    journalists: [
      { name: 'Michael Kofman', handle: 'KofmanMichael', outlet: 'Carnegie Endowment' },
      { name: 'Rob Lee', handle: 'RALee85', outlet: 'FPRI' },
      { name: 'Dara Massicot', handle: 'daramassicot', outlet: 'Carnegie Endowment' },
      { name: 'Konrad Muzyka', handle: 'KonradMuzyka', outlet: 'Rochan Consulting' },
      { name: 'Illia Ponomarenko', handle: 'IAPonomarenko', outlet: 'Kyiv Independent' },
      { name: 'Anastasiia Lapatina', handle: 'lapatina_', outlet: 'Kyiv Independent' },
    ]
  },
  6: { // Saturday — Category F (Geo-Economics & Sanctions)
    category: 'F', focus: 'Geo-Economics & Sanctions',
    journalists: [
      { name: "Brian O'Toole", handle: 'brianoftoole', outlet: 'Atlantic Council' },
      { name: 'Edward Fishman', handle: 'edwardfishman', outlet: 'Columbia / Author (Chokepoints)' },
      { name: 'Rachel Ziemba', handle: 'RachelZiemba', outlet: 'CNAS' },
      { name: 'Emily Kilcrease', handle: 'ekilcrease', outlet: 'CNAS' },
      { name: 'Tom Keatinge', handle: 'TomKeatinge1', outlet: 'RUSI' },
      { name: 'Agathe Demarais', handle: 'AgatheDemarais', outlet: 'ECFR' },
    ]
  },
}

// ─── Source Fetching ────────────────────────────────────────────────────────

// STEP 1A — Direct RSS/page feeds (Tier 0 + Tier 1 + Government)
const DIRECT_SOURCES = [
  // Tier 0 — Breaking / Real-Time
  { url: 'https://feeds.reuters.com/reuters/topNews', name: 'Reuters' },
  { url: 'https://feeds.reuters.com/reuters/worldNews', name: 'Reuters World' },
  { url: 'https://apnews.com/index.rss', name: 'AP News' },
  { url: 'https://feeds.bbci.co.uk/news/world/rss.xml', name: 'BBC World' },
  { url: 'https://www.aljazeera.com/xml/rss/all.xml', name: 'Al Jazeera' },
  { url: 'https://tass.com/rss/v2.xml', name: 'TASS' },
  { url: 'https://en.irna.ir/rss', name: 'IRNA' },
  // Tier 1 — Government / Intergovernmental
  { url: 'https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10', name: 'DoD News' },
  { url: 'https://www.nato.int/cps/en/natohq/press_releases.htm', name: 'NATO Press' },
  { url: 'https://news.un.org/feed/subscribe/en/news/all/rss.xml', name: 'UN News' },
  { url: 'https://www.consilium.europa.eu/en/press/press-releases/', name: 'EU Council' },
  { url: 'https://ofac.treasury.gov/recent-actions', name: 'OFAC' },
  // Tier 1 — Think Tanks
  { url: 'https://www.crisisgroup.org/latest-updates', name: 'Crisis Group' },
  { url: 'https://www.csis.org/analysis', name: 'CSIS' },
  { url: 'https://carnegieendowment.org/research', name: 'Carnegie' },
  { url: 'https://www.atlanticcouncil.org/', name: 'Atlantic Council' },
  { url: 'https://www.iiss.org/en/research/', name: 'IISS' },
  { url: 'https://www.rand.org/pubs/research_reports.html', name: 'RAND' },
  { url: 'https://www.brookings.edu/topics/defense-security/', name: 'Brookings' },
  { url: 'https://www.sipri.org/news', name: 'SIPRI' },
  { url: 'https://www.chathamhouse.org/publications', name: 'Chatham House' },
  { url: 'https://mei.edu/publications', name: 'MEI' },
]

// STEP 1B — Google News RSS with site: operators (replicates WebSearch allowed_domains — FREE, no API key)
const GOOGLE_NEWS_QUERIES = [
  // Query A — Tier 0 breaking: military/conflict/strikes
  { url: 'https://news.google.com/rss/search?q=(site:reuters.com+OR+site:apnews.com+OR+site:afp.com)+military+OR+strike+OR+attack+OR+conflict&hl=en-US&gl=US&ceid=US:en', name: 'GNews: Military/Conflict [Tier0]' },
  // Query B — Tier 0 breaking: diplomacy/sanctions
  { url: 'https://news.google.com/rss/search?q=(site:reuters.com+OR+site:apnews.com+OR+site:aa.com.tr)+diplomatic+OR+ceasefire+OR+summit+OR+sanctions&hl=en-US&gl=US&ceid=US:en', name: 'GNews: Diplomacy/Sanctions [Tier0]' },
  // Query C — Tier 1 think tanks: analysis
  { url: 'https://news.google.com/rss/search?q=(site:csis.org+OR+site:carnegieendowment.org+OR+site:iiss.org+OR+site:rand.org+OR+site:atlanticcouncil.org)&hl=en-US&gl=US&ceid=US:en', name: 'GNews: Think Tanks [Tier1]' },
  // Query D — Government: official statements
  { url: 'https://news.google.com/rss/search?q=(site:defense.gov+OR+site:nato.int+OR+site:news.un.org)+statement+OR+release+OR+press&hl=en-US&gl=US&ceid=US:en', name: 'GNews: Government [Tier1]' },
  // Query E — Regional: Iran/Israel/Gulf/Ukraine/Taiwan
  { url: 'https://news.google.com/rss/search?q=(site:reuters.com+OR+site:apnews.com)+(Iran+OR+Israel+OR+Gaza+OR+Ukraine+OR+Taiwan+OR+China+OR+Red+Sea)&hl=en-US&gl=US&ceid=US:en', name: 'GNews: Active Theaters [Tier0]' },
  // Query F — Sanctions/OFAC/Economic statecraft
  { url: 'https://news.google.com/rss/search?q=(site:ofac.treasury.gov+OR+site:opensanctions.org+OR+site:atlanticcouncil.org)+sanctions+OR+SDN+OR+designation&hl=en-US&gl=US&ceid=US:en', name: 'GNews: Sanctions [Tier1]' },
]

// STEP 1C — Reddit JSON (Tier 3 — "What Most People Missed", free, no key)
const REDDIT_SOURCES = [
  { url: 'https://www.reddit.com/r/CredibleDefense.json?sort=new&limit=10', name: 'Reddit: CredibleDefense' },
  { url: 'https://www.reddit.com/r/geopolitics.json?sort=new&limit=10', name: 'Reddit: Geopolitics' },
  { url: 'https://www.reddit.com/r/worldnews.json?sort=new&limit=10', name: 'Reddit: WorldNews' },
]

async function fetchSource(source: { url: string; name: string }, maxChars = 2000): Promise<string> {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 12000)
    const response = await fetch(source.url, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'XIntelOps Intelligence Engine/2.0',
        'Accept': 'application/rss+xml, application/xml, application/json, text/html, */*',
      }
    })
    clearTimeout(timeout)
    if (!response.ok) return `[${source.name}: ${response.status}]`
    const text = await response.text()
    const clean = text
      .replace(/<!\[CDATA\[/g, '').replace(/\]\]>/g, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
      .replace(/\s+/g, ' ').trim()
      .slice(0, maxChars)
    return `[SOURCE: ${source.name}]\n${clean}`
  } catch {
    return `[${source.name}: unavailable]`
  }
}

async function fetchRedditSource(source: { url: string; name: string }): Promise<string> {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 10000)
    const response = await fetch(source.url, {
      signal: controller.signal,
      headers: { 'User-Agent': 'XIntelOps/2.0' }
    })
    clearTimeout(timeout)
    if (!response.ok) return `[${source.name}: unavailable]`
    const json = await response.json()
    const posts = json?.data?.children?.slice(0, 8) ?? []
    const titles = posts.map((p: Record<string, Record<string, string>>) =>
      `• ${p.data?.title ?? ''} (${p.data?.score ?? 0} pts)`
    ).join('\n')
    return `[SOURCE: ${source.name}]\n${titles}`
  } catch {
    return `[${source.name}: unavailable]`
  }
}

async function fetchAllSources(): Promise<string> {
  // Run all three tiers in parallel
  const [directResults, searchResults, redditResults] = await Promise.all([
    Promise.allSettled(DIRECT_SOURCES.map(s => fetchSource(s, 1500))),
    Promise.allSettled(GOOGLE_NEWS_QUERIES.map(s => fetchSource(s, 2000))),
    Promise.allSettled(REDDIT_SOURCES.map(fetchRedditSource)),
  ])

  const direct = directResults.map(r => r.status === 'fulfilled' ? r.value : '').filter(Boolean)
  const search = searchResults.map(r => r.status === 'fulfilled' ? r.value : '').filter(Boolean)
  const reddit = redditResults.map(r => r.status === 'fulfilled' ? r.value : '').filter(Boolean)

  return [
    '═══ STEP 1A — DIRECT SOURCE FEEDS (Tier 0 + Tier 1) ═══',
    direct.join('\n\n---\n\n'),
    '\n═══ STEP 1B — CURATED DOMAIN SEARCH (Google News RSS) ═══',
    search.join('\n\n---\n\n'),
    '\n═══ STEP 1C — REDDIT TIER 3 (What Most People Missed) ═══',
    reddit.join('\n\n---\n\n'),
  ].join('\n\n')
}

// ─── Pipeline Execution ─────────────────────────────────────────────────────

function getJournalistForToday(utcDate: Date): { journalist: { name: string; handle: string; outlet: string }; category: string; focus: string } {
  // PKT = UTC + 5 hours
  const pktDate = new Date(utcDate.getTime() + 5 * 60 * 60 * 1000)
  const dayOfWeek = pktDate.getUTCDay() // 0=Sun, 1=Mon ... 6=Sat
  const dayRoster = JOURNALIST_ROSTER[dayOfWeek]
  // Rotate within category using ISO week number
  const startOfYear = new Date(pktDate.getUTCFullYear(), 0, 1)
  const weekNum = Math.floor((pktDate.getTime() - startOfYear.getTime()) / (7 * 24 * 60 * 60 * 1000))
  const journalistIndex = weekNum % 6
  return {
    journalist: dayRoster.journalists[journalistIndex],
    category: dayRoster.category,
    focus: dayRoster.focus,
  }
}

function getPKTDateInfo(utcDate: Date): { dateStr: string; timeStr: string; dayName: string; isLinkedInDay: boolean } {
  const pktDate = new Date(utcDate.getTime() + 5 * 60 * 60 * 1000)
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
  const dayName = days[pktDate.getUTCDay()]
  const dateStr = pktDate.toISOString().split('T')[0]
  const hours = String(pktDate.getUTCHours()).padStart(2, '0')
  const mins = String(pktDate.getUTCMinutes()).padStart(2, '0')
  const timeStr = `${hours}:${mins} PKT`
  const isLinkedInDay = [1, 3, 5].includes(pktDate.getUTCDay()) // Mon, Wed, Fri
  return { dateStr, timeStr, dayName, isLinkedInDay }
}

async function runPipeline(sourceContent: string, utcDate: Date): Promise<Record<string, unknown>> {
  const apiKey = Deno.env.get('ANTHROPIC_API_KEY')
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY not set')

  const { journalist, category, focus } = getJournalistForToday(utcDate)
  const { dateStr, timeStr, dayName, isLinkedInDay } = getPKTDateInfo(utcDate)

  const systemPrompt = `You are the XIntelOps Intelligence Engine — an institution-grade geopolitical analyst.

You will receive live content fetched from curated news sources. Your job is to run it through the full XIntelOps pipeline and return a structured JSON package.

## PIPELINE

### STAGE 1 — VERIFICATION
Scan the source content. Identify 2–3 significant geopolitical signals from the past 24 hours.
- Only use signals from named high-trust sources (Reuters, AP, AFP, DoD, NATO, UN, think tanks)
- Discard signals older than 24 hours or with no credible sourcing
- Flag crisis signals: missiles/strikes/attacks/airspace closure/mobilization/diplomatic rupture
- For each signal: extract ONLY verified facts (no speculation, no motives inferred)
- Score: confidence (high/medium/low), misinfo_risk (low/medium/high), actionability (high/medium/low)
- Block signals where confidence=low OR misinfo_risk=high OR actionability=low

### STAGE 2 — ANALYSIS
For the top verified signal:
- If crisis_flag=true: Crisis Mode — focus on immediate operational implications, escalation ladder position, proxy indicators, regional doctrine
- If crisis_flag=false: Standard Analysis — strategic context, actors involved, implications 48h and 7d, what most analysts are missing
- Apply regional doctrine: understand the theater-specific escalation patterns and decision-making frameworks

### STAGE 3 — RED TEAM
Stress-test your analysis:
- What are the strongest counter-arguments?
- What would change if the signal is partially wrong?
- Are there alternative explanations?
- Revise until the analysis is hardened against the top 2 challenges

### STAGE 4 — CONTENT PACKAGE
Based on the analysis, produce:

**X POST**: Choose format:
- SHORT POST (under 280 chars): breaking news, single confirmed fact, urgent update
- THREAD (5–8 tweets): complex analysis, multiple verified data points, doctrinal depth
Write the complete post or thread now.

**WHAT MOST PEOPLE MISSED**: An engagement-focused insight that mainstream coverage overlooked. Format: "What most people are missing about [topic]: [2–3 sentences with the overlooked angle]". Ready to post on X.

**LINKEDIN**: Today is ${dayName}. LinkedIn posting days are Monday, Wednesday, Friday.
${isLinkedInDay ? `Today IS a LinkedIn posting day. Write a full LinkedIn post (200-350 words). Format: Flagship analysis with the full strategic picture. Professional but accessible tone.` : `Today is NOT a LinkedIn posting day. State: "Next LinkedIn post: [next Mon/Wed/Fri — calculated from ${dayName}] — [recommended type]"`}

**INTERNAL BRIEF**: 150–250 word private analytical memo. Full depth. Never published. Will be stored in Supabase for newsletter premium tier and RAG database.

**IMPLICATIONS**:
- 48h implications: What could change in the next 48 hours based on this signal
- 7-day implications: Broader strategic shift indicators to watch over the next week

### STAGE 5 — JOURNALIST ENGAGEMENT
Today's journalist: ${journalist.name} (@${journalist.handle}) — ${journalist.outlet}
Category ${category}: ${focus}

Based on today's top signal and this journalist's specialty, draft a comment that:
- Adds a verified fact, proxy indicator, or doctrinal context they likely did not include
- Is SHORT — 1–3 sentences maximum
- Positions XIntelOps as a precise, credible analytical voice
- Ends with a neutral forward-looking indicator to watch
- Never flatters, never argues, never dismisses

Note: You cannot access X.com directly. Provide the journalist's profile URL and note that the user should find their most recent relevant post.

## OUTPUT FORMAT — Return ONLY valid JSON, no markdown, no explanation:

{
  "scan_session": "SCAN-${dateStr}-${timeStr.replace(':', '').replace(' PKT', '')}",
  "date_pkt": "${dateStr}",
  "time_pkt": "${timeStr}",
  "day_of_week": "${dayName}",
  "signals_scanned": 0,
  "signals_verified": 0,
  "signals_blocked": 0,
  "crisis_detected": false,
  "top_signal": {
    "title": "",
    "source": "",
    "tier": "L0",
    "url": "",
    "summary": "",
    "region": "",
    "domain": "",
    "confidence": "HIGH",
    "crisis_flag": false,
    "verified_facts": []
  },
  "post_format": "SHORT POST",
  "x_post": "",
  "x_thread": null,
  "what_most_missed": "",
  "linkedin_today": ${isLinkedInDay},
  "linkedin_post": "",
  "internal_brief": "",
  "implications_48h": "",
  "implications_7d": "",
  "journalist": {
    "name": "${journalist.name}",
    "handle": "${journalist.handle}",
    "outlet": "${journalist.outlet}",
    "category": "${category}",
    "focus": "${focus}",
    "profile_url": "https://x.com/${journalist.handle}",
    "comment_draft": "",
    "engagement_rationale": ""
  },
  "sources_fetched": [],
  "redteam_summary": ""
}`

  const userMessage = `Today is ${dateStr} (${dayName}), ${timeStr}.

Here is the live content fetched from XIntelOps curated sources:

${sourceContent}

Run the full pipeline. Return ONLY valid JSON.`

  const response = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 4096,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
    })
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Anthropic API error ${response.status}: ${error}`)
  }

  const data = await response.json()
  const rawText = data.content?.[0]?.text || '{}'

  // Parse JSON from Claude's response (handle potential markdown wrapping)
  let jsonText = rawText.trim()
  if (jsonText.startsWith('```')) {
    jsonText = jsonText.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '')
  }

  return JSON.parse(jsonText)
}

// ─── Supabase Save ──────────────────────────────────────────────────────────

async function saveToSupabase(result: Record<string, unknown>): Promise<{ rawSignalId: number | null; outputId: number | null }> {
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
  )

  const signal = result.top_signal as Record<string, unknown>

  // 1. raw_signals
  const { data: rawSignalData, error: rsError } = await supabase
    .from('raw_signals')
    .insert({
      source_name: signal?.source ?? 'Unknown',
      layer: signal?.tier ?? 'L0',
      trust: signal?.confidence ?? 'medium',
      region: signal?.region ?? 'Global',
      domain: signal?.domain ?? 'diplomatic_signal',
      title: signal?.title ?? '',
      summary: signal?.summary ?? '',
      url: signal?.url ?? '',
      processed: true,
    })
    .select('id')
    .single()

  const rawSignalId = rsError ? null : rawSignalData?.id

  // 2. intelligence_outputs
  const { data: outputData, error: outError } = await supabase
    .from('intelligence_outputs')
    .insert({
      source_name: signal?.source ?? 'Unknown',
      region: signal?.region ?? 'Global',
      domain: signal?.domain ?? 'diplomatic_signal',
      confidence: signal?.confidence ?? 'medium',
      crisis_flag: signal?.crisis_flag ?? false,
      x_post: (result.x_post as string) || (typeof result.x_thread === 'string' ? result.x_thread.split('\n')[0].substring(0, 280) : '') || '',
      x_thread: result.x_thread ?? null,
      linkedin_post: result.linkedin_post ?? '',
      internal_brief: result.internal_brief ?? '',
      implications_48h: result.implications_48h ?? '',
      implications_7d: result.implications_7d ?? '',
      redteam_status: 'approved',
      verified_facts: Array.isArray(signal?.verified_facts)
        ? (signal.verified_facts as string[]).join('\n')
        : '',
      raw_signal_id: rawSignalId,
    })
    .select('id')
    .single()

  const outputId = outError ? null : outputData?.id

  // 3. content_schedule
  const journalist = result.journalist as Record<string, unknown>
  await supabase.from('content_schedule').insert({
    run_date: result.date_pkt,
    session_label: result.scan_session,
    morning_format: result.post_format ?? 'SHORT POST',
    morning_signal: (signal?.title as string) ?? '',
    morning_draft: (result.x_post as string) ?? '',
    midday_signal: (signal?.title as string) ?? '',
    midday_draft: (result.what_most_missed as string) ?? '',
    evening_format: 'journalist_comment',
    evening_target: `@${journalist?.handle ?? ''}`,
    evening_draft: (journalist?.comment_draft as string) ?? '',
    linkedin_post_day: result.day_of_week ?? '',
    linkedin_type: result.linkedin_today ? 'flagship_analysis' : 'not_today',
    linkedin_draft: (result.linkedin_post as string) ?? '',
    intelligence_output_id: outputId,
  })

  // 4. journalist_engagements
  await supabase.from('journalist_engagements').insert({
    run_date: result.date_pkt,
    session_label: result.scan_session,
    journalist_category: journalist?.category ?? '',
    journalist_name: journalist?.name ?? '',
    journalist_handle: journalist?.handle ?? '',
    post_url: journalist?.profile_url ?? '',
    post_summary: `Check @${journalist?.handle ?? ''} for their latest post on ${result.day_of_week}`,
    comment_draft: journalist?.comment_draft ?? '',
    engagement_rationale: journalist?.engagement_rationale ?? '',
    intelligence_output_id: outputId,
  })

  // 5. pipeline_log
  const { data: plData } = await supabase.from('pipeline_log').insert({
    session_label: result.scan_session,
    signals_scraped: result.signals_scanned ?? 0,
    signals_verified: result.signals_verified ?? 0,
    signals_approved: result.signals_verified ?? 0,
    signals_blocked: result.signals_blocked ?? 0,
    crisis_detected: result.crisis_detected ?? false,
    email_sent: false,
  }).select('id').single()

  const pipelineLogId = plData?.id ?? null

  return { rawSignalId, outputId, pipelineLogId }
}

// ─── Email via Resend ───────────────────────────────────────────────────────

function buildEmailHtml(result: Record<string, unknown>): string {
  const signal = result.top_signal as Record<string, unknown>
  const journalist = result.journalist as Record<string, unknown>
  const crisisFlag = signal?.crisis_flag ?? false
  const confidenceTag = String(signal?.confidence ?? 'MEDIUM').toUpperCase()
  const tagClass = crisisFlag ? 'tag-crisis' : confidenceTag === 'HIGH' ? 'tag-high' : 'tag-medium'

  const xContent = result.post_format === 'THREAD'
    ? (result.x_thread as string || result.x_post as string || '')
    : (result.x_post as string || '')

  const linkedinSection = result.linkedin_today
    ? `<div class="linkedin-box">${String(result.linkedin_post ?? '').replace(/\n/g, '<br>')}</div>`
    : `<div class="linkedin-box" style="color:#8a9ab0;font-style:italic">${String(result.linkedin_post ?? '')}</div>`

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body { background: #f4f6f9; font-family: -apple-system, 'Helvetica Neue', sans-serif; margin: 0; padding: 24px; }
  .wrapper { max-width: 680px; margin: 0 auto; }
  .header { background: #0a0c0f; padding: 20px 24px; border-radius: 6px 6px 0 0; display: flex; align-items: center; gap: 12px; }
  .logo-mark { background: #2a6fdb; color: white; font-weight: 900; font-size: 13px; padding: 4px 8px; border-radius: 3px; display: inline-block; letter-spacing: 0.05em; }
  .logo-text { color: #e8edf2; font-size: 13px; font-weight: 700; letter-spacing: 0.15em; }
  .scan-date { color: #4a5a6e; font-size: 11px; font-family: monospace; margin-left: auto; }
  .stats-bar { background: #13181f; padding: 10px 24px; display: flex; gap: 24px; border-bottom: 1px solid #1e2733; }
  .stat { font-family: monospace; font-size: 11px; color: #4a5a6e; }
  .stat span { color: #4da6ff; font-weight: 700; }
  .stat.crisis span { color: #e05252; }
  .body { background: #ffffff; padding: 0; border-radius: 0 0 6px 6px; overflow: hidden; }
  .section { padding: 20px 24px; border-bottom: 1px solid #f0f2f5; }
  .section:last-child { border-bottom: none; }
  .section-label { font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #8a9ab0; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .signal-meta { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .tag { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 3px; font-family: monospace; letter-spacing: 0.05em; }
  .tag-high { background: #e8f0fe; color: #2a6fdb; }
  .tag-crisis { background: #fde8e8; color: #e05252; }
  .tag-medium { background: #fef6e8; color: #b87a00; }
  .tag-domain { background: #f4f6f9; color: #4a5a6e; border: 1px solid #e0e5ed; }
  .post-box { background: #f8f9fb; border: 1px solid #e0e5ed; border-left: 3px solid #2a6fdb; border-radius: 4px; padding: 14px 16px; font-size: 13px; color: #1a2332; line-height: 1.6; white-space: pre-wrap; }
  .post-box.crisis { border-left-color: #e05252; background: #fff8f8; }
  .post-box.green { border-left-color: #22c97a; background: #f5fdf9; }
  .post-box.purple { border-left-color: #7c5cbf; background: #f8f5fd; }
  .journalist-name { font-size: 13px; font-weight: 600; color: #1a2332; margin-bottom: 2px; }
  .journalist-handle { font-size: 11px; color: #2a6fdb; font-family: monospace; margin-bottom: 10px; }
  .journalist-hint { background: #f8f9fb; border: 1px solid #e0e5ed; border-radius: 4px; padding: 10px 12px; font-size: 12px; color: #4a5a6e; margin-bottom: 10px; }
  .post-url { font-size: 11px; color: #2a6fdb; font-family: monospace; display: block; margin-bottom: 10px; }
  .brief-text { font-size: 13px; color: #2a3a4a; line-height: 1.7; }
  .implications { background: #f8f9fb; border-radius: 4px; padding: 12px 16px; margin-top: 12px; }
  .imp-label { font-size: 10px; font-weight: 700; color: #8a9ab0; letter-spacing: 0.08em; margin-bottom: 4px; }
  .imp-text { font-size: 12px; color: #2a3a4a; line-height: 1.6; }
  .footer { background: #f8f9fb; border-top: 1px solid #e0e5ed; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }
  .footer-left { font-size: 10px; color: #8a9ab0; font-family: monospace; }
  .footer-right { font-size: 10px; color: #2a6fdb; font-family: monospace; font-weight: 700; }
  .linkedin-box { background: #f0f7ff; border: 1px solid #c8ddf7; border-radius: 4px; padding: 14px 16px; font-size: 13px; color: #1a2332; line-height: 1.6; white-space: pre-wrap; }
  h4 { margin: 8px 0 4px 0; font-size: 11px; color: #8a9ab0; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }
  .signal-title { font-size: 14px; font-weight: 600; color: #1a2332; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <span class="logo-mark">XI</span>
    <span class="logo-text">XINTELOPS</span>
    <span class="scan-date">${String(result.date_pkt ?? '')} · ${String(result.time_pkt ?? '')} · Automated Scan</span>
  </div>
  <div class="stats-bar">
    <div class="stat">SCANNED <span>${result.signals_scanned ?? 0}</span></div>
    <div class="stat">VERIFIED <span>${result.signals_verified ?? 0}</span></div>
    <div class="stat">BLOCKED <span>${result.signals_blocked ?? 0}</span></div>
    <div class="stat crisis">CRISIS <span>${result.crisis_detected ? 'YES ⚠️' : 'NO'}</span></div>
    <div class="stat">SESSION <span>${String(result.scan_session ?? '').slice(-8)}</span></div>
  </div>
  <div class="body">
    <div class="section">
      <div class="section-label">📡 Post This Now — X</div>
      <div class="signal-title">${String(signal?.title ?? '')}</div>
      <div class="signal-meta">
        <span class="tag ${tagClass}">${confidenceTag}</span>
        <span class="tag tag-domain">${String(signal?.domain ?? '').replace(/_/g, ' ').toUpperCase()}</span>
        <span class="tag tag-domain">${String(signal?.region ?? '').toUpperCase()}</span>
        <span class="tag tag-domain">${String(result.post_format ?? 'POST')}</span>
      </div>
      <div class="post-box ${crisisFlag ? 'crisis' : ''}">${String(xContent).replace(/\n/g, '<br>')}</div>
    </div>
    <div class="section">
      <div class="section-label">🔍 What Most People Missed</div>
      <div class="post-box green">${String(result.what_most_missed ?? '').replace(/\n/g, '<br>')}</div>
    </div>
    <div class="section">
      <div class="section-label">💬 Journalist Comment</div>
      <div class="journalist-name">${String(journalist?.name ?? '')}</div>
      <div class="journalist-handle">@${String(journalist?.handle ?? '')} · ${String(journalist?.outlet ?? '')} · Category ${String(journalist?.category ?? '')} · ${String(result.day_of_week ?? '')}</div>
      <div class="journalist-hint">⚡ Find their latest post here: <a href="${String(journalist?.profile_url ?? '')}" class="post-url">${String(journalist?.profile_url ?? '')}</a></div>
      <h4>Your comment:</h4>
      <div class="post-box purple">${String(journalist?.comment_draft ?? '').replace(/\n/g, '<br>')}</div>
    </div>
    <div class="section">
      <div class="section-label">💼 LinkedIn</div>
      ${linkedinSection}
    </div>
    <div class="section">
      <div class="section-label">📋 Internal Brief <span style="font-weight:400;color:#c0c8d4;font-size:9px"> — NOT FOR PUBLICATION</span></div>
      <div class="brief-text">${String(result.internal_brief ?? '').replace(/\n/g, '<br>')}</div>
      <div class="implications">
        <div class="imp-label">⏱ 48-Hour Implications</div>
        <div class="imp-text">${String(result.implications_48h ?? '').replace(/\n/g, '<br>')}</div>
      </div>
      <div class="implications" style="margin-top: 8px;">
        <div class="imp-label">📅 7-Day Indicators</div>
        <div class="imp-text">${String(result.implications_7d ?? '').replace(/\n/g, '<br>')}</div>
      </div>
    </div>
  </div>
  <div class="footer">
    <div class="footer-left">✅ Saved to Supabase · ${String(result.scan_session ?? '')}</div>
    <div class="footer-right">XINTELOPS INTELLIGENCE ENGINE</div>
  </div>
</div>
</body>
</html>`
}

async function sendEmail(result: Record<string, unknown>): Promise<void> {
  const resendKey = Deno.env.get('RESEND_API_KEY')
  if (!resendKey) {
    console.warn('RESEND_API_KEY not set — skipping email')
    return
  }

  const subject = `XIntelOps Scan — ${result.date_pkt} ${result.time_pkt}${result.crisis_detected ? ' ⚠️ CRISIS DETECTED' : ''}`
  const html = buildEmailHtml(result)

  const response = await fetch(RESEND_API_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${resendKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: 'XIntelOps <xintelops@resend.dev>',
      to: [RECIPIENT_EMAIL],
      subject,
      html,
    })
  })

  if (!response.ok) {
    const err = await response.text()
    console.error('Resend error:', err)
  } else {
    console.log('Email sent successfully to', RECIPIENT_EMAIL)
  }
}

// ─── Main Handler ───────────────────────────────────────────────────────────

Deno.serve(async (req: Request) => {
  // Verify CRON_SECRET for scheduled calls (optional security layer)
  const cronSecret = Deno.env.get('CRON_SECRET')
  const authHeader = req.headers.get('x-cron-secret')
  if (cronSecret && authHeader !== cronSecret) {
    // Also allow calls with the standard Supabase auth header
    const bearerToken = req.headers.get('Authorization')?.replace('Bearer ', '')
    const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')
    if (bearerToken !== serviceKey) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
      })
    }
  }

  const utcNow = new Date()
  const { dateStr, timeStr } = getPKTDateInfo(utcNow)

  console.log(`XIntelOps Scan starting — ${dateStr} ${timeStr}`)

  try {
    // Step 1: Fetch sources
    console.log('Step 1: Fetching sources...')
    const sourceContent = await fetchAllSources()

    // Step 2: Run pipeline via Anthropic API
    console.log('Step 2: Running pipeline...')
    const result = await runPipeline(sourceContent, utcNow)

    // Step 3: Save to Supabase
    console.log('Step 3: Saving to Supabase...')
    const { outputId, pipelineLogId } = await saveToSupabase(result)

    // Step 4: Send email via Resend
    console.log('Step 4: Sending email...')
    let emailSent = false
    try {
      await sendEmail(result)
      emailSent = true
      console.log('Email sent successfully')
    } catch (emailErr) {
      console.error('Email send failed:', emailErr instanceof Error ? emailErr.message : String(emailErr))
    }

    // Step 5: Update pipeline_log with email_sent status
    if (pipelineLogId) {
      const supabase = createClient(
        Deno.env.get('SUPABASE_URL') ?? '',
        Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
      )
      await supabase.from('pipeline_log').update({ email_sent: emailSent }).eq('id', pipelineLogId)
    }

    // Step 6: Fire Make webhook
    let webhookFired = false
    try {
      const signal = result.top_signal as Record<string, unknown>
      const journalist = result.journalist as Record<string, unknown>
      const webhookPayload = {
        session_label: result.scan_session,
        date: result.date_pkt,
        time_pkt: result.time_pkt,
        crisis: result.crisis_detected ?? false,
        confidence: signal?.confidence ?? 'medium',
        region: signal?.region ?? '',
        domain: signal?.domain ?? '',
        signal_summary: signal?.title ?? '',
        x_post_short: result.x_post ?? '',
        x_thread: result.x_thread ?? '',
        what_most_people_missed: result.what_most_missed ?? '',
        journalist_name: journalist?.name ?? '',
        journalist_handle: journalist?.handle ?? '',
        journalist_outlet: journalist?.outlet ?? '',
        journalist_post_url: journalist?.profile_url ?? 'SKIPPED',
        journalist_post_summary: `Check @${journalist?.handle ?? ''} for latest post`,
        journalist_comment: journalist?.comment_draft ?? 'SKIPPED',
        linkedin_post: result.linkedin_post ?? '',
        linkedin_post_day: result.day_of_week ?? '',
        linkedin_today: result.linkedin_today ?? false,
        internal_brief: result.internal_brief ?? '',
        implications_48h: result.implications_48h ?? '',
        implications_7d: result.implications_7d ?? '',
        verified_sources: result.sources_fetched ?? [],
        supabase_output_id: outputId,
      }
      const webhookRes = await fetch('https://hook.eu2.make.com/hb1rx9y2nj1cptub820xqqhkcvnv5cr3', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(webhookPayload),
      })
      webhookFired = webhookRes.ok
      console.log('Webhook fired:', webhookRes.status)
    } catch (webhookErr) {
      console.error('Webhook failed (non-blocking):', webhookErr instanceof Error ? webhookErr.message : String(webhookErr))
    }

    console.log(`Scan complete — session: ${result.scan_session}, output_id: ${outputId}, email: ${emailSent}, webhook: ${webhookFired}`)

    return new Response(JSON.stringify({
      success: true,
      session: result.scan_session,
      output_id: outputId,
      crisis: result.crisis_detected,
      signal: (result.top_signal as Record<string, unknown>)?.title,
      webhook_fired: webhookFired,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })

  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    console.error('Scan failed:', message)

    return new Response(JSON.stringify({ success: false, error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    })
  }
})
