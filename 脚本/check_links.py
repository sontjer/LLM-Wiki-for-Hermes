#!/usr/bin/env python3
"""
抗日战争 LLM Wiki — 跨分类链接健康检查
检查双向链接完整性，输出人工需补充的缺失项

用法：
  python3 check_links.py
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path('/mnt/webdav/Study of War of Anti-Japan')
WIKI_DIR = BASE_DIR / 'wiki'

# 重点检测：战役必须有 [[人物xxx]] 链接，人物必须有 [[战役xxx]] 链接
# 格式说明：
#   关联文档段：[[古德里安]]（无前缀，Obsidian全库搜索）
#   本页提及段：[[战役/斯大林格勒战役]]（有前缀，跨分类区分）

def main():
    print("=" * 50)
    print("  抗日战争 LLM Wiki — 链接健康检查")
    print("  格式: 关联文档[[xxx]] / 本页提及[[分类/xxx]]")
    print("=" * 50)
    
    all_ok = True
    
    # 战役 → 检查有无 [[人物]]
    missing_battles = []
    for f in sorted((WIKI_DIR / '战役').glob('*.md')):
        content = f.read_text(encoding='utf-8')
        # 检查关联文档段 + 本页提及段 中的人物链接
        person_refs = content.count("[[人物/") + sum(content.count(f"[[{p}]]") for p in 
            [p.stem for p in (WIKI_DIR / '人物').glob('*.md') if p.stem != f.stem])
        if person_refs == 0:
            missing_battles.append(f.stem)
    
    if missing_battles:
        all_ok = False
        print(f"\n❌ 战役缺少人物链接 ({len(missing_battles)}篇):")
        for m in missing_battles:
            print(f"    - 战役/{m}.md")
    else:
        print(f"\n✅ 战役缺少人物链接: 全部正常")
    
    # 人物 → 检查有无 [[战役]]
    missing_persons = []
    for f in sorted((WIKI_DIR / '人物').glob('*.md')):
        content = f.read_text(encoding='utf-8')
        battle_refs = content.count("[[战役/") + sum(content.count(f"[[{b.stem}]]") for b in 
            (WIKI_DIR / '战役').glob('*.md') if b.stem != f.stem)
        if battle_refs == 0:
            missing_persons.append(f.stem)
    
    if missing_persons:
        all_ok = False
        print(f"\n❌ 人物缺少战役链接 ({len(missing_persons)}篇):")
        for m in missing_persons:
            print(f"    - 人物/{m}.md")
    else:
        print(f"\n✅ 人物缺少战役链接: 全部正常")
    
    if all_ok:
        print("\n🎉 全库跨分类链接完整。")
    else:
        print(f"\n⚠️  以上文件缺少跨分类链接，请手动补充。")
    
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
