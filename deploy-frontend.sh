#!/usr/bin/env bash
# good-hobbies 前端一鍵部署到 GitHub Pages（靜態網站 → 推 gh-pages 分支）
# 前端是純靜態 HTML（非 Next），直接把 frontend/ 內容推上 gh-pages。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/frontend"

TMP="$(mktemp -d)"
echo "▶ 複製靜態檔到暫存…"
cp -R "$SRC/." "$TMP/"
rm -rf "$TMP/.git" "$TMP/.DS_Store"
touch "$TMP/.nojekyll"   # 讓 GitHub Pages 不要跑 Jekyll，保留 src/ 等資料夾

echo "▶ 推 gh-pages…"
cd "$TMP"
git init -q && git checkout -q -b gh-pages
git add -f -A
git -c user.email="lorie0779@gmail.com" -c user.name="lorie" commit -q -m "deploy $(date +%F_%T)"
git remote add origin https://github.com/lorie0779-stack/good-hobbies.git
git -c http.version=HTTP/1.1 -c http.postBuffer=524288000 push -f -q origin gh-pages
echo "✓ 完成 → https://lorie0779-stack.github.io/good-hobbies/"
rm -rf "$TMP"
