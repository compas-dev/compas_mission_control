<script setup>
import { computed, ref, onMounted, onBeforeUnmount, watch, nextTick } from "vue";

const data = ref(null);
const error = ref(null);

// ---- view state ------------------------------------------------------
const theme = ref("dark"); // dark | light
const mode = ref("fleet"); // fleet | ecosystem
const search = ref("");
const activeCats = ref(new Set());
const showArchived = ref(false);
const collapsed = ref(new Set());
const quick = ref(null); // null | "failing" | "dormant"
const groupBy = ref("category"); // category | tier
const sortKey = ref("stars"); // stars | activity | name

const CAT_LABEL = {
  core: "Core", fabrication: "Fabrication", timber: "Timber", geometry: "Geometry",
  structures: "Structures", fea: "FEA", viz: "Visualization", xr: "XR",
  apps: "Apps", tooling: "Tooling", template: "Templates", other: "Other",
};
const PY = ["3.9", "3.10", "3.11", "3.12", "3.13"];
const STALE_ORDER = { fresh: 0, aging: 1, stale: 2, dormant: 3, unknown: 4 };
const CAT_RANK = Object.fromEntries(
  ["core", "geometry", "structures", "fea", "fabrication", "timber", "xr", "viz", "apps", "tooling", "template", "other"].map((c, i) => [c, i])
);
const TIER_GROUP = [
  { id: "core", name: "Core" },
  { id: "foundation", name: "Foundation" },
  { id: "domain", name: "Domain extensions" },
  { id: "visualizers", name: "Visualizers" },
  { id: "apps", name: "Applications" },
  { id: "tooling", name: "Tooling" },
];
const ECO_TIERS = [
  { id: "apps", name: "Applications", sub: "end-user tools & big apps" },
  { id: "visualizers", name: "Visualizers", sub: "viewers, plotters & notebooks" },
  { id: "domain", name: "Domain extensions", sub: "discipline-specific packages" },
  { id: "foundation", name: "Foundation", sub: "geometry & data libraries" },
  { id: "core", name: "Core", sub: "the COMPAS framework" },
  { id: "tooling", name: "Tooling", sub: "shared dev infrastructure" },
];
const VALID_MODES = ["fleet", "ecosystem"];

// ---- lifecycle -------------------------------------------------------
onMounted(async () => {
  try {
    const t = localStorage.getItem("mc_theme");
    if (t) theme.value = t;
    else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) theme.value = "light";
    const g = localStorage.getItem("mc_group"); if (g) groupBy.value = g;
    const s = localStorage.getItem("mc_sort"); if (s) sortKey.value = s;
  } catch (e) {}
  applyTheme();

  const hash = location.hash.replace("#", "");
  if (VALID_MODES.includes(hash)) mode.value = hash;

  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data.json`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`data.json ${res.status}`);
    data.value = await res.json();
  } catch (e) {
    error.value = String(e);
  }

  const focus = new URLSearchParams(location.search).get("focus");
  if (focus && nameToRepo.value[focus]) {
    mode.value = "ecosystem";
    await nextTick();
    onNodeEnter(focus);
  }
  window.addEventListener("resize", onResize);
});
onBeforeUnmount(() => window.removeEventListener("resize", onResize));

watch(theme, applyTheme);
watch(mode, (m) => {
  if (location.hash.replace("#", "") !== m) history.replaceState(null, "", `#${m}`);
  hovered.value = null;
  edgeLines.value = [];
});

function applyTheme() {
  document.documentElement.dataset.theme = theme.value;
}
function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
  try { localStorage.setItem("mc_theme", theme.value); } catch (e) {}
}
function setMode(m) { mode.value = m; }
function setGroup(g) { groupBy.value = g; try { localStorage.setItem("mc_group", g); } catch (e) {} }
function setSort(s) { sortKey.value = s; try { localStorage.setItem("mc_sort", s); } catch (e) {} }
function toggleArchived() { showArchived.value = !showArchived.value; }
function toggleCat(c) {
  const s = new Set(activeCats.value);
  s.has(c) ? s.delete(c) : s.add(c);
  activeCats.value = s;
}
function toggleCollapse(k) {
  const s = new Set(collapsed.value);
  s.has(k) ? s.delete(k) : s.add(k);
  collapsed.value = s;
}
function setQuick(q) { quick.value = quick.value === q ? null : q; }
function openRepo(r) { if (r.url) window.open(r.url, "_blank", "noopener"); }

