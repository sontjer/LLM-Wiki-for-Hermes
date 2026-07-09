#!/usr/bin/env python3
"""
wiki_init.py — LLM Wiki 全量初始化脚本

功能：
1. 扫描源文件目录所有 .md 文件
2. 按 01_分类规则.md 的关键词表分类
3. 复制到工作区对应分类目录
4. 追加关联文档段落（同分类互链）
5. 生成 📑索引/ 目录页

定制方法：
1. 修改下面 SOURCE_DIR / WIKI_DIR 的路径
2. 修改 CATEGORIES 字典适配你的知识领域
3. 修改 CATEGORY_ICONS 字典的 emoji 图标
"""

import os, re, shutil, json
from pathlib import Path

# ═══════════════════════════════════════════
# 配置区 — 按需修改
# ═══════════════════════════════════════════

# 源文件目录：你的原始笔记 .md 文件放在这里
SOURCE_DIR = '/path/to/your-notes'

# 工作区目录：AI 生成的 wiki 副本放在这里
WIKI_DIR = '/path/to/wiki-workspace'

# 链接缓存文件（用于增量追踪）
LINK_CACHE_FILE = os.path.join(WIKI_DIR, '📑索引', '.link_cache.json')

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

# 分类 emoji 图标（可选）
CATEGORY_ICONS = {
    'Cloudflare': '☁️', 'Docker': '🐳', 'Linux': '🐧',
    '虚拟化': '🖥️', '代理': '🔗', 'VPN隧道': '🔐',
    '网络': '🌐', '安全': '🛡️', '存储': '💾', '未分类': '📦',
}


# ═══════════════════════════════════════════
# 核心逻辑 — 一般无需修改
# ═══════════════════════════════════════════

def classify(filename: str, content: str) -> str:
    """根据文件名和内容判断分类"""
    text = (filename + ' ' + content[:2000]).lower()
    scores = {}
    for cat, keywords in CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[cat] = score
    if not scores:
        return '未分类'
    return max(scores, key=scores.get)


def get_all_md_files():
    """获取源文件目录下所有 .md 文件，跳过已在 Wiki 中的"""
    existing = set()
    for root, dirs, files in os.walk(WIKI_DIR):
        for f in files:
            if f.endswith('.md') and not f.startswith('00_'):
                existing.add(f)

    files = []
    for f in Path(SOURCE_DIR).glob('*.md'):
        if f.name.startswith('_'):
            continue
        if f.name in existing:
            continue
        files.append(f)
    return sorted(files)


def copy_with_links(src_path: Path, dest_dir: str, related: list):
    """复制文件到目标目录，追加关联文档段落"""
    dest_path = Path(WIKI_DIR) / dest_dir / src_path.name

    content = src_path.read_text(encoding='utf-8')

    if related:
        related = [r for r in related if r != src_path.name]
        if related:
            link_section = '\n\n## 关联文档\n\n'
            for r in related:
                link_name = r.replace('.md', '')
                link_section += f'- [[{link_name}]]\n'
            if '## 关联文档' not in content:
                content += link_section

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(content, encoding='utf-8')
    return str(dest_path)


def update_index(category: str, entries: list):
    """更新分类索引页"""
    index_path = Path(WIKI_DIR) / '📑索引' / f'{category}.md'
    index_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    icon = CATEGORY_ICONS.get(category, '📄')

    lines.append(f'# {icon} {category}（{len(entries)} 篇）\n')
    lines.append(f'> 源文件目录 → Wiki 目录：`{category}/`\n')
    lines.append('')
    lines.append('| 文档 | 简介 |')
    lines.append('|------|------|')

    for entry in sorted(entries, key=lambda x: x['name']):
        name = entry['name'].replace('.md', '')
        desc = entry.get('desc', '')
        lines.append(f'| [[{name}]] | {desc} |')

    lines.append('')
    index_path.write_text('\n'.join(lines), encoding='utf-8')
    return str(index_path)


def build_full_index(all_categories: dict):
    """生成 00_全目录.md"""
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
            name = e['name'].replace('.md', '')
            desc = e.get('desc', '')
            lines.append(f'- [[{name}]] — {desc}')
        lines.append('')

    index_path.write_text('\n'.join(lines), encoding='utf-8')
    return str(index_path)


def main():
    files = get_all_md_files()
    print(f'📂 扫描到 {len(files)} 篇文档')

    categorized = {cat: [] for cat in CATEGORIES}
    categorized['未分类'] = []

    for f in files:
        content = f.read_text(encoding='utf-8', errors='replace')
        cat = classify(f.name, content)
        desc = content.strip()[:80].replace('\n', ' ').strip()
        categorized[cat].append({'name': f.name, 'desc': desc, 'path': f})

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
    for cat, entries in categorized.items():
        if entries:
            idx_path = update_index(cat, entries)
            print(f'  ✅ {cat} → {idx_path}')

    full_path = build_full_index(categorized)
    print(f'  ✅ 全目录 → {full_path}')

    print(f'\n🎉 LLM Wiki 初始化完成！')
    print(f'   修改上面 CATEGORIES 字典即可适配你的知识领域。')


if __name__ == '__main__':
    main()
