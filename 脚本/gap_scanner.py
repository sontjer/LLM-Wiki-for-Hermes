#!/usr/bin/env python3
"""
LLM Wiki — 知识缺口探测器（通用版）
自动发现知识库中"高频提及但未入库"的实体缺口。
无需领域知识，适用于任何主题的 LLM Wiki。

用法:
  python3 gap_scanner.py <库根>                    # 默认三支柱模式
  python3 gap_scanner.py <库根> --mode pattern     # 模式匹配（任何领域可用）
  python3 gap_scanner.py <库根> --mode wiki-cat    # Wikipedia分类爬取
  python3 gap_scanner.py <库根> --list entities.json  # 用已知实体清单

输出: .hermes_cache/gap_report.md
"""

import sys, re, json, time
from pathlib import Path
from collections import Counter

# ===== 四支柱模式匹配规则（通用，任何主题可用） =====

# 支柱1：人物后缀模式
PERSON_SUFFIX = [
    '天皇', '首相', '总统', '元帅', '大将', '将军', '上将', '中将',
    '少将', '大佐', '主席', '委员长', '总统', '总理', '议长',
    '部长', '大臣', '总督', '长官', '都督', '元帅', '提督',
]

# 支柱2：事件后缀模式
EVENT_SUFFIX = [
    '战争', '战役', '事变', '运动', '革命', '起义', '政变', '叛乱',
    '条约', '协定', '同盟', '公约', '宣言', '决议', '法案',
    '会议', '大会', '峰会', '谈判', '交涉',
    '袭击', '屠杀', '惨案', '爆炸', '灾难',
    '改革', '维新', '变法', '新政',
]

# 支柱3：机构后缀模式
ORG_SUFFIX = [
    '政府', '军队', '军', '省', '部', '厅', '署', '局', '处',
    '会', '银行', '舰队', '公司', '社', '党', '派', '团',
    '委员会', '司令部', '指挥部', '总部',
    '帝国', '王国', '共和国', '联邦', '联盟',
]

# 支柱4：概念后缀模式 —— 新增
CONCEPT_SUFFIX = [
    '主义', '论', '化', '观', '思想', '学说', '思潮',
    '制度', '体制', '模式', '政策', '方针', '战略', '路线',
    '理念', '原理', '原则', '精神', '文化',
]

# 通用停用词（各领域都应过滤的）
STOP_WORDS = set(
    '方面 成立 成功 能力 支持 计划 文化 公司 关系 方案 时期 利益 国家 '
    '作为 成为 不是 没有 通过 进行 发展 实现 进入 达到 提出 表示 指出 '
    '这些 那些 全部 主要 基本 重要 不同 各种 大量 极其 非常 特别 '
    '开始 结束 继续 已经 尚未 仍然 同时 由于 因此 从而 其中 之后 '
    '公里 万人 司令部 司令官 司令 任务 平民 左右 高地 集团 全体 合计'.split()
)


def load_wiki_entities(wiki_dir):
    """加载现有 wiki 所有实体名"""
    existing = set()
    for cat_dir in wiki_dir.iterdir():
        if not cat_dir.is_dir():
            continue
        name = cat_dir.name
        if name.startswith('📑') or name.startswith('📤') or name in ('.hermes_cache', '.obsidian'):
            continue
        for f in cat_dir.glob('*.md'):
            existing.add(f.stem)
    return existing


def extract_texts(raw_dir):
    """读取所有 raw 文件"""
    parts = []
    for f in sorted(raw_dir.glob('*.md')):
        try:
            parts.append(f.read_text(encoding='utf-8'))
        except:
            pass
    return '\n'.join(parts)


def pattern_discovery(text, existing):
    """
    四支柱模式匹配：从文本中发现未入库实体候选。
    适用于任何语言/主题的文本，无需外部知识。
    """
    candidates = Counter()

    # 支柱1：人物（姓氏前缀 + 后缀）
    for m in re.finditer(r'[\u4e00-\u9fff]{2,5}(?:' + '|'.join(PERSON_SUFFIX) + r')', text):
        name = m.group()
        if name not in existing and len(name) >= 2:
            candidates[name] += 1

    # 支柱2：事件（2-8字 + 战争/条约/运动 等）
    for m in re.finditer(r'[\u4e00-\u9fff]{2,10}(?:' + '|'.join(EVENT_SUFFIX) + r')', text):
        name = m.group()
        if name not in existing and 3 <= len(name) <= 12:
            candidates[name] += 1

    # 支柱3：机构（2-6字 + 政府/军/部/省/厅 等）
    for m in re.finditer(r'[\u4e00-\u9fff]{2,8}(?:' + '|'.join(ORG_SUFFIX) + r')', text):
        name = m.group()
        if name not in existing and 3 <= len(name) <= 10:
            candidates[name] += 1

    # 支柱4：概念（2-8字 + 主义/论/化/观/思想 等）
    for m in re.finditer(r'[\u4e00-\u9fff]{2,10}(?:' + '|'.join(CONCEPT_SUFFIX) + r')', text):
        name = m.group()
        if name not in existing and 3 <= len(name) <= 12:
            candidates[name] += 1

    return candidates