// ---- helpers ---------------------------------------------------------
function daysSince(ds) {
  if (!ds) return null;
  const d = new Date(ds + "T00:00:00Z");
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}
function relTime(ds) {
  const d = daysSince(ds);
  if (d === null) return "—";
  if (d <= 0) return "today";
  if (d === 1) return "1d";
  if (d < 60) return d + "d";
  if (d < 730) return Math.round(d / 30) + "mo";
  return Math.round(d / 365) + "y";
}
function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (e) { return iso; }
}
function pinInfo(r) {
  const raw = r.packaging?.compas_pin;
  if (!raw) return { text: "no pin", cls: "" };
  const spec = raw.replace(/^compas\s*/, "").trim();
  const floor = r.packaging?.compas_major_floor;
  if (floor >= 2) return { text: spec, cls: "pin-2x" };
  if (floor != null && floor < 2) return { text: spec, cls: "pin-old" };
  return { text: spec === "*" || spec === "" ? "unpinned" : spec, cls: "" };
}
const staleClass = (s) => "s-" + (s || "unknown");
const catLabel = (c) => CAT_LABEL[c] || c;
const relTag = (r) => r.release?.github_tag || r.release?.pypi_version || null;
const pyOn = (r, v) => (r.packaging?.python_versions || []).includes(v);
const featStatus = (r, id) => r.features?.[id]?.status || "unknown";
function featClass(st) {
  if (st === "adopted") return "adopted";
  if (st === "not-adopted") return "not";
  return "";
}

// ---- derived data ----------------------------------------------------
const repos = computed(() => data.value?.repos ?? []);
const features = computed(() => data.value?.features ?? []);
const categories = computed(() => data.value?.categories ?? []);

const active = computed(() => repos.value.filter((r) => r.status !== "archived"));
const summary = computed(() => {
  const app = active.value.filter((r) => ["adopted", "not-adopted"].includes(r.features?.compas2?.status));
  const on2x = app.filter((r) => r.features?.compas2?.status === "adopted").length;
  return {
    tracked: repos.value.length,
    archived: repos.value.length - active.value.length,
    applicable: app.length, on2x,
    pct2x: app.length ? Math.round((on2x / app.length) * 100) : null,
    failing: active.value.filter((r) => r.health?.ci === "failing").length,
    dormant: active.value.filter((r) => r.health?.staleness === "dormant").length,
    fresh: active.value.filter((r) => r.health?.staleness === "fresh").length,
  };
});

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  const cats = activeCats.value;
  return repos.value.filter((r) => {
    if (!showArchived.value && r.status === "archived") return false;
    if (cats.size && !cats.has(r.category)) return false;
    if (quick.value === "failing" && r.health?.ci !== "failing") return false;
    if (quick.value === "dormant" && r.health?.staleness !== "dormant") return false;
    if (q && !`${r.name} ${r.category} ${r.description ?? ""}`.toLowerCase().includes(q)) return false;
    return true;
  });
});

function comparator(a, b) {
  if ((a.status === "archived") !== (b.status === "archived")) return a.status === "archived" ? 1 : -1;
  if (sortKey.value === "name") return a.name.localeCompare(b.name);
  if (sortKey.value === "activity") {
    const oa = STALE_ORDER[a.health?.staleness] ?? 9, ob = STALE_ORDER[b.health?.staleness] ?? 9;
    if (oa !== ob) return oa - ob;
    return (b.stars ?? 0) - (a.stars ?? 0);
  }
  return (b.stars ?? 0) - (a.stars ?? 0) || a.name.localeCompare(b.name);
}

