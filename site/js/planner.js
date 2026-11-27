// Flight-plan builder: pick a remote, schedule and retention, get the exact
// pyproject block, workflow cron and command, plus a preview of what stays.
(() => {
  const form = document.querySelector("[data-planner]");
  if (!form) return;
  const data = JSON.parse(document.getElementById("cab-data").textContent);
  const d = data.defaults;
  const [cm, ch, , , cd] = (document.documentElement.dataset.cron || "0 0 * * 0").split(/\s+/);
  const $ = (n) => form.elements[n];
  const out = (k) => form.querySelector(`[data-out="${k}"]`);
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  DAYS.forEach((name, i) => $("day").add(new Option(name, i)));
  $("day").add(new Option("every day", "*"));
  for (let h = 0; h < 24; h++) $("hour").add(new Option(`${String(h).padStart(2, "0")}:00 UTC`, h));
  $("remote").value = d.remote; $("folder").value = d.folder; $("keep").value = d.keep;
  $("day").value = cd; $("hour").value = +ch;

  const toml = (s) => JSON.stringify(s);
  function render() {
    const keep = +$("keep").value;
    const extra = $("exclude").value.split(",").map((s) => s.trim()).filter(Boolean);
    const day = $("day").value, hour = +$("hour").value;
    out("keep").textContent = keep === 0 ? "all" : keep;

    const ex = [...d.exclude.split(", "), ...extra];
    out("toml").textContent = [
      "[tool.cab]",
      `remote = ${toml($("remote").value || d.remote)}`,
      `folder = ${toml($("folder").value)}`,
      `keep = ${keep}`,
      `exclude = [${ex.map(toml).join(", ")}]`,
    ].join("\n");

    const cron = `${cm} ${hour} * * ${day}`;
    const when = new Date();
    when.setUTCHours(hour, +cm, 0, 0);
    const local = when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
    out("cron").textContent =
      `on:\n  schedule:\n    - cron: "${cron}"  # ${day === "*" ? "daily" : DAYS[day] + "s"} ${String(hour).padStart(2, "0")}:00 UTC (${local} for you)`;

    const flags = [];
    if ($("remote").value && $("remote").value !== d.remote) flags.push(`--remote ${$("remote").value}`);
    if ($("folder").value !== d.folder) flags.push(`--folder ${JSON.stringify($("folder").value)}`);
    if (keep !== d.keep) flags.push(`--keep ${keep}`);
    if (extra.length) flags.push(`--exclude "${ex.join(",")}"`);
    out("cmd").textContent = `cab run ${flags.join(" ")}`.trim() + "   # or just `cab run` with the block above";

    // retention preview: the last 16 runs, newest on the right
    const runs = 16, every = day === "*" ? 1 : 7;
    const strip = out("strip");
    strip.textContent = "";
    for (let i = runs - 1; i >= 0; i--) {
      const kept = keep === 0 || i < keep;
      const cell = document.createElement("span");
      cell.className = kept ? "kept" : "gone";
      const t = new Date(Date.now() - i * every * 864e5);
      cell.title = `${t.toISOString().slice(0, 10)} · ${kept ? "kept" : "pruned"}`;
      strip.appendChild(cell);
    }
    const stays = keep === 0 ? runs : Math.min(keep, runs);
    const span = keep === 0 ? "forever" : `${keep * every} days back`;
    out("summary").textContent =
      `after ${runs} runs: ${stays} on the remote, ~${(stays * 48 / 1024).toFixed(2)} MB at 48 KB each, history reaches ${span}`;
  }

  form.addEventListener("input", render);
  form.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    e.preventDefault();
    const text = out(btn.dataset.copy).textContent;
    try { await navigator.clipboard.writeText(text); btn.textContent = "copied"; }
    catch { btn.textContent = "select + copy"; }
    setTimeout(() => (btn.textContent = "copy"), 1400);
  });
  render();
})();