def list_discovery(text, existing, entity_list):
    """
    已知清单匹配：用外部实体清单做精确匹配。
    需要准备 entities.json，格式见示例。
    """
    counter = Counter()
    for name in entity_list:
        cnt = text.count(name)
        if cnt > 0 and name not in existing:
            counter[name] = cnt
    return counter


def guess_category(name):
    """根据实体名猜测分类"""
    if any(kw in name for kw in PERSON_SUFFIX):
        return '人物'
    elif any(kw in name for kw in EVENT_SUFFIX):
        return '事件'
    elif any(kw in name for kw in ORG_SUFFIX):
        return '政府与机构'
    elif any(kw in name for kw in CONCEPT_SUFFIX):
        return '概念与政策'
    return '概念与政策'


def print_report(candidates, vault, tag='模式匹配'):
    """输出分级报告并保存"""
    all_gaps = [(n, c) for n, c in candidates.most_common(120) if c >= 2]
    all_gaps.sort(key=lambda x: -x[1])

    print(f"\n  📌 共发现 {len(all_gaps)} 个候选缺口（频次≥2）\n")

    high = [(n, c) for n, c in all_gaps if c >= 5]
    medium = [(n, c) for n, c in all_gaps if 3 <= c < 5]

    if high:
        print(f"  ⭐ 高优先级（≥5次）:")
        for name, count in high[:15]:
            print(f"    [{guess_category(name)}] {name:<16} ×{count}")
    if medium:
        print(f"\n  ⭐⭐ 中优先级（3-4次）:")
        for name, count in medium[:15]:
            print(f"    [{guess_category(name)}] {name:<16} ×{count}")

    print(f"\n  📝 完整报告: {vault / '.hermes_cache' / 'gap_report.md'}")

    # 保存报告
    report = vault / '.hermes_cache' / 'gap_report.md'
    report.parent.mkdir(exist_ok=True)
    with open(report, 'w', encoding='utf-8') as f:
        f.write(f"# 知识缺口报告 — {vault.name}\n")
        f.write(f"模式: {tag}\n")
        f.write(f"生成: {time.strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("## 建议采集\n\n| 实体 | 频次 | 建议分类 |\n|------|------|---------|\n")
        for name, count in all_gaps[:60]:
            f.write(f"| {name} | ×{count} | {guess_category(name)} |\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    vault = Path(sys.argv[1])
    mode = 'pattern'
    list_path = None

    for i, arg in enumerate(sys.argv):
        if arg == '--mode' and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]
        elif arg == '--list' and i + 1 < len(sys.argv):
            list_path = Path(sys.argv[i + 1])
            mode = 'list'

    raw_dir = vault / 'raw'
    wiki_dir = vault / 'wiki'

    if not raw_dir.exists() or not wiki_dir.exists():
        print(f"❌ {vault} 不是有效的 LLM Wiki 库根")
        sys.exit(1)

    existing = load_wiki_entities(wiki_dir)
    all_text = extract_texts(raw_dir)

    print(f"═" * 55)
    print(f"  LLM Wiki 知识缺口探测器（通用版）")
    print(f"  库: {vault}")
    print(f"  模式: {mode}")
    print(f"  源文件: {len(list(raw_dir.glob('*.md')))} 篇")
    print(f"  已有实体: {len(existing)} 个")
    print(f"═" * 55)

    if mode == 'pattern':
        candidates = pattern_discovery(all_text, existing)
        print_report(candidates, vault, tag='三支柱模式匹配')

    elif mode == 'list':
        if not list_path or not list_path.exists():
            print("❌ 未指定实体清单文件 (--list entities.json)")
            sys.exit(1)
        with open(list_path, 'r', encoding='utf-8') as f:
            entity_list = json.load(f)
        candidates = list_discovery(all_text, existing, entity_list)
        print(f"📋 加载实体清单: {len(entity_list)} 个")
        print_report(candidates, vault, tag='已知清单匹配')

    elif mode == 'wiki-cat':
        # 模式3：Wikipedia 分类爬取（需要分类名参数）
        print("ℹ️  Wikipedia 分类模式: python3 gap_scanner.py <库根> --mode wiki-cat --cat '分类名'")
        print("   示例: python3 gap_scanner.py /path/to/vault --mode wiki-cat --cat '法国大革命'")

    else:
        print(f"❌ 未知模式: {mode}")
        sys.exit(1)


if __name__ == '__main__':
    main()
