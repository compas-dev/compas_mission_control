<script setup>
import { computed, ref, onMounted, watch, nextTick } from "vue";

const data = ref(null);
const error = ref(null);

// ---- view + filters (shared across all sections) ---------------------
const view = ref("health"); // health | migration | features
const search = ref("");
const activeCats = ref(new Set());
const showArchived = ref(false);
const quick = ref(null); // null | "failing" | "dormant" — from clickable tiles
const collapsed = ref(new Set());
const sort = ref({ key: "stars", dir: -1 });

const STALE_ORDER = { fresh: 0, aging: 1, stale: 2, dormant: 3, unknown: 4 };
const CI_ORDER = { passing: 0, none: 1, unknown: 2, failing: 3 };
const PY_COLUMNS = ["3.9", "3.10", "3.11", "3.12", "3.13"];
const CAT_LABEL = {
  core: "Core", fabrication: "Fabrication", timber: "Timber", geometry: "Geometry",
  structures: "Structures", fea: "FEA", viz: "Visualization", xr: "XR",
  tooling: "Tooling", template: "Templates", other: "Other",
};

const VALID_VIEWS = ["health", "migration", "features", "ecosystem"];

onMounted(async () => {
  const hash = location.hash.replace("#", "");
  if (VALID_VIEWS.includes(hash)) view.value = hash;
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data.json`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`data.json ${res.status}`);
    data.value = await res.json();
  } catch (e) {
    error.value = String(e);
  }
  // ?focus=<pkg> deep-links straight to a package's dependency trace.
  const focus = new URLSearchParams(location.search).get("focus");
  if (focus && nameToRepo.value[focus]) {
    view.value = "ecosystem";
    await nextTick();
    onNodeEnter(nameToRepo.value[focus]);
  }
});

// Keep the active view in the URL hash so views are deep-linkable.
watch(view, (v) => {
  if (location.hash.replace("#", "") !== v) history.replaceState(null, "", `#${v}`);
});

// ---- helpers ---------------------------------------------------------
function daysSince(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr + "T00:00:00Z");
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}
function relTime(dateStr) {
  const days = daysSince(dateStr);
  if (days === null) return "—";
  if (days <= 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 60) return `${days}d ago`;
  if (days < 730) return `${Math.round(days / 30)}mo ago`;
  return `${Math.round(days / 365)}y ago`;
}
function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
const staleClass = (s) => ({ fresh: "s-good", aging: "s-warning", stale: "s-serious", dormant: "s-critical" }[s] || "s-muted");
const catLabel = (c) => CAT_LABEL[c] || c;

function pinInfo(r) {
  const raw = r.packaging?.compas_pin;
  if (!raw) return { text: "n/a", cls: "muted-cell" };
  const spec = raw.replace(/^compas\s*/, "").trim();
  const floor = r.packaging?.compas_major_floor;
  if (floor >= 2) return { text: spec, cls: "pin-2x" };
  if (floor != null && floor < 2) return { text: spec, cls: "pin-old" };
  return { text: spec === "*" || spec === "" ? "unpinned" : spec, cls: "muted-cell" };
}

// ---- derived data ----------------------------------------------------
const repos = computed(() => data.value?.repos ?? []);
const features = computed(() => data.value?.features ?? []);
const categories = computed(() => data.value?.categories ?? []);
const pyColumns = computed(() => PY_COLUMNS);

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  const cats = activeCats.value;
  return repos.value.filter((r) => {
    if (!showArchived.value && r.status === "archived") return false;
    if (cats.size && !cats.has(r.category)) return false;
    if (quick.value === "failing" && r.health?.ci !== "failing") return false;
    if (quick.value === "dormant" && r.health?.staleness !== "dormant") return false;
    if (q && !(`${r.name} ${r.category} ${r.description ?? ""}`.toLowerCase().includes(q))) return false;
    return true;
  });
});

