// Loaded synchronously in <head> so the saved light/dark choice applies before the first paint (no flash).
(function () {
  try {
    var saved = localStorage.getItem('mmc-theme');
    if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
  } catch (e) { /* storage blocked: follow the OS setting */ }
})();
