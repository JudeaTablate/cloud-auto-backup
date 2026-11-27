// Live bits: countdown to the next scheduled backup, and an altitude tape
// that follows the section you're reading. The schedule comes from the
// cron line in backup.yml, which build.py copies into data-cron.
(() => {
  const root = document.documentElement;
  const [min, hour, , , dow] = (root.dataset.cron || "0 0 * * 0").split(/\s+/);

  function nextRun(now = new Date()) {
    const t = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), +hour, +min));
    const day = dow === "*" ? t.getUTCDay() : +dow % 7;
    let add = (day - t.getUTCDay() + 7) % 7;
    if (add === 0 && t <= now) add = dow === "*" ? 1 : 7;
    t.setUTCDate(t.getUTCDate() + add);
    return t;
  }

  const pad = (n) => String(n).padStart(2, "0");
  const out = document.querySelectorAll("[data-countdown]");
  const local = document.querySelector("[data-local-time]");
  function tick() {
    const next = nextRun();
    let s = Math.max(0, Math.floor((next - Date.now()) / 1000));
    const d = Math.floor(s / 86400); s %= 86400;
    const text = `${d}d ${pad(Math.floor(s / 3600))}h ${pad(Math.floor(s / 60) % 60)}m ${pad(s % 60)}s`;
    out.forEach((el) => (el.textContent = text));
    if (local) {
      local.textContent = next.toLocaleString(undefined, {
        weekday: "long", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
      });
    }
  }
  tick();
  setInterval(tick, 1000);

  // pause / resume the cloud drift; remembered per browser when storage works
  const toggle = document.querySelector("[data-drift]");
  if (toggle) {
    const set = (still) => {
      root.classList.toggle("still", still);
      toggle.textContent = still ? "resume clouds" : "pause clouds";
      toggle.setAttribute("aria-pressed", String(still));
      try { localStorage.setItem("cab-still", still ? "1" : ""); } catch {}
    };
    let saved = false;
    try { saved = localStorage.getItem("cab-still") === "1"; } catch {}
    set(saved);
    toggle.addEventListener("click", () => set(!root.classList.contains("still")));
  }

  // altitude tape: highlight the flight level of the section in view
  const tape = document.querySelector(".tape");
  if (!tape || !("IntersectionObserver" in window)) return;
  const marks = new Map([...tape.querySelectorAll("[data-fl]")].map((m) => [m.dataset.fl, m]));
  const links = document.querySelectorAll(".nav a[href^='#']");
  const seen = new Map();
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => seen.set(e.target.id, e.intersectionRatio));
    const [id] = [...seen].sort((a, b) => b[1] - a[1])[0] || [];
    if (!id || !marks.has(id)) return;
    marks.forEach((m, k) => m.classList.toggle("on", k === id));
    links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#${id}`));
    const m = marks.get(id);
    tape.style.setProperty("--needle", `${m.offsetTop + m.offsetHeight / 2}px`);
  }, { threshold: [0, 0.25, 0.5, 0.75, 1] });
  document.querySelectorAll("main section[id]").forEach((s) => io.observe(s));
})();
