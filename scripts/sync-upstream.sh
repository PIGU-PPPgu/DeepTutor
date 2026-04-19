#!/usr/bin/env bash
# sync-upstream.sh — 一键同步上游 HKUDS/DeepTutor 到本地 fork
#
# 用法：
#   ./scripts/sync-upstream.sh              # 同步并自动合并
#   ./scripts/sync-upstream.sh --dry-run    # 只查看有哪些更新，不合并
#   ./scripts/sync-upstream.sh --check      # 检查上游是否有新版本
#
# 冲突解决策略：
#   - capabilities/ 目录：保留我们的改动
#   - 前端 (web/)：优先上游
#   - 品牌名 (IntelliTutor)：保留我们的
#   - 其他：自动合并，失败则提示手动处理

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UPSTREAM_REMOTE="upstream"
UPSTREAM_URL="https://github.com/HKUDS/DeepTutor.git"
UPSTREAM_BRANCH="main"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

cd "$REPO_ROOT"

# ── Step 1: Ensure upstream remote ──
if ! git remote get-url "$UPSTREAM_REMOTE" &>/dev/null; then
    info "添加上游 remote: $UPSTREAM_URL"
    git remote add upstream "$UPSTREAM_URL"
fi

# ── Step 2: Fetch upstream ──
info "正在 fetch 上游更新..."
git fetch upstream "$UPSTREAM_BRANCH" 2>&1

# ── Step 3: Check for new commits ──
LOCAL_HEAD=$(git rev-parse HEAD)
UPSTREAM_HEAD=$(git rev-parse "upstream/$UPSTREAM_BRANCH")
COMMITS_BEHIND=$(git rev-list HEAD.."upstream/$UPSTREAM_BRANCH" --count)

if [ "$COMMITS_BEHIND" -eq 0 ]; then
    ok "已经是最新，无需同步。"
    exit 0
fi

info "上游有 ${COMMITS_BEHIND} 个新 commit："
git log --oneline HEAD.."upstream/$UPSTREAM_BRANCH" | head -20

# ── Dry run ──
if [ "${1:-}" = "--check" ]; then
    echo ""
    info "上游有新版本可用。运行 ./scripts/sync-upstream.sh 来同步。"
    exit 0
fi

if [ "${1:-}" = "--dry-run" ]; then
    info "Dry run 模式，不执行合并。"
    echo ""
    info "冲突预测："
    git diff --name-only HEAD "upstream/$UPSTREAM_BRANCH" | while read f; do
        # 检查是否是我们修改过的文件
        if git diff --name-only HEAD~10 HEAD | grep -q "^$f$"; then
            warn "可能冲突: $f"
        else
            echo "  无冲突: $f"
        fi
    done
    exit 0
fi

# ── Step 4: Stash local changes ──
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
    info "暂存本地改动..."
    git stash push -m "sync-upstream-auto-stash"
    STASHED=true
fi

# ── Step 5: Merge ──
info "开始合并上游 $UPSTREAM_BRANCH..."
MERGE_OK=true

if ! git merge "upstream/$UPSTREAM_BRANCH" --no-edit; then
    MERGE_OK=false
    CONFLICTS=$(grep -rl "<<<<<<< HEAD" --include="*.py" --include="*.tsx" --include="*.ts" --include="*.json" 2>/dev/null || true)

    if [ -z "$CONFLICTS" ]; then
        error "合并失败但没有发现冲突文件，请手动检查。"
        exit 1
    fi

    warn "发现 $(echo "$CONFLICTS" | wc -l) 个冲突文件，尝试自动解决..."

    for f in $CONFLICTS; do
        # 策略1: capability 文件 → 保留我们的
        if [[ "$f" == deeptutor/capabilities/* ]]; then
            info "保留我们的改动: $f"
            git checkout --ours "$f"
            git add "$f"
            continue
        fi

        # 策略2: 品牌名 → 保留 IntelliTutor
        if grep -q "IntelliTutor\|intellitutor" "$f" 2>/dev/null; then
            info "保留品牌名 (IntelliTutor): $f"
            # 用 Python 脚本精细解决
            python3 -c "
import re, sys
with open('$f') as fh:
    c = fh.read()
def keep_brand(m):
    ours, theirs = m.group(1), m.group(2)
    if 'intellitutor' in ours.lower() or 'IntelliTutor' in ours:
        return ours
    return theirs
c = re.sub(r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> upstream/main', keep_brand, c, flags=re.DOTALL)
with open('$f', 'w') as fh:
    fh.write(c)
" 2>/dev/null || true
            git add "$f"
            continue
        fi

        # 策略3: 前端 → 优先上游
        if [[ "$f" == web/* ]]; then
            info "采用上游版本: $f"
            git checkout --theirs "$f"
            git add "$f"
            continue
        fi

        # 策略4: 其他 → 保留我们的
        info "保留我们的改动: $f"
        git checkout --ours "$f"
        git add "$f"
    done

    # 检查是否还有未解决的冲突
    if grep -rl "<<<<<<< HEAD" --include="*.py" --include="*.tsx" --include="*.ts" --include="*.json" 2>/dev/null; then
        error "仍有未解决的冲突，请手动处理。"
        exit 1
    fi

    git commit --no-edit
    ok "冲突已自动解决并提交。"
fi

if [ "$MERGE_OK" = true ]; then
    ok "合并成功（无冲突）。"
fi

# ── Step 6: Restore stash ──
if [ "$STASHED" = true ]; then
    info "恢复本地改动..."
    git stash pop
fi

# ── Step 7: Summary ──
echo ""
ok "同步完成！"
echo "  上游: $UPSTREAM_URL ($UPSTREAM_BRANCH)"
echo "  合并: $COMMITS_BEHIND 个 commit"
echo "  当前: $(git rev-parse --short HEAD)"
echo ""
echo "  建议运行测试: pytest tests/ -x"
echo "  建议推送到远程: git push origin main"