function healthComparator(a, b) {
  if ((a.status === "archived") !== (b.status === "archived"))
    return a.status === "archived" ? 1 : -1;
  const { key, dir } = sort.value;
  const val = (r) => ({
    name: r.name, category: r.category,
    staleness: STALE_ORDER[r.health?.staleness] ?? 9,
    ci: CI_ORDER[r.health?.ci] ?? 9,
    open_issues: r.health?.open_issues ?? -1,
    open_prs: r.health?.open_prs ?? -1,
    release: r.release?.github_date ?? r.release?.pypi_date ?? "",
    stars: r.stars ?? 0,
  }[key] ?? r.name);
  const va = val(a), vb = val(b);
  if (va < vb) return -dir;
  if (va > vb) return dir;
  return a.name.localeCompare(b.name);
}
const byName = (a, b) =>
  ((a.status === "archived") !== (b.status === "archived"))
    ? (a.status === "archived" ? 1 : -1)
    : a.name.localeCompare(b.name);

// Group filtered repos by category (in canonical order), sorted per view.
function grouping(sortFn) {
  return categories.value
    .map((cat) => {
      const rs = filtered.value.filter((r) => r.category === cat).sort(sortFn);
      return { cat, repos: rs };
    })
    .filter((g) => g.repos.length);
}
const groupsHealth = computed(() => grouping(healthComparator));
const groupsPlain = computed(() => grouping(byName));

function groupStats(g) {
  const on2x = g.repos.filter((r) => r.features?.compas2?.status === "adopted").length;
  const app = g.repos.filter((r) => ["adopted", "not-adopted"].includes(r.features?.compas2?.status)).length;
  const failing = g.repos.filter((r) => r.health?.ci === "failing").length;
  return { on2x, app, failing };
}

function setSort(key) {
  if (sort.value.key === key) sort.value = { key, dir: -sort.value.dir };
  else sort.value = { key, dir: key === "name" || key === "category" ? 1 : -1 };
}
const arrow = (key) => (sort.value.key === key ? (sort.value.dir === 1 ? "▲" : "▼") : "");

function toggleCat(c) {
  const s = new Set(activeCats.value);
  s.has(c) ? s.delete(c) : s.add(c);
  activeCats.value = s;
}
function toggleCollapse(c) {
  const s = new Set(collapsed.value);
  s.has(c) ? s.delete(c) : s.add(c);
  collapsed.value = s;
}
function setQuick(q) {
  quick.value = quick.value === q ? null : q;
}
const allCollapsed = computed(() => categories.value.length && collapsed.value.size >= groupsPlain.value.length);
function toggleAll() {
  collapsed.value = allCollapsed.value ? new Set() : new Set(groupsPlain.value.map((g) => g.cat));
}

// ---- summary tiles ---------------------------------------------------
const summary = computed(() => {
  const active = repos.value.filter((r) => r.status !== "archived");
  const applicable = active.filter((r) => ["adopted", "not-adopted"].includes(r.features?.compas2?.status));
  const on2x = applicable.filter((r) => r.features?.compas2?.status === "adopted").length;
  return {
    tracked: repos.value.length,
    archived: repos.value.length - active.length,
    pct2x: applicable.length ? Math.round((on2x / applicable.length) * 100) : null,
    on2x, applicable: applicable.length,
    failingCI: active.filter((r) => r.health?.ci === "failing").length,
    dormant: active.filter((r) => r.health?.staleness === "dormant").length,
  };
});

const featureStats = computed(() => {
  const out = {};
  for (const f of features.value) {
    let adopted = 0, applicable = 0;
    for (const r of filtered.value) {
      const st = r.features?.[f.id]?.status;
      if (st === "adopted") { adopted++; applicable++; }
      else if (st === "not-adopted") applicable++;
    }
    out[f.id] = { adopted, applicable };
  }
  return out;
});

const featCell = (st) => ({ adopted: "cell-adopted", "not-adopted": "cell-not", "n/a": "cell-na" }[st] || "cell-unknown");
const featGlyph = (st) => ({ adopted: "✓", "not-adopted": "✗", "n/a": "–" }[st] || "?");