const lanes = computed(() => {
  const buckets = groupBy.value === "tier"
    ? TIER_GROUP.map((t) => ({ key: t.id, label: t.name, catClass: "", test: (r) => (r.tier || "domain") === t.id }))
    : categories.value.map((c) => ({ key: c, label: catLabel(c), catClass: "cat-" + c, test: (r) => r.category === c }));
  return buckets
    .map((b) => {
      const rs = filtered.value.filter(b.test).slice().sort(comparator);
      if (!rs.length) return null;
      const app = rs.filter((r) => ["adopted", "not-adopted"].includes(r.features?.compas2?.status)).length;
      const on2x = rs.filter((r) => r.features?.compas2?.status === "adopted").length;
      const fail = rs.filter((r) => r.health?.ci === "failing").length;
      return { ...b, repos: rs, app, on2x, fail, open: !collapsed.value.has(b.key) };
    })
    .filter(Boolean);
});
const matchCount = computed(() => filtered.value.length);

// ---- ecosystem -------------------------------------------------------
const nameToRepo = computed(() => Object.fromEntries(repos.value.map((r) => [r.name, r])));
const dependentsMap = computed(() => {
  const m = {};
  for (const r of repos.value) for (const d of r.ecosystem_deps || []) (m[d] ||= []).push(r.name);
  return m;
});
function ecoNodes(tier) {
  return repos.value
    .filter((r) => (showArchived.value || r.status !== "archived") && (r.tier || "domain") === tier)
    .sort((a, b) => (CAT_RANK[a.category] ?? 99) - (CAT_RANK[b.category] ?? 99) || (b.stars ?? 0) - (a.stars ?? 0) || a.name.localeCompare(b.name));
}
const tierBands = computed(() => ECO_TIERS.map((t) => ({ ...t, repos: ecoNodes(t.id) })).filter((t) => t.repos.length));

function isMatch(r) {
  const q = search.value.trim().toLowerCase();
  if (activeCats.value.size && !activeCats.value.has(r.category)) return false;
  if (q && !`${r.name} ${r.category} ${r.description ?? ""}`.toLowerCase().includes(q)) return false;
  return true;
}
const filterActive = computed(() => !!search.value.trim() || activeCats.value.size > 0);
const hovered = ref(null);
const hoverDeps = computed(() => new Set(hovered.value ? nameToRepo.value[hovered.value]?.ecosystem_deps || [] : []));
const hoverDependents = computed(() => new Set(hovered.value ? dependentsMap.value[hovered.value] || [] : []));
function nodeClass(r) {
  if (hovered.value) {
    if (r.name === hovered.value) return "is-active";
    if (hoverDeps.value.has(r.name)) return "is-dep";
    if (hoverDependents.value.has(r.name)) return "is-dependent";
    return "is-dim";
  }
  if (filterActive.value && !isMatch(r)) return "is-dim";
  return "";
}
const hoveredInfo = computed(() => {
  if (!hovered.value) return null;
  const r = nameToRepo.value[hovered.value];
  return { name: r.name, deps: r.ecosystem_deps || [], dependents: dependentsMap.value[r.name] || [] };
});

const diagramEl = ref(null);
const edgeLines = ref([]);
const diagramSize = ref({ w: 0, h: 0 });
function computeEdges(name) {
  const cont = diagramEl.value;
  if (!cont) return;
  const crect = cont.getBoundingClientRect();
  diagramSize.value = { w: crect.width, h: crect.height };
  const center = (n) => {
    const e = cont.querySelector(`[data-node="${CSS.escape(n)}"]`);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return { x: r.left + r.width / 2 - crect.left, y: r.top + r.height / 2 - crect.top };
  };
  const from = center(name);
  if (!from) return;
  const lines = [];
  for (const d of nameToRepo.value[name]?.ecosystem_deps || []) {
    const c = center(d);
    if (c) lines.push({ x1: from.x, y1: from.y, x2: c.x, y2: c.y, kind: "dep" });
  }
  for (const d of dependentsMap.value[name] || []) {
    const c = center(d);
    if (c) lines.push({ x1: from.x, y1: from.y, x2: c.x, y2: c.y, kind: "dependent" });
  }
  edgeLines.value = lines;
}
function onNodeEnter(name) {
  hovered.value = name;
  nextTick(() => computeEdges(name));
}
function onNodeLeave() {
  hovered.value = null;
  edgeLines.value = [];
}
function onResize() {
  if (hovered.value) computeEdges(hovered.value);
}
</script>

