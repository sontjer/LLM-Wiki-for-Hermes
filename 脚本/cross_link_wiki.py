#!/usr/bin/env python3
"""
LLM Wiki — 交叉链接增强脚本（通用版）
为 wiki/ 文档扫描全文，识别提及的其他分类实体，追加 [[wikilink]] 反向链接。

用法:
  python3 cross_link_wiki.py <库根>

示例:
  python3 cross_link_wiki.py /mnt/webdav/Study of Modern Japan
  python3 cross_link_wiki.py /mnt/webdav/Study of the National
"""

import sys, re
from pathlib import Path


def build_entity_index(wiki_dir):
    """扫描所有 wiki 文档，构建 {文件名: 分类} 索引"""
    index = {}
    seen_files = set()

    for cat_dir in wiki_dir.iterdir():
        if not cat_dir.is_dir():
            continue
        cat = cat_dir.name
        if cat.startswith('📑') or cat.startswith('📤') or cat in ('.hermes_cache', '.obsidian'):
            continue
        for f in cat_dir.glob('*.md'):
            stem = f.stem
            if stem not in seen_files:
                index[stem] = cat
                seen_files.add(stem)

    return index


def scan_and_link(wiki_dir, entity_index):
    """对每篇文档，识别文中出现的其他分类实体，追加反向链接"""
    total_enhanced = 0

    for cat_dir in wiki_dir.iterdir():
        if not cat_dir.is_dir():
            continue
        cat = cat_dir.name
        if cat.startswith('📑') or cat.startswith('📤') or cat in ('.hermes_cache', '.obsidian'):
            continue

        for f in sorted(cat_dir.glob('*.md')):
            try:
                content = f.read_text(encoding='utf-8')
            except:
                continue

            # 跳过已有本页提及段落的（避免重复增加）
            if '## 本页提及的相关条目' in content:
                continue

            # 在正文中查找其他分类的实体名
            found = set()
            text_before_section = content.split('## ')[0] if '## ' in content else content

            for entity, entity_cat in entity_index.items():
                if entity_cat == cat:
                    continue  # 同分类不跨链
                if len(entity) < 2:
                    continue
                if entity in text_before_section:
                    found.add((entity_cat, entity))

            if not found:
                continue

            # 追加段落
            parts = [content.rstrip(), '\n\n---\n## 本页提及的相关条目\n']
            for e_cat, e_name in sorted(found):
                parts.append(f'- [[{e_cat}/{e_name}]]')

            f.write_text(''.join(parts), encoding='utf-8')
            print(f"  ✓ {cat}/{f.stem}.md → {len(found)} 个跨分类链接")
            total_enhanced += 1

    return total_enhanced


def main():
    if len(sys.argv) < 2:
        vault = Path.cwd()
    else:
        vault = Path(sys.argv[1])

    wiki_dir = vault / 'wiki'
    if not wiki_dir.exists():
        print(f"❌ {wiki_dir} 不存在")
        sys.exit(1)

    print("=" * 50)
    print(f"  LLM Wiki — 交叉链接增强")
    print(f"  {vault.name}")
    print("=" * 50)

    print("\n📑 构建实体索引...")
    index = build_entity_index(wiki_dir)
    print(f"   索引 {len(index)} 个实体")

    print("\n🔗 扫描并追加跨分类链接...")
    enhanced = scan_and_link(wiki_dir, index)

    print(f"\n   已增强 {enhanced} 篇文档")
    print(f"\n{'=' * 50}")
    print(f"  ✅ 完成")
    print(f"{'=' * 50}")


if __name__ == '__main__':
    main()
