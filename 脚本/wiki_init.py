#!/usr/bin/env python3
"""
wiki_init.py — LLM Wiki 全量初始化 + 增量同步脚本

功能：
1. 全量模式（默认）：扫描所有源文件 → 分类 → 复制 → 建链 → 生成索引
2. 增量模式 (--incremental)：对比 mtime，只处理源文件更新的文档

分类模式：
  --classify-mode keyword   → 关键词匹配（传统模式）
  --classify-mode embedding → Embedding 原型匹配（默认，需 SILICONFLOW_API_KEY）
  当 embedding API 不可用时自动降级为关键词匹配

定制方法：
1. 修改下面 SOURCE_DIR / WIKI_DIR 的路径
2. 修改 CATEGORIES 字典适配你的知识领域
3. 修改 CATEGORY_ICONS 字典的 emoji 图标
"""

import os, re, shutil, json, argparse, sys
from pathlib import Path

# ═══════════════════════════════════════════
# 配置区 — 按需修改
# ═══════════════════════════════════════════

# 源文件目录：你的原始笔记 .md 文件放在这里
SOURCE_DIR = '/path/to/your-notes'

# 工作区目录：AI 生成的 wiki 副本放在这里
WIKI_DIR = '/path/to/wiki-workspace'

# 跳过文件名前缀（以下划线/点开头等）
SKIP_PREFIXES = ('_', '.')

# ═══════════════════════════════════════════
# 分类规则 — 按你的知识领域修改
# 格式: '分类名': ['关键词1', '关键词2', ...]
# ═══════════════════════════════════════════

CATEGORIES = {
    'Cloudflare': ['cloudflare', 'cf ', 'argo', 'edgetunnel', '优选ip', '优选域名', 'worker', 'pages', 'cdn优选'],
    'Docker': ['docker', 'compose', 'portainer', '容器部署', '镜像'],
    'Linux': ['linux', 'ubuntu', 'debian', 'alpine', 'arch', 'kernel', 'systemd', 'manjaro', 'fedora'],
    '虚拟化': ['pve', 'proxmox', '虚拟机', 'lxc', 'esxi', 'all in one'],
    '代理': ['mihomo', 'clash', 'mosdns', 'sing-box', '订阅', '透明代理', '代理'],
    'VPN隧道': ['wireguard', 'jackal', 'snell', 'vpn', '隧道', 'udp2raw', 'phantun', 'openvpn'],
    '网络': ['iptables', 'nftables', '路由', 'ros', 'routeros', '软路由', 'openwrt', '转发'],
    '安全': ['安全', 'fail2ban', '渗透', 'osint', '加固', '防火墙'],
    '存储': ['nas', '群晖', '黑群', 'unraid', 'webdav', '存储'],
    'Windows': ['win11', 'internet explorer', 'windows'],
    '其他应用': ['duckduckgo', 'bt', 'tracker', 'yesplaymusic'],
    '开发工具': ['trae', 'github desktop', 'n8n', 'git'],
    'AI工具': ['notebooklm', 'mcp', 'chatgpt', 'clawdbot'],
    'Web开发': ['wordpress', 'bilibili', 'web'],
}

CATEGORY_ICONS = {
    'Cloudflare': '☁️', 'Docker': '🐳', 'Linux': '🐧',
    '虚拟化': '🖥️', '代理': '🔗', 'VPN隧道': '🔐',
    '网络': '🌐', '安全': '🛡️', '存储': '💾', '未分类': '📦',
}

CATEGORY_ORDER = list(CATEGORIES.keys()) + ['未分类']


# ═══════════════════════════════════════════
# 分类器（关键词保底）
# ═══════════════════════════════════════════

def classify_keyword(filename: str, content: str) -> str:
    """关键词匹配分类（保底方案）"""
    text = (filename + ' ' + content[:2000]).lower()
    scores = {}
    for cat, keywords in CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[cat] = score
    if not scores:
        return '未分类'
    return max(scores, key=scores.get)


# ═══════════════════════════════════════════
# Embedding 分类器（默认）
# ═══════════════════════════════════════════

_embed_classifier = None

def _ensure_embed_classifier():
    global _embed_classifier
    if _embed_classifier is not None:
        return _embed_classifier
    try:
        from embed_classifier import EmbeddingClassifier
        clf = EmbeddingClassifier(WIKI_DIR, CATEGORIES, CATEGORY_ORDER)
        clf.load_or_build()
        _embed_classifier = clf
        return clf
    except Exception as e:
        print(f"  ⚠️ embedding 分类器初始化失败: {e}")
        print("  使用关键词模式作为降级")
        return None


def classify_embedding(filename: str, content: str) -> str:
    clf = _ensure_embed_classifier()
    if clf is None:
        return classify_keyword(filename, content)
    return clf.classify(filename, content, fallback_classify_fn=classify_keyword)


classify = classify_embedding  # 默认


# ═══════════════════════════════════════════
# 文件操作
# ═══════════════════════════════════════════