<template>
  <div v-if="error" class="empty">Failed to load data.json — {{ error }}</div>
  <div v-else-if="!data" class="empty">Loading ecosystem data…</div>

  <template v-else>
    <!-- masthead -->
    <header class="masthead">
      <div class="brand">
        <div class="logo"><div class="logo-dot"></div></div>
        <div>
          <h1 class="brand-title">Mission Control</h1>
          <div class="brand-sub">Signal board · <span class="mono">{{ summary.tracked }}</span> COMPAS repositories</div>
        </div>
      </div>
      <div class="mast-right">
        <div class="collected">
          <div class="collected-label">Collected</div>
          <div class="collected-time mono">{{ fmtDate(data.generated_at) }}</div>
        </div>
        <button class="theme-btn" @click="toggleTheme" title="Toggle theme">{{ theme === "dark" ? "☀" : "☾" }}</button>
      </div>
    </header>

    <!-- KPI ribbon -->
    <div class="ribbon">
      <div class="kpi">
        <div><span class="kpi-value">{{ summary.tracked }}</span></div>
        <div class="kpi-label">Repositories</div>
        <div class="kpi-sub">{{ summary.archived }} archived</div>
      </div>
      <div class="kpi">
        <div>
          <span class="kpi-value" :class="summary.pct2x === 100 ? 'good' : 'accent'">{{ summary.pct2x === null ? "—" : summary.pct2x }}</span>
          <span class="kpi-unit" v-if="summary.pct2x !== null">%</span>
        </div>
        <div class="kpi-label">On COMPAS 2.x</div>
        <div class="kpi-sub">{{ summary.on2x }}/{{ summary.applicable }}</div>
      </div>
      <button class="kpi clickable" :class="{ active: quick === 'failing' }" @click="setQuick('failing')">
        <div><span class="kpi-value" :class="summary.failing ? 'critical' : 'good'">{{ summary.failing }}</span></div>
        <div class="kpi-label">Failing CI <span class="kpi-cta">{{ quick === "failing" ? "· clear" : "· filter" }}</span></div>
        <div class="kpi-sub">default branch</div>
      </button>
      <button class="kpi clickable" :class="{ active: quick === 'dormant' }" @click="setQuick('dormant')">
        <div><span class="kpi-value" :class="summary.dormant ? 'serious' : ''">{{ summary.dormant }}</span></div>
        <div class="kpi-label">Dormant <span class="kpi-cta">{{ quick === "dormant" ? "· clear" : "· filter" }}</span></div>
        <div class="kpi-sub">&gt;1y idle</div>
      </button>
      <div class="ribbon-mig">
        <div class="mig-head">
          <span class="mig-head-label">2.x adoption</span>
          <span class="mono" style="font-size: 11px; color: var(--muted)">{{ summary.on2x }}/{{ summary.applicable }}</span>
        </div>
        <div class="mig-bar"><div class="mig-bar-fill" :style="{ width: (summary.pct2x || 0) + '%' }"></div></div>
        <div class="mig-legend">
          <span><span style="color: var(--good)">●</span> {{ summary.fresh }} fresh</span>
          <span><span style="color: var(--serious)">●</span> {{ summary.dormant }} dormant</span>
          <span><span style="color: var(--critical)">▲</span> {{ summary.failing }} fail CI</span>
        </div>
      </div>
    </div>

    <!-- toolbar -->
    <div class="toolbar">
      <div class="segmented">
        <button class="seg-btn" :class="{ active: mode === 'fleet' }" @click="setMode('fleet')">Fleet</button>
        <button class="seg-btn" :class="{ active: mode === 'ecosystem' }" @click="setMode('ecosystem')">Ecosystem</button>
      </div>
      <input class="search-input" type="search" v-model="search" placeholder="Filter repositories…" />
      <div class="chips">
        <button v-for="c in categories" :key="c" class="chip" :class="{ active: activeCats.has(c) }" @click="toggleCat(c)">{{ catLabel(c) }}</button>
      </div>
      <div class="toolbar-right">
        <template v-if="mode === 'fleet'">
          <div class="control">
            <span class="control-label">Group</span>
            <div class="segmented seg-sm">
              <button class="seg-btn" :class="{ active: groupBy === 'category' }" @click="setGroup('category')">Category</button>
              <button class="seg-btn" :class="{ active: groupBy === 'tier' }" @click="setGroup('tier')">Tier</button>
            </div>
          </div>
          <div class="control">
            <span class="control-label">Sort</span>
            <div class="segmented seg-sm">
              <button class="seg-btn" :class="{ active: sortKey === 'stars' }" @click="setSort('stars')">Stars</button>
              <button class="seg-btn" :class="{ active: sortKey === 'activity' }" @click="setSort('activity')">Activity</button>
              <button class="seg-btn" :class="{ active: sortKey === 'name' }" @click="setSort('name')">A–Z</button>
            </div>
          </div>
        </template>
        <label class="toggle"><input type="checkbox" v-model="showArchived" /> Archived</label>
      </div>
    </div>

    <div class="hint-row">
      <span v-if="mode === 'fleet'">each tile = one package · all four signals at a glance</span>
      <span v-else>dependency stack — core at the base, applications on top. Hover a package to trace its links.</span>
      <span class="matchcount">{{ matchCount }} / {{ summary.tracked }} shown</span>
    </div>

    <!-- ===== ECOSYSTEM ===== -->
    <template v-if="mode === 'ecosystem'">
      <div class="eco-caption">
        <template v-if="hoveredInfo">
          <span class="eco-focus">{{ hoveredInfo.name }}</span>
          <span class="eco-rel"><span class="edge-key dep">depends on</span> {{ hoveredInfo.deps.length ? hoveredInfo.deps.join(", ") : "—" }}</span>
          <span class="eco-rel"><span class="edge-key dependent">used by</span> {{ hoveredInfo.dependents.length ? hoveredInfo.dependents.join(", ") : "—" }}</span>
        </template>
        <span v-else class="eco-hint">Hover a package to trace what it depends on and what uses it.</span>
      </div>
      <div class="diagram" ref="diagramEl" @mouseleave="onNodeLeave">
        <svg class="edges" :width="diagramSize.w" :height="diagramSize.h" :viewBox="`0 0 ${diagramSize.w} ${diagramSize.h}`" preserveAspectRatio="none">
          <line v-for="(l, i) in edgeLines" :key="i" :class="l.kind" :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" />
        </svg>
        <div v-for="t in tierBands" :key="t.id" class="tier-band">
          <div class="tier-label">
            <span class="tier-name">{{ t.name }}</span>
            <span class="tier-sub">{{ t.sub }}</span>
          </div>
          <div class="tier-nodes">
            <button
              v-for="r in t.repos" :key="r.name"
              class="node" :class="['cat-' + r.category, nodeClass(r), { archived: r.status === 'archived' }]"
              :data-node="r.name"
              @mouseenter="onNodeEnter(r.name)" @focus="onNodeEnter(r.name)"
              @click="openRepo(r)" :title="r.description || r.name"
            >
              <span class="node-dot"></span>
              <span>{{ r.name }}</span>
              <span v-if="r.stars" class="node-stars">★{{ r.stars }}</span>
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- ===== FLEET CARDS ===== -->
    <template v-else>
      <div v-if="!lanes.length" class="empty">No repositories match the filters.</div>
      <div v-for="g in lanes" :key="g.key" class="lane">
        <div class="lane-head" @click="toggleCollapse(g.key)">
          <span class="lane-dot" :class="g.catClass" :style="g.catClass ? { background: 'var(--node-color, var(--accent))' } : { background: 'var(--accent)' }"></span>
          <span class="lane-chev">{{ g.open ? "▾" : "▸" }}</span>
          <span class="lane-name">{{ g.label }}</span>
          <span class="lane-count mono">{{ g.repos.length }}</span>
          <span v-if="g.fail" class="lane-fail">{{ g.fail }} failing</span>
          <span class="lane-2x mono">{{ g.on2x }}/{{ g.app }} on 2.x</span>
        </div>

        <div v-if="g.open" class="card-grid">
          <div v-for="r in g.repos" :key="r.name" class="card" :class="{ archived: r.status === 'archived' }">
            <div class="card-stripe" :style="{ background: `var(--cat-${r.category})` }"></div>
            <div class="card-body">
              <div class="card-head">
                <div class="card-head-left">
                  <a class="card-name" :href="r.url" target="_blank" rel="noopener">{{ r.name }}</a>
                  <span class="card-cat">{{ catLabel(r.category) }}<template v-if="r.role"> · {{ r.role }}</template></span>
                </div>
                <span class="card-stars">★ {{ r.stars ?? 0 }}</span>
              </div>

              <div class="stat-grid">
                <div class="stat">
                  <span class="stat-label">Activity</span>
                  <span class="stale-cell"><span class="dot" :class="staleClass(r.health?.staleness)"></span><span class="stat-val">{{ relTime(r.health?.last_commit_date) }}</span></span>
                </div>
                <div class="stat">
                  <span class="stat-label">CI</span>
                  <span v-if="r.health?.ci === 'passing'" class="ci-pass">● pass</span>
                  <span v-else-if="r.health?.ci === 'failing'" class="ci-fail">▲ fail</span>
                  <span v-else class="ci-none">—</span>
                </div>
                <div class="stat">
                  <span class="stat-label">Backlog</span>
                  <span class="stat-val" title="open issues · open PRs">{{ r.health?.open_issues ?? "—" }} · {{ r.health?.open_prs ?? "—" }}</span>
                </div>
              </div>

              <div class="ver-block">
                <div class="ver-row">
                  <span class="pin" :class="pinInfo(r).cls" title="COMPAS-core pin">{{ pinInfo(r).text }}</span>
                  <span v-if="relTag(r)" class="release">{{ relTag(r) }} · {{ relTime(r.release?.github_date || r.release?.pypi_date) }}</span>
                  <span v-if="r.release?.drift" class="drift" :title="`GitHub ${r.release.github_tag} ≠ PyPI ${r.release.pypi_version}`">⚠ drift</span>
                </div>
                <div class="support-row">
                  <span class="py-dots" title="Python 3.9–3.13 support">
                    <span v-for="v in PY" :key="v" class="py-dot" :class="{ on: pyOn(r, v) }"></span>
                  </span>
                  <span class="hosts">
                    <span class="host" :class="{ on: r.packaging?.hosts?.rhino }" title="Rhino">R</span>
                    <span class="host" :class="{ on: r.packaging?.hosts?.ghpython }" title="Grasshopper / GHPython">GH</span>
                    <span class="host" :class="{ on: r.packaging?.hosts?.blender }" title="Blender">B</span>
                  </span>
                </div>
              </div>

              <div class="adoption">
                <div class="adopt-label">Adoption</div>
                <div class="adopt-dots">
                  <span
                    v-for="f in features" :key="f.id"
                    class="adot" :class="featClass(featStatus(r, f.id))"
                    :title="`${f.label} — ${featStatus(r, f.id)}`"
                  ></span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <footer class="pagefoot">COMPAS Mission Control · collected nightly from the GitHub &amp; PyPI APIs</footer>
  </template>
</template>
