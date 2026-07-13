#!/usr/bin/env python3
"""
Wikipedia 采集后校验工具 — 防止空文件/消歧义/短条目入库
用法:
  python3 check_collected.py /path/to/raw [--fix] [--min-size 500]
  
模式:
  check（默认）: 扫描 raw/ 下所有 .md，报告问题文件
  --fix: 对问题文件尝试用 --alt-titles 或英文版重采

输出:
  绿色 ✅ = 正常
  黄色 ⚠️ = 偏短但可能合理
  红色 ❌ = 需要重采
"""

import sys, re, os, subprocess
from pathlib import Path

# 默认最低字节（Wikipedia extract 少于这个数大概率是 stub 或下载失败）
MIN_SIZE = 500

# 已知的短条目白名单（这些条目确实就是短的）
SHORT_WHITELIST = {
    '第二次世界大战年表.md',  # 时间线本身就短
}


def validate_file(path: Path) -> dict:
    """检查单个 raw 文件的质量"""
    name = path.name
    size = path.stat().st_size
    issues = []

    if size == 0:
        issues.append('空文件')
    elif size < MIN_SIZE and name not in SHORT_WHITELIST:
        issues.append(f'文件过小 ({size} bytes)')
    
    if size > 0:
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
            
            # 检查是否为 HTML 页面（opencli 下载错误）
            if re.search(r'<!DOCTYPE html|<html', content[:200]):
                issues.append('HTML页面而非文本extract')
            
            # 检查是否为消歧义页
            if re.search(r'(消歧义|消歧義|disambiguation)', content[:1000]):
                issues.append('消歧义页面')
            
            # 检查是否只有尾部行（"来源：Wikipedia" 但无正文）
            if not re.search(r'\| extract \|', content) and not re.search(r'<!DOCTYPE html|<html', content[:200]):
                issues.append('缺少Wikipedia extract')
                
        except Exception as e:
            issues.append(f'读取失败: {e}')
    
    return {
        'name': name,
        'size': size,
        'issues': issues,
        'ok': len(issues) == 0
    }


def try_fix(path: Path, name: str, raw_dir: Path):
    """尝试修复问题文件"""
    # 备选标题列表（由文件名推测）
    alt_titles = []
    stem = path.stem  # 去掉 .md

    # 常见备选
    alt_map = {
        '地中海战场': '地中海戰區, Mediterranean and Middle East theatre of World War II',
        '虎式坦克': '虎I戰車',
        '哈尔西': '小威廉·海爾賽, 海爾賽',
        '阿拉曼战役': '第一次阿拉曼战役, 阿拉曼战役 (消歧义)',
        '休·道丁': 'Hugh Dowding, 第一代道丁男爵休·道丁',
        '大西泷治郎': '大西瀧治郎',
        '威廉·梅塞施密特': '威利·梅塞施密特',
        'B-29轰炸机': 'B-29超級堡壘轟炸機',
        '喷火战斗机': '噴火戰鬥機',
        '火炬行动': '火炬行動',
    }
    
    if stem in alt_map:
        candidates = [c.strip() for c in alt_map[stem].split(',')]
    else:
        # 尝试繁体和英文
        candidates = [stem]
        # 如果是简体中文，加繁体
        import unicodedata
        traditional = unicodedata.normalize('NFKC', stem)
        if traditional != stem:
            candidates.append(traditional)
    
    for title in candidates:
        lang = 'en' if re.match(r'^[a-zA-Z\s]', title) else 'zh'
        print(f"    尝试: {title} ({lang})")
        
        result = subprocess.run(
            ['opencli', 'wikipedia', 'page', title, '--lang', lang, '-f', 'md'],
            capture_output=True, text=True, timeout=15
        )
        
        # 清理污染
        clean = result.stdout
        for pattern in ['Update available:', 'Run: npm install', '^url: ']:
            clean = re.sub(pattern, '', clean, flags=re.MULTILINE)
        
        size = len(clean.encode('utf-8'))
        if size >= MIN_SIZE:
            path.write_text(clean, encoding='utf-8')
            print(f"    ✅ 修复完成: {size} bytes")
            return True
    
    return False


def main():
    fix_mode = '--fix' in sys.argv
    
    # 确定目标目录
    if len(sys.argv) >= 2 and not sys.argv[1].startswith('--'):
        raw_dir = Path(sys.argv[1])
    else:
        raw_dir = Path.cwd() / 'raw'
    
    if not raw_dir.exists():
        print(f"❌ {raw_dir} 不存在")
        sys.exit(1)
    
    md_files = sorted(raw_dir.glob('*.md'))
    print(f"\n📂 扫描 {len(md_files)} 个文件...\n")
    
    ok_count = 0
    warn_count = 0
    fail_count = 0
    fixes = 0
    
    for f in md_files:
        result = validate_file(f)
        if result['ok']:
            ok_count += 1
        else:
            issues_str = ' + '.join(result['issues'])
            if any('空文件' in i or '过小' in i or '消歧义' in i for i in result['issues']):
                fail_count += 1
                print(f"  ❌ {result['name']:<35} ({result['size']:>6} bytes) — {issues_str}")
                if fix_mode:
                    if try_fix(f, result['name'], raw_dir):
                        fixes += 1
            else:
                warn_count += 1
                print(f"  ⚠️  {result['name']:<35} ({result['size']:>6} bytes) — {issues_str}")
    
    print(f"\n{'='*50}")
    print(f"  ✅ 正常: {ok_count}   ⚠️ 偏短: {warn_count}   ❌ 需修复: {fail_count}")
    if fix_mode:
        print(f"  🔧 已修复: {fixes}")
    print(f"{'='*50}")
    
    if not fix_mode and fail_count > 0:
        print(f"\n💡 运行 python3 check_collected.py {raw_dir} --fix 自动修复")
    
    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    main()