function openRepo(r) {
  if (r.url) window.open(r.url, "_blank", "noopener");
}

// ---- ecosystem dependency diagram ------------------------------------
const CAT_RANK = Object.fromEntries(
  ["core", "geometry", "structures", "fea", "fabrication", "timber", "xr", "viz", "apps", "tooling", "template", "other"]
    .map((c, i) => [c, i])
);
const TIER_META = [
  { id: "apps", name: "Applications", sub: "end-user tools & big apps" },
  { id: "domain", name: "Domain extensions", sub: "discipline-specific packages" },
  { id: "foundation", name: "Foundation", sub: "geometry & data libraries" },
  { id: "core", name: "Core", sub: "the COMPAS framework" },
  { id: "tooling", name: "Tooling", sub: "shared dev infrastructure" },
];

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
const tierBands = computed(() => TIER_META.map((t) => ({ ...t, repos: ecoNodes(t.id) })).filter((t) => t.repos.length));

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
function onNodeEnter(r) {
  hovered.value = r.name;
  nextTick(() => computeEdges(r.name));
}
function onNodeLeave() {
  hovered.value = null;
  edgeLines.value = [];
}
const hoveredInfo = computed(() => {
  if (!hovered.value) return null;
  const r = nameToRepo.value[hovered.value];
  return { name: r.name, deps: r.ecosystem_deps || [], dependents: dependentsMap.value[r.name] || [] };
});

const VIEWS = [
  { id: "health", label: "Health" },
  { id: "migration", label: "Migration" },
  { id: "features", label: "Features" },
  { id: "ecosystem", label: "Ecosystem" },
];
const matchCount = computed(() => filtered.value.length);
</script>

