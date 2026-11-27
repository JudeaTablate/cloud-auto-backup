// A pretend `cab` you can type into. Help text is the real argparse output
// (build.py embeds it as JSON); the remote lives in memory and resets on reload.
(() => {
  const box = document.querySelector("[data-term]");
  const data = JSON.parse(document.getElementById("cab-data").textContent);
  if (!box) return;
  const screen = box.querySelector(".screen");
  const input = box.querySelector("input");
  const PROMPT = "guest@cab:~$";
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  const stamp = (d) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}_${pad(d.getUTCHours())}-${pad(d.getUTCMinutes())}`;
  const clock = () => new Date().toTimeString().slice(0, 8);
  const human = (b) => (b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`);
  const hex = (n) => Array.from({ length: n }, () => "0123456789abcdef"[(Math.random() * 16) | 0]).join("");

  // seed the remote with six weekly snapshots ending last Sunday 00:00 UTC
  const remote = [];
  const sun = new Date(); sun.setUTCHours(0, 0, 0, 0); sun.setUTCDate(sun.getUTCDate() - sun.getUTCDay());
  for (let i = 5; i >= 0; i--) {
    const d = new Date(sun - i * 7 * 864e5);
    const name = `${data.defaults.prefix}_${stamp(d)}.zip`;
    remote.push({ name, size: 46000 + ((Math.random() * 4000) | 0), when: d });
    remote.push({ name: name + ".sha256", size: 98, when: d });
  }

  function print(text = "", cls = "") {
    const line = document.createElement("div");
    if (cls) line.className = cls;
    line.textContent = text;
    screen.appendChild(line);
    screen.scrollTop = screen.scrollHeight;
  }
  const log = (msg) => print(`${clock()}  ${msg}`);

  function parse(args) {
    const cfg = { ...data.defaults, dry_run: false };
    const takes = ["remote", "folder", "source", "keep", "prefix", "exclude"];
    for (let i = 0; i < args.length; i++) {
      let [flag, val] = args[i].split("=");
      if (flag === "-n" || flag === "--dry-run") { cfg.dry_run = true; continue; }
      const key = flag.replace(/^--/, "");
      if (!flag.startsWith("--") || !takes.includes(key)) throw `unrecognized arguments: ${args[i]}`;
      val = val ?? args[++i];
      if (val === undefined) throw `argument ${flag}: expected one argument`;
      if (key === "keep" && !/^\d+$/.test(val)) throw `argument --keep: invalid int value: '${val}'`;
      cfg[key] = key === "keep" ? +val : val;
    }
    cfg.target = `${cfg.remote}:${cfg.folder.replace(/^\/+|\/+$/g, "")}`;
    return cfg;
  }

  const snaps = (prefix) => {
    const re = new RegExp(`^${prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}_\\d{4}-\\d\\d-\\d\\d_\\d\\d-\\d\\d\\.zip$`);
    return remote.filter((f) => re.test(f.name)).sort((a, b) => (a.name < b.name ? 1 : -1));
  };

  async function prune(cfg) {
    const doomed = cfg.keep > 0 ? snaps(cfg.prefix).slice(cfg.keep) : [];
    if (!doomed.length) return log(`retain   nothing to prune (keep=${cfg.keep})`);
    for (const z of doomed) {
      for (const name of [z.name, z.name + ".sha256"]) {
        const i = remote.findIndex((f) => f.name === name);
        if (i < 0) continue;
        await wait(160);
        if (!cfg.dry_run) remote.splice(i, 1);
        log(`pruned   ${name}${cfg.dry_run ? "  [dry-run]" : ""}`);
      }
    }
  }

  const commands = {
    async run(cfg) {
      const name = `${cfg.prefix}_${stamp(new Date())}.zip`;
      const size = 46000 + ((Math.random() * 6000) | 0);
      await wait(500); log(`packed   ${name}  (${data.files} files, ${human(size)})`);
      await wait(250); log(`sha256   ${hex(64)}`);
      await wait(700);
      if (!cfg.dry_run && !remote.some((f) => f.name === name)) {
        remote.push({ name, size, when: new Date() }, { name: name + ".sha256", size: 98, when: new Date() });
      }
      log(`uploaded -> ${cfg.target}${cfg.dry_run ? "  [dry-run]" : ""}`);
      if (cfg.keep) await prune(cfg);
    },
    async list(cfg) {
      const s = snaps(cfg.prefix);
      if (!s.length) return log(`no snapshots at ${cfg.target}`);
      s.forEach((f) => print(`${f.name}  ${human(f.size).padStart(9)}  ${f.when.toISOString().slice(0, 16).replace("T", " ")}`));
    },
    prune,
    async config(cfg) {
      for (const k of ["remote", "folder", "source", "keep", "prefix", "exclude", "dry_run"]) {
        const v = k === "dry_run" ? (cfg[k] ? "True" : "False") : cfg[k];
        print(`${k.padEnd(8)} = ${v}`);
      }
      print(`${"target".padEnd(8)} = ${cfg.target}`);
    },
  };

  const extras = {
    help: () => print(data.help.cab),
    clear: () => (screen.textContent = ""),
    ls: () => print(data.ls.join("  ")),
    whoami: () => print("guest (this terminal runs in your browser; nothing leaves it)"),
    date: () => print(new Date().toUTCString()),
    history: () => history.forEach((h, i) => print(`${String(i + 1).padStart(4)}  ${h}`)),
    sudo: () => print("sudo: you are cleared for takeoff, not for root.", "err"),
    exit: () => print("there is no exit. only backups."),
  };

  async function exec(line) {
    const [cmd, ...args] = line.trim().split(/\s+/);
    if (!cmd) return;
    if (extras[cmd]) return extras[cmd](args);
    if (cmd !== "cab") return print(`${cmd}: command not found. try 'help'`, "err");
    const sub = args[0] && !args[0].startsWith("-") ? args.shift() : "run";
    if (args.includes("-h") || args.includes("--help")) return print(data.help[sub] || data.help.cab);
    if (args.includes("--version")) return print(`cab ${data.version}`);
    if (!commands[sub]) return print(`cab: error: argument COMMAND: invalid choice: '${sub}' (choose from 'run', 'list', 'prune', 'config')`, "err");
    try {
      await commands[sub](parse(args));
    } catch (e) {
      print(`usage: cab ${sub} [-h] [--remote REMOTE] [--folder FOLDER] ...`, "err");
      print(`cab ${sub}: error: ${e}`, "err");
    }
  }

  const history = [];
  let cursor = 0, busy = false;
  async function submit(line) {
    if (busy) return;
    busy = true; input.disabled = true;
    print(`${PROMPT} ${line}`, "cmdline");
    if (line.trim()) { history.push(line); cursor = history.length; }
    await exec(line);
    busy = false; input.disabled = false; input.value = "";
    if (box.contains(document.activeElement) || document.activeElement === document.body) input.focus({ preventScroll: true });
  }

  const words = ["cab run", "cab run --dry-run", "cab list", "cab prune --keep ", "cab config", "cab --help", "help", "clear", "ls", "whoami"];
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submit(input.value); }
    else if (e.key === "ArrowUp" && cursor > 0) { e.preventDefault(); input.value = history[--cursor]; }
    else if (e.key === "ArrowDown") { e.preventDefault(); cursor = Math.min(history.length, cursor + 1); input.value = history[cursor] || ""; }
    else if (e.key === "Tab") {
      const hit = words.find((w) => w.startsWith(input.value) && w !== input.value);
      if (hit) { e.preventDefault(); input.value = hit; }
    }
  });
  box.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-cmd]");
    if (chip) return submit(chip.dataset.cmd);
    if (!window.getSelection().toString()) input.focus({ preventScroll: true });
  });

  // type one command by itself the first time the terminal scrolls into view
  print("cab simulator. type 'help', or tap a command below. tab completes, arrows recall.", "dim");
  const io = new IntersectionObserver(async ([e]) => {
    if (!e.isIntersecting) return;
    io.disconnect();
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    for (const ch of "cab run") { input.value += ch; await wait(90); }
    await wait(250); submit(input.value);
  }, { threshold: 0.6 });
  io.observe(box);
})();
