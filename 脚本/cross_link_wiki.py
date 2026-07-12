#!/usr/bin/env python3
"""
抗日战争 LLM Wiki — 交叉链接增强脚本
为所有 wiki/ 文档扫描全文，识别提及的其他分类实体，追加 [[wikilink]] 反向链接
"""

import os
import re
from pathlib import Path

# ============ 配置区（按需修改）============
BASE_DIR = Path('/mnt/webdav/Study of War of Anti-Japan')
WIKI_DIR = BASE_DIR / 'wiki'
CATEGORIES = ['战役', '人物', '装备与技术', '部队编制', '概念与政策', '时间线']
# ========================================

# ============ 构建所有实体的名称索引 ============
def build_entity_index(wiki_dir):
    """扫描所有 wiki 文档，构建 {文件名: 分类} 索引"""
    index = {}  # filename → category
    seen_files = set()

    for cat_dir in wiki_dir.iterdir():
        if not cat_dir.is_dir() or cat_dir.name.startswith('📑'):
            continue
        for f in cat_dir.glob('*.md'):
            name = f.stem
            index[name] = cat_dir.name
            seen_files.add((cat_dir.name, name))

    return index, seen_files


def scan_for_links(content, entity_index, source_cat, source_name):
    """扫描内容，找出所有提及的实体（中文名不设边界限制，只防过短匹配）"""
    matches = []

    for name, cat in sorted(entity_index.items(), key=lambda x: -len(x[0])):
        # 跳过自身和同分类（同分类已有关联文档）
        if cat == source_cat and name == source_name:
            continue

        # 对短名称（2字以下）额外谨慎
        if len(name) <= 1:
            continue

        # 全文搜索出现次数
        count = content.count(name)
        if count > 0:
            matches.append((cat, name, count))

    # 按出现次数降序排列（最相关的排前面）
    matches.sort(key=lambda x: -x[2])
    return matches


def generate_backlinks(matches, source_cat):
    """生成反向链接段落"""
    if not matches:
        return ''

    # 按分类分组
    by_cat = {}
    for cat, name, count in matches:
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append((name, count))

    # 排除同分类（已在关联文档中）
    lines = ['\n\n---\n## 本页提及的相关条目\n']
    for cat, items in by_cat.items():
        if cat == source_cat:
            continue
        if cat == '时间线':
            continue
        # 人物相关的排最前面作为 inline mention
        for name, count in items:
            lines.append(f'- [[{cat}/{name}]]')

    if len(lines) == 1:
        return ''

    return '\n'.join(lines)


def process_wiki_file(filepath, entity_index, source_cat, source_name):
    """处理一篇 wiki 文档"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 移除已有的「本页提及的相关条目」段落（如有）
    marker = '## 本页提及的相关条目'
    if marker in content:
        idx = content.find(marker)
        # 找到段落开始位置（前面的 --- 分隔符）
        section_start = content.rfind('\n---\n', 0, idx)
        if section_start == -1:
            section_start = content.rfind('---\n', 0, idx)
            if section_start == -1:
                section_start = idx
        content = content[:section_start].rstrip() + '\n'

    # 扫描提及
    matches = scan_for_links(content, entity_index, source_cat, source_name)
    if not matches:
        return False

    # 生成链接段落
    backlinks = generate_backlinks(matches, source_cat)
    if not backlinks:
        return False

    # 追加
    content = content.rstrip() + backlinks + '\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    # 统计
    cross_cat = len(set(cat for cat, _, _ in matches if cat != source_cat and cat != '时间线'))
    total_links = sum(1 for cat, _, _ in matches if cat != source_cat and cat != '时间线')
    print(f"  ✓ {source_cat}/{source_name}.md → {total_links} 个跨分类链接（{cross_cat} 个分类）")
    return True


def main():
    print("=" * 50)
    print("  抗日战争 LLM Wiki — 交叉链接增强")
    print("=" * 50)

    # 1. 构建实体索引
    print("\n📑 构建实体索引...")
    entity_index, seen_files = build_entity_index(WIKI_DIR)
    print(f"   索引 {len(entity_index)} 个实体")

    # 统计各分类
    by_cat = {}
    for name, cat in entity_index.items():
        by_cat.setdefault(cat, []).append(name)
    for cat, names in sorted(by_cat.items()):
        print(f"   {cat}: {len(names)} 个")

    # 2. 逐篇处理
    print("\n🔗 扫描并追加跨分类链接...")
    total_processed = 0
    total_linked = 0

    for cat_dir in WIKI_DIR.iterdir():
        if not cat_dir.is_dir() or cat_dir.name.startswith('📑'):
            continue
        cat = cat_dir.name
        for f in sorted(cat_dir.glob('*.md')):
            name = f.stem
            if process_wiki_file(f, entity_index, cat, name):
                total_processed += 1

    # Also process 索引 pages for cross-linking
    print("\n   📑索引页跳过（索引页已经是自动生成的）")

    print(f"\n   已增强 {total_processed} 篇文档")

    print("\n" + "=" * 50)
    print("  ✅ 交叉链接增强完成")
    print("=" * 50)


if __name__ == '__main__':
    main()