def get_source_files():
    files = []
    for f in Path(SOURCE_DIR).glob('*.md'):
        if f.name.startswith(SKIP_PREFIXES):
            continue
        files.append(f)
    return sorted(files)


def copy_with_links(src_path: Path, dest_dir: str, related: list):
    dest_path = Path(WIKI_DIR) / dest_dir / src_path.name
    content = src_path.read_text(encoding='utf-8')
    if related:
        related = [r for r in related if r != src_path.name]
        if related:
            link_section = '\n\n## 关联文档\n\n'
            for r in related:
                link_section += f'- [[{r.replace(".md", "")}]]\n'
            if '## 关联文档' not in content:
                content += link_section
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(content, encoding='utf-8')
    return str(dest_path)


def get_desc(content: str) -> str:
    return content.strip()[:80].replace('\n', ' ').strip()


def update_index(category: str, entries: list):
    index_path = Path(WIKI_DIR) / '📑索引' / f'{category}.md'
    index_path.parent.mkdir(parents=True, exist_ok=True)
    icon = CATEGORY_ICONS.get(category, '📄')
    lines = [f'# {icon} {category}（{len(entries)} 篇）\n']
    lines.append(f'> 源文件目录 → Wiki 目录：`{category}/`\n')
    lines.append('')
    lines.append('| 文档 | 简介 |')
    lines.append('|------|------|')
    for entry in sorted(entries, key=lambda x: x['name']):
        name = entry['name'].replace('.md', '')
        lines.append(f'| [[{name}]] | {entry.get("desc", "")} |')
    lines.append('')
    index_path.write_text('\n'.join(lines), encoding='utf-8')
    return str(index_path)


def build_full_index(all_categories: dict):
    index_path = Path(WIKI_DIR) / '📑索引' / '00_全目录.md'
    index_path.parent.mkdir(parents=True, exist_ok=True)
    total = sum(len(v) for v in all_categories.values())
    lines = ['# 📚 全目录\n']
    lines.append(f'> 基于源笔记目录，共 {total} 篇文档。\n')
    lines.append('## 目录导航\n')
    for cat, entries in sorted(all_categories.items()):
        if not entries:
            continue
        lines.append(f'### {cat}（{len(entries)} 篇）\n')
        for e in entries:
            lines.append(f'- [[{e["name"].replace(".md", "")}]] — {e.get("desc", "")}')
        lines.append('')
    index_path.write_text('\n'.join(lines), encoding='utf-8')
    return str(index_path)


def scan_wiki_files(category_dirs: list) -> dict:
    existing = {}
    for cat in category_dirs:
        cat_path = Path(WIKI_DIR) / cat
        if not cat_path.exists():
            continue
        for f in cat_path.glob('*.md'):
            mtime = f.stat().st_mtime
            desc = get_desc(f.read_text(encoding='utf-8', errors='replace'))
            existing[f.name] = {'cat': cat, 'mtime': mtime, 'desc': desc}
    return existing


# ═══════════════════════════════════════════
# 全量模式
# ═══════════════════════════════════════════

def run_full():
    print('═' * 40)
    print('📦 全量模式：扫描全部源文件')
    print('═' * 40)
    files = get_source_files()
    print(f'📂 扫描到 {len(files)} 篇文档\n')
    categorized = {cat: [] for cat in CATEGORIES}
    categorized['未分类'] = []
    for f in files:
        content = f.read_text(encoding='utf-8', errors='replace')
        cat = classify(f.name, content)
        categorized[cat].append({'name': f.name, 'desc': get_desc(content), 'path': f})
    for cat, entries in sorted(categorized.items()):
        print(f'  {cat}: {len(entries)} 篇')
    print('\n📋 正在复制并建链...')
    copied_count = 0
    for cat, entries in categorized.items():
        dest = '未分类' if cat == '未分类' else cat
        all_in_cat = [e['name'] for e in entries]
        for e in entries:
            copy_with_links(e['path'], dest, all_in_cat)
            copied_count += 1
    print(f'✅ 已复制 {copied_count} 篇文档到分类目录')
    print('\n📑 正在生成索引...')
    for cat, entries in sorted(categorized.items()):
        if entries:
            print(f'  ✅ {cat} → {update_index(cat, entries)}')
    print(f'  ✅ 全目录 → {build_full_index(categorized)}')
    print(f'\n🎉 全量初始化完成！共 {copied_count} 篇文档入 Wiki。')


# ═══════════════════════════════════════════
# 增量模式
# ═══════════════════════════════════════════

