"""
embed_classifier.py — Embedding 原型匹配分类器

原理：
1. 读取每个分类 Wiki 目录下的所有 .md 文件作为原型文档
2. 调用硅基流动 embedding API 向量化每篇文档
3. 计算每个分类的质心（平均向量）
4. 新文档 → 向量化 → 与各质心算余弦相似度 → 取最高分

依赖：
- pip install requests
- 环境变量 SILICONFLOW_API_KEY（硅基流动 API Key）
- 可选：SILICONFLOW_BASE_URL（默认 https://api.siliconflow.cn/v1）

降级：
- API 超时/失败 → 自动回退关键词匹配
- 相似度全低于阈值 → 归入"未分类"
"""

import os, json, sys, time
from pathlib import Path

# ════════ 配置 ════════
EMBED_MODEL = "Qwen/Qwen3-Embedding-4B"
EMBED_DIM = 2560           # Qwen3-Embedding-4B 实际维度
SIMILARITY_THRESHOLD = 0.35       # 低于此值归未分类
PROTOTYPE_CACHE_FILE = "prototype_embeddings.json"

# ════════ embedding API 调用 ════════

def _get_api_key():
    return os.environ.get('SILICONFLOW_API_KEY', '')

def _get_base_url():
    return os.environ.get('SILICONFLOW_BASE_URL', 'https://api.siliconflow.cn/v1')


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    批量 embedding，兼容 OpenAI 格式
    返回 list of vectors，每向量是 float list
    """
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
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBED_MODEL,
                "input": batch,
                "encoding_format": "float",
            },
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


# ════════ 原型管理 ════════

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


def build_prototypes(wiki_dir: str, categories: dict, category_order: list[str],
                     force_rebuild: bool = False) -> dict:
    """
    从 Wiki 工作区读取各分类文档，构建 embedding 质心
    返回: {分类名: [embedding_vector]}
    """
    if not force_rebuild:
        cached = load_prototypes(wiki_dir)
        if cached:
            all_cats = set(categories.keys()) | {'未分类'}
            if all_cats.issubset(cached.keys()):
                print(f"📦 使用缓存的 prototype embeddings（{len(cached)} 个分类）")
                return cached
            print("  ⚠️ 分类表变了，重新构建")

    print("🔮 正在构建 prototype embeddings...")

    all_texts = []
    text_cat_map = []

    for cat in category_order:
        cat_dir = Path(wiki_dir) / cat
        if not cat_dir.exists():
            continue

        md_files = sorted(cat_dir.glob('*.md'))
        if not md_files:
            continue

        print(f"  📖 {cat}: {len(md_files)} 篇")

        for f in md_files:
            name = f.stem
            text = name
            try:
                content = f.read_text(encoding='utf-8', errors='replace')[:500]
                text += ' ' + content
            except:
                pass
            all_texts.append(text)
            text_cat_map.append(cat)

    if not all_texts:
        print("  ⚠️ 没有找到任何文档")
        return {}

    print(f"  🚀 正在调用 embedding API（{len(all_texts)} 段文本）...")
    vectors = embed_texts(all_texts)
    print(f"  ✅ 完成，共 {len(vectors)} 个向量")

    cat_vectors = {cat: [] for cat in category_order}
    for cat, vec in zip(text_cat_map, vectors):
        cat_vectors[cat].append(vec)

    prototypes = {}
    for cat, vecs in cat_vectors.items():
        if not vecs:
            continue
        centroid = [sum(dims) / len(vecs) for dims in zip(*vecs)]
        prototypes[cat] = centroid

    save_prototypes(wiki_dir, prototypes)
    print(f"  💾 已缓存到 {get_cache_path(wiki_dir)}")

    return prototypes


# ════════ 分类器 ════════

class EmbeddingClassifier:
    """Embedding 原型匹配分类器"""

    def __init__(self, wiki_dir: str, categories: dict,
                 category_order: list[str] = None):
        self.wiki_dir = wiki_dir
        self.categories = categories
        self.category_order = category_order or list(categories.keys()) + ['未分类']
        self.prototypes = {}

    def load_or_build(self, force_rebuild: bool = False):
        self.prototypes = build_prototypes(
            self.wiki_dir, self.categories, self.category_order, force_rebuild
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
            sim = cosine_similarity(query_vec, centroid)
            scores[cat] = round(sim, 4)

        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]

        if best_score < SIMILARITY_THRESHOLD:
            return '未分类', scores, False

        return best_cat, scores, False
