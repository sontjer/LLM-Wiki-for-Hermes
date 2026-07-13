#!/usr/bin/env python3
"""
LLM Wiki — 链接完整性验证

用法:
  python3 validate_links.py /path/to/vault           # 验证 wiki 交叉链接
  python3 validate_links.py /path/to/vault --html    # 验证 HTML 人物跳转

检查项:
  1. wiki 中所有 [[分类/文件]] 链接 → 目标存在
  2. wiki 中所有 [[文件]] 链接（无前缀） → 文件名存在
  3. HTML 中所有 href="#person-XXX" → id="person-XXX" 存在
  4. HTML 中所有 era-figures 人物标签 → 对应人物卡片存在
  5. 总链接覆盖统计

退出码: 0 = 通过, 1 = 失败
"""

import sys, re
from pathlib import Path


def check_wiki_links(wiki_dir) -> tuple[list, dict]:
    """验证 wiki 目录下所有文件的交叉链接"""
    # 构建索引
    name_to_cat = {}   # filename → category
    for cat_dir in wiki_dir.iterdir():
        if not cat_dir.is_dir():
            continue
        cat = cat_dir.name
        if cat.startswith('📑') or cat.startswith('📤'):
            continue
        for f in cat_dir.glob('*.md'):
            name_to_cat[f.stem] = cat

    errors = []
    stats = {'linked_files': 0, 'total_links': 0, 'dead_links': 0, 'files_with_links': 0}

    for cat_dir in wiki_dir.iterdir():
        if not cat_dir.is_dir():
            continue
        cat = cat_dir.name
        if cat.startswith('📑') or cat.startswith('📤'):
            continue

        for f in sorted(cat_dir.glob('*.md')):
            content = f.read_text(encoding='utf-8', errors='replace')
            links_in_file = 0

            for m in re.finditer(r'\[\[([^\]]+)\]\]', content):
                stats['total_links'] += 1
                links_in_file += 1
                link = m.group(1)
                anchor = link.split('|')[0]

                if '/' in anchor:
                    # 带分类前缀 [[分类/名称]]
                    target_cat, target_name = anchor.split('/', 1)
                    if target_name not in name_to_cat:
                        errors.append(f"  ❌ {cat}/{f.stem}.md → [[{link}]] (文件不存在)")
                        stats['dead_links'] += 1
                    elif name_to_cat[target_name] != target_cat:
                        errors.append(f"  ⚠️  {cat}/{f.stem}.md → [[{link}]] (实际在 {name_to_cat[target_name]}/)")
                        stats['dead_links'] += 1
                else:
                    # 无前缀 [[名称]]，检查文件名
                    if anchor not in name_to_cat:
                        errors.append(f"  ❌ {cat}/{f.stem}.md → [[{anchor}]] (文件不存在)")
                        stats['dead_links'] += 1

            if links_in_file > 0:
                stats['linked_files'] += 1
                stats['files_with_links'] += 1

    return errors, stats


def check_html_links(html_path) -> tuple[list, dict]:
    """验证 HTML 文件中的人物跳转系统"""
    if not html_path.exists():
        return [f"  ❌ HTML 文件不存在: {html_path}"], {}

    html = html_path.read_text(encoding='utf-8')
    errors = []
    stats = {}

    # 1. 提取所有人物锚点和跳转链接
    anchors = set(re.findall(r'id="person-([^"]+)"', html))
    hrefs = re.findall(r'href="#person-([^"]+)"', html)

    stats['person_cards'] = len(anchors)
    stats['person_links'] = len(hrefs)

    # 2. 检查跳转链接是否有对应锚点
    linked = set(hrefs)
    missing = linked - anchors
    if missing:
        for m in sorted(missing):
            errors.append(f"  ❌ href=#person-{m} → 无对应人物卡片")
    
    # 3. 检查 era-figures 中的人物标签是否都有对应卡片
    era_links = set(re.findall(
        r'<div class="era-figures">.*?</div>',
        html, re.DOTALL
    ))
    era_names = set()
    for era in era_links:
        for m in re.finditer(r'href="#person-([^"]+)"', era):
            era_names.add(m.group(1))
    
    missing_from_era = era_names - anchors
    if missing_from_era:
        for m in sorted(missing_from_era):
            errors.append(f"  ❌ era-figures 标签 → {m} (无人物卡片)")
        stats['era_issues'] = len(missing_from_era)

    stats['era_links_total'] = len(era_names)
    stats['ok'] = len(errors) == 0
    return errors, stats


def main():
    if len(sys.argv) < 2:
        print("用法: python3 validate_links.py <库根> [--html]")
        sys.exit(1)

    vault = Path(sys.argv[1])
    check_html = '--html' in sys.argv
    all_errors = []
    
    # 检查项1: wiki 交叉链接
    wiki_dir = vault / 'wiki'
    if wiki_dir.exists():
        print(f"\n{'='*55}")
        print(f"  1️⃣  wiki 交叉链接验证")
        print(f"{'='*55}")
        errors, stats = check_wiki_links(wiki_dir)
        all_errors.extend(errors)
        
        total = stats.get('total_links', 0)
        dead = stats.get('dead_links', 0)
        print(f"  总链接数: {total}")
        print(f"  有链接的文件: {stats.get('files_with_links', 0)}")
        if dead == 0:
            print(f"  ✅ 所有 {total} 个链接有效")
        else:
            print(f"  ❌ {dead} 个错误链接:")
            for e in errors[:20]:
                print(e)
            if len(errors) > 20:
                print(f"  ... 还有 {len(errors)-20} 个")
    
    # 检查项2: HTML 人物跳转
    if check_html:
        output_dir = wiki_dir / '📤输出'
        html_files = list(output_dir.glob('*.html')) if output_dir.exists() else []
        
        if html_files:
            print(f"\n{'='*55}")
            print(f"  2️⃣  HTML 人物跳转系统验证")
            print(f"{'='*55}")
            
            for hf in html_files:
                print(f"\n  📄 {hf.name}")
                errors, stats = check_html_links(hf)
                all_errors.extend(errors)
                
                print(f"    人物卡片: {stats.get('person_cards', 0)}")
                print(f"    跳转链接: {stats.get('person_links', 0)}")
                if errors:
                    for e in errors:
                        print(e)
                else:
                    print(f"    ✅ 全部匹配")
    
    # 最终结果
    print(f"\n{'='*55}")
    if all_errors:
        print(f"  ❌ 发现 {len(all_errors)} 个问题")
        sys.exit(1)
    else:
        print(f"  ✅ 全部通过")
        print(f"{'='*55}")


if __name__ == '__main__':
    main()
