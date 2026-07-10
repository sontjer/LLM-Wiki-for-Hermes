"""
embed_classifier.py — Embedding 原型匹配分类器

原理：
1. 从源文件目录扫描所有 .md 文件，对每个分类用关键词打分筛选高置信文档
2. 高置信文档 → Qwen3-Embedding-4B 向量化 → 每个分类平均得质心
3. 新文档 → 向量化 → 与各质心算余弦相似度 → 取最高分

关键设计：质心只从源文件内容构建（不依赖 Wiki 目录），避免错分污染。
每篇文档要命中 ≥2 个分类关键词才能入选原型池。

依赖：
- pip install requests
- 环境变量 SILICONFLOW_API_KEY（硅基流动 API Key）
"""

import os, json, sys, time
from pathlib import Path

# ════════ 配置 ════════
EMBED_MODEL = "Qwen/Qwen3-Embedding-4B"
EMBED_DIM = 2560
SIMILARITY_THRESHOLD = 0.35        # 低于此值归未分类
PROTOTYPE_MIN_KEYWORD_HITS = 2     # 入选原型池的最低关键词命中数
PROTOTYPE_MAX_PER_CATEGORY = 10    # 每类最多取这么多篇
PROTOTYPE_CACHE_FILE = "prototype_embeddings.json"

# ════════ embedding API ════════

def _get_api_key():
    return os.environ.get('SILICONFLOW_API_KEY', '')

