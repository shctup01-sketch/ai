#!/bin/sh
# Wraps game.html (artifact fragment) into a standalone, installable index.html.
# Each build gets a version stamp; the running app compares it with version.json
# on the server and offers to reload when a newer build is out.
cd "$(dirname "$0")"
VER="$(date -u +%Y%m%d-%H%M%S)"
printf '{"v":"%s"}\n' "$VER" > version.json
{
  printf '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
  printf '<title>공룡 상단</title>\n'
  printf '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">\n'
  printf '<meta name="theme-color" content="#1c1711">\n<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="mobile-web-app-capable" content="yes">\n'
  printf '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n<meta name="apple-mobile-web-app-title" content="공룡 상단">\n'
  printf '<link rel="manifest" href="manifest.webmanifest">\n<link rel="icon" href="icon-192.png">\n<link rel="apple-touch-icon" href="icon-192.png">\n'
  printf '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}[hidden]{display:none!important}\n'
  printf '#upd{position:fixed;left:50%%;top:calc(10px + env(safe-area-inset-top,0px));transform:translateX(-50%%);z-index:999;padding:11px 18px;border-radius:14px;border:2px solid #f3c79a;background:#d4763c;color:#1c120a;font:700 14px system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.5)}</style>\n'
  printf '<script>window.__VER="%s"</script>\n' "$VER"
  printf '</head>\n<body>\n'
  cat game.html
  printf '\n<button id="upd" hidden>새 패치가 있어요 · 눌러서 적용</button>\n'
  printf '<script>\n(function () {\n  var VER = "%s";\n' "$VER"
  cat <<'EOF'
  if (!/^https?:$/.test(location.protocol)) return;
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(function () {});
  var btn = document.getElementById('upd');
  btn.onclick = function () { try { save(); } catch (e) {} location.reload(); };
  function check() {
    fetch('version.json?t=' + Date.now(), { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && j.v && j.v !== VER) btn.hidden = false; }).catch(function () {});
  }
  setInterval(check, 120000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) check(); });
})();
</script>
EOF
  printf '</body>\n</html>\n'
} > index.html