<template>
  <div v-if="error" class="empty">Failed to load data.json — {{ error }}</div>
  <div v-else-if="!data" class="empty">Loading ecosystem data…</div>

  <template v-else>
    <!-- ---- masthead ---- -->
    <header class="masthead">
      <div>
        <h1>COMPAS Mission Control</h1>
        <div class="subtitle">Ecosystem health &amp; 2.x migration across {{ summary.tracked }} tracked repositories</div>
      </div>
      <div class="updated">Updated {{ fmtDateTime(data.generated_at) }}</div>
    </header>

    <!-- ---- summary tiles (failing / dormant are clickable filters) ---- -->
    <div class="tiles">
      <div class="tile">
        <div class="value">{{ summary.tracked }}</div>
        <div class="label">Repositories tracked</div>
        <div class="sub" v-if="summary.archived">{{ summary.archived }} archived</div>
      </div>
      <div class="tile">
        <div class="value" :class="summary.pct2x === 100 ? 'good' : 'accent'">
          {{ summary.pct2x === null ? "—" : summary.pct2x + "%" }}
        </div>
        <div class="label">On COMPAS 2.x</div>
        <div class="sub">{{ summary.on2x }}/{{ summary.applicable }} dependents</div>
      </div>
      <button class="tile clickable" :class="{ active: quick === 'failing' }" @click="setQuick('failing')">
        <div class="value" :class="summary.failingCI ? 'critical' : 'good'">{{ summary.failingCI }}</div>
        <div class="label">Failing CI <span class="tile-cta">{{ quick === 'failing' ? '· clear' : '· filter' }}</span></div>
        <div class="sub">on default branch</div>
      </button>
      <button class="tile clickable" :class="{ active: quick === 'dormant' }" @click="setQuick('dormant')">
        <div class="value" :class="summary.dormant ? 'critical' : ''">{{ summary.dormant }}</div>
        <div class="label">Dormant <span class="tile-cta">{{ quick === 'dormant' ? '· clear' : '· filter' }}</span></div>
        <div class="sub">no commits &gt; 1&nbsp;year</div>
      </button>
    </div>

    <!-- ---- sticky toolbar: tabs + filters ---- -->
    <div class="toolbar">
      <div class="tabs" role="tablist">
        <button v-for="v in VIEWS" :key="v.id" class="tab" role="tab"
                :aria-selected="view === v.id" @click="view = v.id">{{ v.label }}</button>
      </div>
      <input type="search" v-model="search" placeholder="Filter repositories…" />
      <div class="chips-row">
        <button v-for="c in categories" :key="c" class="filter-chip"
                :aria-pressed="activeCats.has(c)" @click="toggleCat(c)">{{ catLabel(c) }}</button>
      </div>
      <div class="toolbar-right">
        <label class="toggle"><input type="checkbox" v-model="showArchived" /> Archived</label>
        <button class="ghost-btn" @click="toggleAll">{{ allCollapsed ? "Expand all" : "Collapse all" }}</button>
      </div>
    </div>

    <p class="viewhint">
      <template v-if="view === 'health'">Staleness, CI, backlog and releases. Click a header to sort within each group; click a row to open the repo.</template>
      <template v-else-if="view === 'migration'">COMPAS-core pin, Python-version support (CI matrix preferred), and host-app packaging.</template>
      <template v-else-if="view === 'features'">
        <span class="legend">
          <span><span class="cell cell-adopted">✓</span> adopted</span>
          <span><span class="cell cell-not">✗</span> not adopted</span>
          <span><span class="cell cell-na">–</span> n/a</span>
          <span><span class="cell cell-unknown">?</span> unknown</span>
          <span><span class="dot" style="background:var(--accent)"></span> manual</span>
        </span>
      </template>
      <template v-else>
        Dependency stack — core at the base, applications on top. Hover a package to trace what it
        <span class="edge-key dep">depends on</span> and what
        <span class="edge-key dependent">uses it</span>.
      </template>
      <span v-if="view !== 'ecosystem'" class="matchcount">{{ matchCount }} of {{ summary.tracked }} shown</span>
    </p>

    <div v-if="!matchCount && view !== 'ecosystem'" class="empty">No repositories match the filters.</div>

    <!-- ============ HEALTH ============ -->
    <div v-show="view === 'health' && matchCount" class="card scroll-x">
      <table>
        <thead>
          <tr>
            <th class="sortable" @click="setSort('name')">Repository <span class="arrow">{{ arrow("name") }}</span></th>
            <th class="sortable" @click="setSort('staleness')">Last commit <span class="arrow">{{ arrow("staleness") }}</span></th>
            <th class="sortable center" @click="setSort('ci')">CI <span class="arrow">{{ arrow("ci") }}</span></th>
            <th class="sortable num" @click="setSort('open_issues')">Issues <span class="arrow">{{ arrow("open_issues") }}</span></th>
            <th class="sortable num" @click="setSort('open_prs')">PRs <span class="arrow">{{ arrow("open_prs") }}</span></th>
            <th class="sortable" @click="setSort('release')">Latest release <span class="arrow">{{ arrow("release") }}</span></th>
            <th class="sortable num" @click="setSort('stars')">★ <span class="arrow">{{ arrow("stars") }}</span></th>
          </tr>
        </thead>
        <tbody v-for="g in groupsHealth" :key="g.cat">
          <tr class="group-row" @click="toggleCollapse(g.cat)">
            <td colspan="7">
              <span class="chev">{{ collapsed.has(g.cat) ? "▸" : "▾" }}</span>
              <span class="group-name">{{ catLabel(g.cat) }}</span>
              <span class="group-count">{{ g.repos.length }}</span>
              <span v-if="groupStats(g).failing" class="group-stat crit">{{ groupStats(g).failing }} failing CI</span>
              <span class="group-stat">{{ groupStats(g).on2x }}/{{ groupStats(g).app }} on 2.x</span>
            </td>
          </tr>
          <template v-if="!collapsed.has(g.cat)">
            <tr v-for="r in g.repos" :key="r.name" :class="{ archived: r.status === 'archived' }"
                @click="openRepo(r)" style="cursor:pointer">
              <td>
                <span class="repo-name">
                  <a :href="r.url" target="_blank" rel="noopener" @click.stop>{{ r.name }}</a>
                  <span v-if="r.role" class="role-tag">{{ r.role }}</span>
                </span>
              </td>
              <td>
                <span class="stale-cell">
                  <span class="dot" :class="staleClass(r.health?.staleness)"></span>
                  <span class="reltime">{{ relTime(r.health?.last_commit_date) }}</span>
                </span>
              </td>
              <td class="center">
                <span v-if="r.health?.ci === 'passing'" class="badge badge-good"><span class="glyph">●</span>pass</span>
                <span v-else-if="r.health?.ci === 'failing'" class="badge badge-critical"><span class="glyph">▲</span>fail</span>
                <span v-else class="badge badge-muted">—</span>
              </td>
              <td class="num" :class="{ 'muted-cell': !r.health?.open_issues }">{{ r.health?.open_issues ?? "—" }}</td>
              <td class="num" :class="{ 'muted-cell': !r.health?.open_prs }">{{ r.health?.open_prs ?? "—" }}</td>
              <td>
                <template v-if="r.release?.github_tag || r.release?.pypi_version">
                  <span class="pin-cell">{{ r.release.github_tag || r.release.pypi_version }}</span>
                  <span class="reltime"> · {{ relTime(r.release.github_date || r.release.pypi_date) }}</span>
                  <span v-if="r.release.drift" class="drift-flag"
                        :title="`GitHub ${r.release.github_tag} ≠ PyPI ${r.release.pypi_version}`">⚠ drift</span>
                </template>
                <span v-else class="muted-cell">none</span>
              </td>
              <td class="num">{{ r.stars ?? 0 }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- ============ MIGRATION ============ -->
    <div v-show="view === 'migration' && matchCount" class="card scroll-x">
      <table class="ver-grid">
        <thead>
          <tr>
            <th>Repository</th>
            <th>COMPAS pin</th>
            <th v-for="v in pyColumns" :key="v" class="center">{{ v }}</th>
            <th class="center">Hosts</th>
          </tr>
        </thead>
        <tbody v-for="g in groupsPlain" :key="g.cat">
          <tr class="group-row" @click="toggleCollapse(g.cat)">
            <td :colspan="pyColumns.length + 3">
              <span class="chev">{{ collapsed.has(g.cat) ? "▸" : "▾" }}</span>
              <span class="group-name">{{ catLabel(g.cat) }}</span>
              <span class="group-count">{{ g.repos.length }}</span>
              <span class="group-stat">{{ groupStats(g).on2x }}/{{ groupStats(g).app }} on 2.x</span>
            </td>
          </tr>
          <template v-if="!collapsed.has(g.cat)">
            <tr v-for="r in g.repos" :key="r.name" :class="{ archived: r.status === 'archived' }">
              <td><span class="repo-name"><a :href="r.url" target="_blank" rel="noopener">{{ r.name }}</a></span></td>
              <td class="pin-cell"><span :class="pinInfo(r).cls">{{ pinInfo(r).text }}</span></td>
              <td v-for="v in pyColumns" :key="v" class="center">
                <span class="cell" :class="(r.packaging?.python_versions || []).includes(v) ? 'cell-adopted' : 'cell-na'"
                      :title="`Python support source: ${r.packaging?.python_source || 'unknown'}`">
                  {{ (r.packaging?.python_versions || []).includes(v) ? "✓" : "·" }}
                </span>
              </td>
              <td class="center">
                <span class="host-icons">
                  <span class="host" :class="{ on: r.packaging?.hosts?.rhino }" title="Rhino">R</span>
                  <span class="host" :class="{ on: r.packaging?.hosts?.ghpython }" title="Grasshopper / GHPython">GH</span>
                  <span class="host" :class="{ on: r.packaging?.hosts?.blender }" title="Blender">B</span>
                </span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- ============ FEATURES ============ -->
    <div v-show="view === 'features' && matchCount" class="card scroll-x">
      <table>
        <thead>
          <tr>
            <th>Repository</th>
            <th v-for="f in features" :key="f.id" class="center" :title="f.kind">{{ f.label }}</th>
          </tr>
        </thead>
        <tbody v-for="g in groupsPlain" :key="g.cat">
          <tr class="group-row" @click="toggleCollapse(g.cat)">
            <td :colspan="features.length + 1">
              <span class="chev">{{ collapsed.has(g.cat) ? "▸" : "▾" }}</span>
              <span class="group-name">{{ catLabel(g.cat) }}</span>
              <span class="group-count">{{ g.repos.length }}</span>
            </td>
          </tr>
          <template v-if="!collapsed.has(g.cat)">
            <tr v-for="r in g.repos" :key="r.name" :class="{ archived: r.status === 'archived' }">
              <td><span class="repo-name"><a :href="r.url" target="_blank" rel="noopener">{{ r.name }}</a></span></td>
              <td v-for="f in features" :key="f.id" class="center">
                <span class="cell" :class="[featCell(r.features?.[f.id]?.status), { 'manual-mark': r.features?.[f.id]?.source === 'manual' }]"
                      :title="`${r.features?.[f.id]?.status ?? 'unknown'} — ${r.features?.[f.id]?.detail ?? ''}`">
                  {{ featGlyph(r.features?.[f.id]?.status) }}
                </span>
              </td>
            </tr>
          </template>
        </tbody>
        <tfoot>
          <tr class="col-footer">
            <td class="rowlabel">adopted / applicable (shown)</td>
            <td v-for="f in features" :key="f.id">{{ featureStats[f.id].adopted }}/{{ featureStats[f.id].applicable }}</td>
          </tr>
        </tfoot>
      </table>
    </div>

    <!-- ============ ECOSYSTEM DIAGRAM ============ -->
    <div v-show="view === 'ecosystem'" class="eco-wrap">
      <div class="eco-caption">
        <template v-if="hoveredInfo">
          <span class="eco-focus">{{ hoveredInfo.name }}</span>
          <span class="eco-rel"><span class="edge-key dep">depends on</span>
            {{ hoveredInfo.deps.length ? hoveredInfo.deps.join(", ") : "—" }}</span>
          <span class="eco-rel"><span class="edge-key dependent">used by</span>
            {{ hoveredInfo.dependents.length ? hoveredInfo.dependents.join(", ") : "—" }}</span>
        </template>
        <template v-else><span class="eco-hint">Hover any package to trace its dependencies. Edges are resolved from parsed requirements across tracked repos.</span></template>
      </div>

      <div class="diagram card" ref="diagramEl" @mouseleave="onNodeLeave">
        <svg class="edges" :width="diagramSize.w" :height="diagramSize.h"
             :viewBox="`0 0 ${diagramSize.w} ${diagramSize.h}`" preserveAspectRatio="none">
          <line v-for="(l, i) in edgeLines" :key="i" :class="l.kind"
                :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" />
        </svg>
        <div v-for="t in tierBands" :key="t.id" class="tier-band">
          <div class="tier-label">
            <span class="tier-name">{{ t.name }}</span>
            <span class="tier-sub">{{ t.sub }}</span>
          </div>
          <div class="tier-nodes">
            <button v-for="r in t.repos" :key="r.name" class="node" :class="['cat-' + r.category, nodeClass(r), { archived: r.status === 'archived' }]"
                    :data-node="r.name" @mouseenter="onNodeEnter(r)" @focus="onNodeEnter(r)"
                    @click="openRepo(r)" :title="r.description || r.name">
              <span class="node-dot"></span>
              <span class="node-name">{{ r.name }}</span>
              <span v-if="r.stars" class="node-stars">{{ r.stars }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <details class="warnings" v-if="data.warnings?.length">
      <summary>{{ data.warnings.length }} collector warning(s)</summary>
      <ul><li v-for="(w, i) in data.warnings" :key="i">{{ w }}</li></ul>
    </details>

    <footer class="pagefoot">
      COMPAS Mission Control · data collected nightly from the GitHub &amp; PyPI APIs
    </footer>
  </template>
</template>