def _get_base_url():
    return os.environ.get('SILICONFLOW_BASE_URL', 'https://api.siliconflow.cn/v1')


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    import requests
    api_key = _get_api_key()
    base_url = _get_base_url()
    if not api_key:
        raise RuntimeError("SILICONFLOW_API_KEY 未设置")

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = requests.post(
            f"{base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": EMBED_MODEL, "input": batch, "encoding_format": "float"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Embedding API 返回 {resp.status_code}: {resp.text}")
        data = resp.json()
        sorted_data = sorted(data['data'], key=lambda x: x['index'])
        all_embeddings.extend([item['embedding'] for item in sorted_data])
        if i + batch_size < len(texts):
            time.sleep(0.5)
    return all_embeddings


# ════════ 余弦相似度 ════════

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(av * bv for av, bv in zip(a, b))
    norm_a = sum(av * av for av in a) ** 0.5
    norm_b = sum(bv * bv for bv in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ════════ 关键词打分 ════════

def keyword_score(filename: str, content: str, keywords: list[str]) -> int:
    """统计文档命中关键词的次数（保底分类用）"""
    text = (filename + ' ' + content[:2000]).lower()
    return sum(1 for kw in keywords if kw in text)


# ════════ 原型构建（从源文件，不从Wiki目录）════════

def get_cache_path(wiki_dir: str) -> str:
    return os.path.join(wiki_dir, '.hermes_cache', PROTOTYPE_CACHE_FILE)


def load_prototypes(wiki_dir: str) -> dict:
    cache_path = get_cache_path(wiki_dir)
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return json.load(f)
    return {}


def save_prototypes(wiki_dir: str, prototypes: dict):
    cache_path = get_cache_path(wiki_dir)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(prototypes, f)


def score_source_docs_for_category(source_dir: str, category: str,
                                    keywords: list[str]) -> list[tuple]:
    """
    对源文件目录扫一遍，返回该分类的高置信文档列表

    返回: [(Path, score, title_preview), ...]
    按 score 降序，最多 PROTOTYPE_MAX_PER_CATEGORY 篇
    """
    scored = []
    for f in Path(source_dir).glob('*.md'):
        if f.name.startswith('_') or f.name.startswith('.'):
            continue
        try:
            content = f.read_text(encoding='utf-8', errors='replace')[:2000]
        except:
            continue
        score = keyword_score(f.name, content, keywords)
        if score >= PROTOTYPE_MIN_KEYWORD_HITS:
            preview = f.stem[:60]
            scored.append((f, score, preview))

    scored.sort(key=lambda x: -x[1])
    return scored[:PROTOTYPE_MAX_PER_CATEGORY]


def build_prototypes(source_dir: str, wiki_dir: str,
                     categories: dict, category_order: list[str],
                     force_rebuild: bool = False) -> dict:
    """
    从源文件目录构造清洁质心（不依赖 Wiki 目录）

    流程：
    1. 对每个分类，用关键词从源文件目录筛出高置信文档
    2. 只读这些文档的内容做 embedding
    3. 按分类平均得质心向量
    4. 缓存到 Wiki 目录下

    参数:
        source_dir: 源文件目录（IT/）
        wiki_dir:   Wiki 目录（用来放缓存）
        categories: 分类关键词字典
        category_order: 分类列表
        force_rebuild: 强制重建
    返回:
        {分类名: centroid_vector}
    """
    if not force_rebuild:
        cached = load_prototypes(wiki_dir)
        if cached:
            all_cats = set(categories.keys()) | {'未分类'}
            if all_cats.issubset(cached.keys()):
                print(f"📦 使用缓存的 prototype embeddings（{len(cached)} 个分类）")
                # 验证缓存是清洁构建的（简单检查：有 metadata 标记）
                if '_meta' in cached and cached['_meta'].get('build_from') == 'source':
                    return cached
                print("  ⚠️ 缓存来自旧版（Wiki 目录构建），重新构建")

    print("🔮 正在构建 prototype embeddings（从源文件筛选高置信文档）...")

    all_texts = []
    text_cat_map = []
    cat_doc_count = {}

    for cat in category_order:
        if cat == '未分类':
            continue  # 未分类没有关键词，跳过

        keywords = categories.get(cat, [])
        if not keywords:
            continue

        docs = score_source_docs_for_category(source_dir, cat, keywords)
        if not docs:
            print(f"  ⚠️ {cat}: 无高置信文档（关键词命中 ≥{PROTOTYPE_MIN_KEYWORD_HITS}）")
            continue

        cat_doc_count[cat] = len(docs)
        print(f"  📖 {cat}: {len(docs)} 篇高置信文档")

        for f, score, preview in docs:
            try:
                content = f.read_text(encoding='utf-8', errors='replace')[:500]
            except:
                content = ''
            text = f.stem + ' ' + content
            all_texts.append(text)
            text_cat_map.append(cat)

    if not all_texts:
        print("  ⚠️ 没有找到任何高置信文档")
        return {}

    print(f"  🚀 正在调用 embedding API（{len(all_texts)} 段文本）...")
    vectors = embed_texts(all_texts)

    # 按分类平均得质心
    cat_vectors = {cat: [] for cat in category_order if cat != '未分类'}
    for cat, vec in zip(text_cat_map, vectors):
        cat_vectors[cat].append(vec)

    prototypes = {}
    for cat, vecs in cat_vectors.items():
        if not vecs:
            continue
        centroid = [sum(dims) / len(vecs) for dims in zip(*vecs)]
        prototypes[cat] = centroid

    # 写入 metadata 标记清洁来源
    prototypes['_meta'] = {
        'build_from': 'source',
        'model': EMBED_MODEL,
        'dim': EMBED_DIM,
        'doc_count': cat_doc_count,
        'min_keyword_hits': PROTOTYPE_MIN_KEYWORD_HITS,
    }

    save_prototypes(wiki_dir, prototypes)
    print(f"  💾 已缓存到 {get_cache_path(wiki_dir)}")
    for cat, count in cat_doc_count.items():
        print(f"    {cat}: {count} 篇")

    return prototypes


# ════════ 分类器 ════════

class EmbeddingClassifier:
    """Embedding 原型匹配分类器"""

    def __init__(self, source_dir: str, wiki_dir: str,
                 categories: dict, category_order: list[str] = None):
        self.source_dir = source_dir
        self.wiki_dir = wiki_dir
        self.categories = categories
        self.category_order = category_order or list(categories.keys()) + ['未分类']
        self.prototypes = {}

    def load_or_build(self, force_rebuild: bool = False):
        self.prototypes = build_prototypes(
            self.source_dir, self.wiki_dir,
            self.categories, self.category_order,
            force_rebuild,
        )

    def classify(self, filename: str, content: str,
                 fallback_classify_fn=None) -> str:
        if not self.prototypes:
            if fallback_classify_fn:
                return fallback_classify_fn(filename, content)
            return '未分类'

        query_text = filename + ' ' + content[:500]

        try:
            vectors = embed_texts([query_text])
        except Exception as e:
            print(f"  ⚠️ Embedding API 失败: {e}，回退关键词模式")
            if fallback_classify_fn:
                return fallback_classify_fn(filename, content)
            return '未分类'

        query_vec = vectors[0]

        scores = {}
        for cat, centroid in self.prototypes.items():
            if cat == '_meta':
                continue
            sim = cosine_similarity(query_vec, centroid)
            scores[cat] = sim

        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]

        if best_score < SIMILARITY_THRESHOLD:
            return '未分类'

        return best_cat

    def classify_with_details(self, filename: str, content: str,
                              fallback_classify_fn=None) -> tuple:
        """返回: (分类名, {分类: 分数}, 是否用了fallback)"""
        if not self.prototypes:
            if fallback_classify_fn:
                return fallback_classify_fn(filename, content), {}, True
            return '未分类', {}, True

        query_text = filename + ' ' + content[:500]

        try:
            vectors = embed_texts([query_text])
        except Exception as e:
            print(f"  ⚠️ Embedding API 失败: {e}，回退关键词")
            if fallback_classify_fn:
                return fallback_classify_fn(filename, content), {}, True
            return '未分类', {}, True

        query_vec = vectors[0]

        scores = {}
        for cat, centroid in self.prototypes.items():
            if cat == '_meta':
                continue
            sim = cosine_similarity(query_vec, centroid)
            scores[cat] = round(sim, 4)

        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]

        if best_score < SIMILARITY_THRESHOLD:
            return '未分类', scores, False

        return best_cat, scores, False
