// Small enhancements for exercise pages that use css/exercise.css.
// The page reads fine without this script.
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  // Contents: always open on wide screens, collapsed on narrow ones.
  var toc = document.querySelector(".toc");
  var wide = window.matchMedia("(min-width: 960px)");
  function syncToc() { if (toc) toc.open = wide.matches; }
  if (wide.addEventListener) wide.addEventListener("change", syncToc);
  syncToc();

  // Copy buttons on command and code blocks (not on sample output).
  document.querySelectorAll(".code:not(.output)").forEach(function (block) {
    var pre = block.querySelector("pre");
    if (!pre || !navigator.clipboard) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.setAttribute("aria-label", block.classList.contains("command") ? "Copy command" : "Copy code");
    button.addEventListener("click", function () {
      var lines = pre.querySelectorAll(".line");
      var text = lines.length
        ? Array.prototype.map.call(lines, function (l) { return l.textContent; }).join("\n")
        : pre.textContent.trim();
      navigator.clipboard.writeText(text).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 1500);
      }, function () {
        button.textContent = "Press Ctrl+C";
      });
    });
    block.appendChild(button);
  });

  // Highlight, in the contents, the last section whose start has scrolled past
  // the top third of the window.
  if (!toc) return;
  var links = Array.prototype.filter.call(
    toc.querySelectorAll('a[href^="#"]'),
    function (a) { return document.getElementById(a.getAttribute("href").slice(1)); }
  );
  var pending = false;
  function update() {
    pending = false;
    var line = window.innerHeight / 3;
    var current = links[0];
    links.forEach(function (a) {
      var target = document.getElementById(a.getAttribute("href").slice(1));
      if (target.getBoundingClientRect().top <= line) current = a;
    });
    links.forEach(function (a) {
      if (a === current) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
  }
  window.addEventListener("scroll", function () {
    if (!pending) { pending = true; requestAnimationFrame(update); }
  }, { passive: true });
  update();
})();
