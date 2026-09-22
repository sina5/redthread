/* Typing animation for the terminal demo on the front page.
 *
 * Every line below is real output from the commands shown, captured against
 * the CLI (paths and the remote are the only things swapped for readable
 * stand-ins). The same transcript is also server-rendered into the <pre> in
 * docs/index.md, so the demo reads fine without JS, in print, and under
 * prefers-reduced-motion — this file only wipes that copy and replays it a
 * line at a time. Edit one and you must edit the other.
 */
(function () {
  var STEPS = [
    {"note": "One-time setup. The store is an orphan branch of this repo — no second remote to provision."},
    { "cmd": "redthread init my-project --phases build,test,present --store ./redthread-store --worktree-repo .",
      "out": [
       "initialized store at redthread-store (phases: build, test, present)",
       "committed the store's scaffolding",
       "committed .redthread.yaml to the host repo (and gitignored the store directory)",
       "publishes: yes — the store has no remote, so nothing can leave this machine"
     ] },
    { "cmd": "claude mcp add redthread -- redthread mcp-serve --store ./redthread-store",
      "out": [
       "Added stdio MCP server redthread with command: redthread mcp-serve",
       "--store ./redthread-store to local config"
     ] },
    {"note": "Memory leaves the machine only once you say so."},
    { "cmd": "redthread publish --enable",
      "out": [
       "publishes: yes — publishing is enabled for this store",
       "(remote: git@github.com:acme/myproj.git)"
     ] },
    {"note": "Everything below is what your agent does over MCP — memory_write, memory_search, context_log."},
    { "cmd": "redthread memory write notes db-choice notes.md --description \"Why we picked Postgres\"",
      "out": [
       "written (pushed) — remote: git@github.com:acme/myproj.git"
     ] },
    { "cmd": "redthread memory list",
      "out": [
       "  notes/db-choice\tWhy we picked Postgres",
       "  sessions/2026-09-22_add-eval-worker\tAdded the eval worker; 412 tests green"
     ] },
    { "cmd": "redthread memory search postgres",
      "out": [
       "notes/db-choice\tPostgres over SQLite: the eval workers need concurrent writers."
     ] },
    {"note": "Pipeline context — build → test → present — lives in the same store."},
    { "cmd": "run_id=$(redthread run start)",
      "out": [] },
    { "cmd": "redthread log $run_id build note '{\"msg\": \"compiled 412 files in 31s\"}'",
      "out": [
       "01M34YFZ5K3T10D0CBJYDVW13P"
     ] },
    { "cmd": "redthread handoff publish $run_id build handoff.json",
      "out": [] },
    { "cmd": "redthread sync",
      "out": [
       "synced (pushed to git@github.com:acme/myproj.git)"
     ] },
    { "cmd": "redthread status",
      "out": [
       "store\t~/code/myproj/redthread-store (my-project)",
       "branch\tredthread-store [worktree]",
       "commits\tyes",
       "remote\tgit@github.com:acme/myproj.git",
       "publishes\tyes — publishing is enabled for this store",
       "unpushed\t0 commit(s)",
       "uncommitted\tnothing"
     ],
      "slow": [200, 120, 120, 120, 120, 120, 120] },
    {"note": "A different machine. Nothing on it but a git clone.", "rule": true},
    { "cmd": "git clone git@github.com:acme/myproj.git && cd myproj",
      "out": [
       "Cloning into 'myproj'...",
       "done."
     ],
      "slow": [600, 900] },
    { "cmd": "redthread attach",
      "out": [
       "attached redthread-store (worktree mode)"
     ],
      "slow": [900] },
    { "cmd": "redthread memory list",
      "out": [
       "  notes/db-choice\tWhy we picked Postgres",
       "  sessions/2026-09-22_add-eval-worker\tAdded the eval worker; 412 tests green"
     ],
      "slow": [400, 150] }
  ];

  var PAUSE_ICON =
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>';
  var PLAY_ICON =
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>';

  // Bumped on every (re)init so a loop left over from a previous page — the
  // theme's instant navigation keeps the document alive across pages — stops
  // writing into a <pre> that is no longer on screen.
  var generation = 0;

  function init() {
    // Selected by class, not id: the theme's content.code.copy pass renames
    // the ids of code blocks it adopts, and ours must stay findable.
    var term = document.querySelector(".rt-term-window .rt-term");
    var toggle = document.getElementById("rt-term-toggle");
    if (!term) return;

    generation += 1;
    var mine = generation;
    var alive = function () {
      return generation === mine && term.isConnected;
    };

    if (
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      // Leave the server-rendered transcript exactly as it is.
      if (toggle) toggle.hidden = true;
      return;
    }

    var paused = false;
    var waiters = [];
    var cursor = null;

    if (toggle) {
      toggle.hidden = false;
      toggle.onclick = function () {
        paused = !paused;
        toggle.setAttribute("aria-pressed", paused ? "true" : "false");
        toggle.setAttribute(
          "aria-label",
          paused ? "Play the terminal demo" : "Pause the terminal demo"
        );
        toggle.innerHTML =
          (paused ? PLAY_ICON : PAUSE_ICON) +
          "<span>" +
          (paused ? "Play" : "Pause") +
          "</span>";
        if (!paused) {
          while (waiters.length) waiters.shift()();
        }
      };
    }

    function held() {
      if (!paused) return Promise.resolve();
      return new Promise(function (resolve) {
        waiters.push(resolve);
      });
    }

    // Stepped so a pause takes effect mid-wait rather than after it.
    async function sleep(ms) {
      var left = ms;
      while (left > 0) {
        await held();
        if (!alive()) throw 0;
        var slice = Math.min(left, 50);
        await new Promise(function (r) {
          setTimeout(r, slice);
        });
        if (!paused) left -= slice;
      }
    }

    function esc(t) {
      return t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
    }

    function follow() {
      term.scrollTop = term.scrollHeight;
    }

    function newPrompt() {
      term.insertAdjacentHTML(
        "beforeend",
        '<span class="rt-term-prompt">$</span> <span class="rt-term-cmd"></span>'
      );
      var cmd = term.lastElementChild;
      cursor = document.createElement("span");
      cursor.className = "rt-term-cursor";
      term.appendChild(cursor);
      follow();
      return cmd;
    }

    async function typeCmd(text) {
      var span = newPrompt();
      for (var i = 0; i < text.length; i++) {
        span.textContent += text[i];
        follow();
        await sleep(text[i] === " " ? 70 : 25 + Math.random() * 35);
      }
      await sleep(320);
      if (cursor) cursor.remove();
      term.insertAdjacentHTML("beforeend", "\n");
    }

    async function printOut(lines, slow) {
      for (var i = 0; i < lines.length; i++) {
        await sleep(slow && slow[i] != null ? slow[i] : 110);
        term.insertAdjacentHTML(
          "beforeend",
          '<span class="rt-term-out">' + esc(lines[i]) + "</span>\n"
        );
        follow();
      }
    }

    async function printNote(text, rule) {
      // No trailing newline here: the note span is display:block, and a
      // newline after a block element inside a <pre> renders as a blank line.
      term.insertAdjacentHTML(
        "beforeend",
        '<span class="rt-term-note' +
          (rule ? " rt-term-rule" : "") +
          '"># ' +
          esc(text) +
          "</span>"
      );
      follow();
      await sleep(rule ? 900 : 550);
    }

    async function run() {
      for (;;) {
        term.innerHTML = "";
        term.scrollTop = 0;
        for (var i = 0; i < STEPS.length; i++) {
          var step = STEPS[i];
          if (step.note) {
            await printNote(step.note, step.rule);
            continue;
          }
          await typeCmd(step.cmd);
          await printOut(step.out, step.slow);
          await sleep(400);
        }
        newPrompt();
        await sleep(6000);
      }
    }

    run().catch(function () {
      /* superseded by a newer init, or the element went away */
    });
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(init);
  } else if (document.readyState !== "loading") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