def run_incremental():
    print('═' * 40)
    print('🔄 增量模式：仅同步已修改的源文件')
    print('═' * 40)

    category_dirs = list(CATEGORIES.keys()) + ['未分类']
    existing = scan_wiki_files(category_dirs)

    source_files = get_source_files()
    changed = []
    new_files = []
    for f in source_files:
        src_mtime = f.stat().st_mtime
        if f.name in existing:
            if src_mtime > existing[f.name]['mtime']:
                changed.append({'name': f.name, 'path': f, 'old_cat': existing[f.name]['cat']})
        else:
            new_files.append({'name': f.name, 'path': f})

    total_pending = len(changed) + len(new_files)
    if total_pending == 0:
        print('\n✅ 所有文档已是最新，无需同步。')
        return

    print(f'\n📂 待处理：')
    if changed:
        print(f'  🔄 已修改：{len(changed)} 篇')
        for c in sorted(changed, key=lambda x: x['name']):
            print(f'     - {c["name"]}（原分类：{c["old_cat"]}）')
    if new_files:
        print(f'  🆕 新文档：{len(new_files)} 篇')
        for n in sorted(new_files, key=lambda x: x['name']):
            print(f'     - {n["name"]}')

    print('\n📋 正在重新分类并复制...')
    affected_cats = set()
    copied_count = 0

    for c in changed:
        content = c['path'].read_text(encoding='utf-8', errors='replace')
        cat = classify(c['name'], content)
        affected_cats.add(c['old_cat']); affected_cats.add(cat)
        dest = '未分类' if cat == '未分类' else cat
        if cat != c['old_cat'] and c['old_cat'] != '未分类':
            old_path = Path(WIKI_DIR) / c['old_cat'] / c['name']
            if old_path.exists(): old_path.unlink()
        copy_with_links(c['path'], dest, [])
        copied_count += 1

    for n in new_files:
        content = n['path'].read_text(encoding='utf-8', errors='replace')
        cat = classify(n['name'], content)
        affected_cats.add(cat)
        copy_with_links(n['path'], '未分类' if cat == '未分类' else cat, [])
        copied_count += 1

    print(f'✅ 已同步 {copied_count} 篇文档')

    print('\n🔗 正在更新关联链接...')
    for cat in affected_cats:
        cat_dir = Path(WIKI_DIR) / cat
        if not cat_dir.exists(): continue
        all_md = sorted([f.name for f in cat_dir.glob('*.md')])
        for f in cat_dir.glob('*.md'):
            content = f.read_text(encoding='utf-8')
            if '## 关联文档' in content:
                content = content[:content.index('## 关联文档')].rstrip()
            related = [r for r in all_md if r != f.name]
            if related:
                link_section = '\n\n## 关联文档\n\n'
                for r in related:
                    link_section += f'- [[{r.replace(".md", "")}]]\n'
                content += link_section
            f.write_text(content, encoding='utf-8')
    print(f'  ✅ 已更新 {len(affected_cats)} 个分类的链接')

    print('\n📑 正在更新索引...')
    all_wiki = {}
    for cat_dir_name in category_dirs:
        cat_dir = Path(WIKI_DIR) / cat_dir_name
        if not cat_dir.exists(): continue
        entries = []
        for f in cat_dir.glob('*.md'):
            entries.append({'name': f.name, 'desc': get_desc(f.read_text(encoding='utf-8', errors='replace'))})
        if entries: all_wiki[cat_dir_name] = entries

    for cat in affected_cats:
        if cat in all_wiki:
            print(f'  ✅ {cat} → {update_index(cat, all_wiki[cat])}')

    print(f'  ✅ 全目录 → {build_full_index(all_wiki)}')
    print(f'\n🎉 增量同步完成！共处理 {total_pending} 篇文档。')


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LLM Wiki 初始化/增量同步')
    parser.add_argument('--incremental', '-i', action='store_true', help='增量模式')
    parser.add_argument('--classify-mode', choices=['keyword', 'embedding'],
                        default='embedding',
                        help='分类模式: keyword（关键词）或 embedding（语义，默认）')
    parser.add_argument('--rebuild-prototypes', action='store_true',
                        help='强制重建 embedding 原型（分类规则变化时使用）')
    args = parser.parse_args()

    if not Path(SOURCE_DIR).exists():
        print(f'❌ 源文件目录不存在：{SOURCE_DIR}')
        print('   请修改脚本开头 SOURCE_DIR 配置')
        sys.exit(1)
    if not Path(WIKI_DIR).exists():
        print(f'❌ 工作区目录不存在：{WIKI_DIR}')
        print('   请修改脚本开头 WIKI_DIR 配置')
        sys.exit(1)

    # 选择分类模式
    if args.classify_mode == 'keyword':
        print('🔧 分类模式: 关键词匹配（传统模式）')
        classify = classify_keyword
    else:
        print('🔮 分类模式: embedding 语义分类')
        classify = classify_embedding
        if args.rebuild_prototypes:
            try:
                from embed_classifier import EmbeddingClassifier
                clf = EmbeddingClassifier(WIKI_DIR, CATEGORIES, CATEGORY_ORDER)
                clf.load_or_build(force_rebuild=True)
                print('  ✅ 原型已重建')
            except Exception as e:
                print(f'  ⚠️ 重建失败: {e}')

    if args.incremental:
        run_incremental()
    else:
        run_full()
