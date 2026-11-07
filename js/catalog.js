// Search and tag filtering for the catalog page (index.html).
// Every tag comes from the data-tags attribute on each exercise's <li>.
// The current search is kept in the URL (#tags=web,attack&q=sql) so it can be linked to.
(function () {
  "use strict";

  var PINNED = ["attack", "defense"];

  var $ = function (id) { return document.getElementById(id); };
  var searchEl = $("search");
  var cloudEl = $("tag-cloud");
  var activeEl = $("active-tags");
  var hintEl = $("hint");
  var countEl = $("result-count");
  var emptyEl = $("empty");
  var catalogEl = $("catalog");

  var selected = [];

  var entries = Array.prototype.map.call(catalogEl.children, function (li) {
    var tags = (li.getAttribute("data-tags") || "")
      .split(",")
      .map(function (t) { return t.trim().toLowerCase(); })
      .filter(Boolean);
    return {
      li: li,
      tags: tags,
      text: (li.textContent + " " + tags.join(" ")).toLowerCase()
    };
  });

  var allTags = [];
  entries.forEach(function (e) {
    e.tags.forEach(function (t) {
      if (allTags.indexOf(t) === -1) allTags.push(t);
    });
  });
  allTags.sort(function (a, b) {
    var pa = PINNED.indexOf(a), pb = PINNED.indexOf(b);
    if (pa !== -1 || pb !== -1) return (pa === -1 ? 99 : pa) - (pb === -1 ? 99 : pb);
    return a.localeCompare(b);
  });

  function tagButton(tag, label) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "tag";
    b.setAttribute("data-tag", tag);
    b.setAttribute("aria-pressed", "false");
    b.setAttribute("aria-label", "Filter by tag " + tag);
    b.textContent = label || tag;
    b.addEventListener("click", function () { toggle(tag); });
    return b;
  }

  // Filter panel
  var cloudButtons = {};
  allTags.forEach(function (tag, i) {
    if (i === PINNED.length) {
      var divider = document.createElement("span");
      divider.className = "tag-divider";
      cloudEl.appendChild(divider);
    }
    var b = tagButton(tag);
    var count = document.createElement("span");
    count.className = "count";
    b.appendChild(count);
    b.countEl = count;
    cloudEl.appendChild(b);
    cloudButtons[tag] = b;
  });

  // Tags on each exercise row
  var rowButtons = [];
  entries.forEach(function (e) {
    var list = document.createElement("ul");
    list.className = "tag-list";
    e.tags.forEach(function (tag) {
      var item = document.createElement("li");
      var b = tagButton(tag);
      rowButtons.push(b);
      item.appendChild(b);
      list.appendChild(item);
    });
    e.li.appendChild(list);
  });

  function terms() {
    return searchEl.value.toLowerCase().split(/\s+/).filter(Boolean);
  }

  function matches(entry, tags, words) {
    return tags.every(function (t) { return entry.tags.indexOf(t) !== -1; }) &&
      words.every(function (w) { return entry.text.indexOf(w) !== -1; });
  }

  // The tag that Enter would apply: an exact match, or the only tag starting with the text.
  function suggestedTag() {
    var q = searchEl.value.trim().toLowerCase();
    if (!q || /\s/.test(q)) return null;
    var candidates = allTags.filter(function (t) {
      return t.indexOf(q) === 0 && selected.indexOf(t) === -1;
    });
    if (candidates.indexOf(q) !== -1) return q;
    return candidates.length === 1 ? candidates[0] : null;
  }

  function toggle(tag) {
    var i = selected.indexOf(tag);
    if (i === -1) selected.push(tag); else selected.splice(i, 1);
    render();
  }

  function clearAll() {
    selected = [];
    searchEl.value = "";
    render();
    searchEl.focus();
  }

  function renderActive() {
    activeEl.textContent = "";
    activeEl.hidden = selected.length === 0;
    selected.forEach(function (tag) {
      var b = tagButton(tag);
      b.setAttribute("aria-pressed", "true");
      b.setAttribute("aria-label", "Remove tag " + tag);
      var x = document.createElement("span");
      x.className = "remove";
      x.setAttribute("aria-hidden", "true");
      x.textContent = "×";
      b.appendChild(x);
      b.addEventListener("click", function () { searchEl.focus(); });
      activeEl.appendChild(b);
    });
    if (selected.length > 1) {
      var clear = document.createElement("button");
      clear.type = "button";
      clear.className = "text-button";
      clear.textContent = "Clear tags";
      clear.addEventListener("click", function () {
        selected = [];
        render();
        searchEl.focus();
      });
      activeEl.appendChild(clear);
    }
  }

  function renderHint() {
    var tag = suggestedTag();
    hintEl.hidden = !tag;
    if (!tag) return;
    hintEl.textContent = "Press Enter to filter by tag ";
    var code = document.createElement("code");
    code.textContent = tag;
    hintEl.appendChild(code);
  }

  function writeHash() {
    var parts = [];
    if (selected.length) parts.push("tags=" + selected.map(encodeURIComponent).join(","));
    var q = searchEl.value.trim();
    if (q) parts.push("q=" + encodeURIComponent(q));
    var hash = parts.length ? "#" + parts.join("&") : "";
    if (hash === location.hash) return;
    try {
      history.replaceState(null, "", hash || location.pathname + location.search);
    } catch (e) { /* the page still works if the URL cannot be updated */ }
  }

  function readHash() {
    var params = new URLSearchParams(location.hash.slice(1));
    selected = (params.get("tags") || "")
      .split(",")
      .map(function (t) { return t.trim().toLowerCase(); })
      .filter(function (t, i, list) {
        return allTags.indexOf(t) !== -1 && list.indexOf(t) === i;
      });
    searchEl.value = params.get("q") || "";
  }

  function render() {
    var words = terms();

    var shown = 0;
    entries.forEach(function (e) {
      var on = matches(e, selected, words);
      e.li.hidden = !on;
      if (on) shown++;
    });

    // Each panel count is how many exercises would remain with that tag added.
    allTags.forEach(function (tag) {
      var b = cloudButtons[tag];
      var isOn = selected.indexOf(tag) !== -1;
      var n = entries.filter(function (e) {
        return matches(e, selected.concat(tag), words);
      }).length;
      b.countEl.textContent = n;
      b.setAttribute("aria-pressed", String(isOn));
      b.setAttribute("aria-label", "Filter by tag " + tag + ", " + n + (n === 1 ? " exercise" : " exercises"));
      b.disabled = n === 0 && !isOn;
    });

    rowButtons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(selected.indexOf(b.getAttribute("data-tag")) !== -1));
    });

    var total = entries.length;
    var filtering = selected.length > 0 || words.length > 0;
    countEl.textContent = filtering
      ? "Showing " + shown + " of " + total + " exercises"
      : total + " exercises";
    emptyEl.hidden = shown !== 0;

    renderActive();
    renderHint();
    writeHash();
  }

  searchEl.addEventListener("input", render);

  searchEl.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && searchEl.value) {
      ev.preventDefault();
      searchEl.value = "";
      render();
    } else if (ev.key === "Backspace" && !searchEl.value && selected.length) {
      selected.pop();
      render();
    }
  });

  $("search-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var tag = suggestedTag();
    if (tag) {
      selected.push(tag);
      searchEl.value = "";
      render();
    }
  });

  $("empty-clear").addEventListener("click", clearAll);

  window.addEventListener("hashchange", function () {
    readHash();
    render();
  });

  // The panel is always open on wide screens and starts collapsed on narrow ones.
  var wide = window.matchMedia("(min-width: 900px)");
  var panel = $("tag-panel");
  function syncPanel() { panel.open = wide.matches; }
  if (wide.addEventListener) wide.addEventListener("change", syncPanel);
  syncPanel();

  $("filters").hidden = false;
  $("toolbar").hidden = false;

  readHash();
  render();
})();
