"""
私人学习教练 - 在线资源获取模块
通过 agent-browser 搜索和获取最新在线学习资源
"""
import json
import subprocess
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path


class OnlineResourceFetcher:
    """在线资源获取器 - 使用 agent-browser 抓取最新学习资源"""

    def __init__(self, cache_dir: str = None):
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(__file__).resolve().parent / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _run_browser(self, url: str, action: str = "snapshot") -> Optional[str]:
        """使用 agent-browser 访问网页并获取内容"""
        try:
            result = subprocess.run(
                ["agent-browser", "navigate", url],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                return None
            # 获取页面快照
            snap = subprocess.run(
                ["agent-browser", "snapshot"],
                capture_output=True, text=True, timeout=15
            )
            return snap.stdout if snap.returncode == 0 else None
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"浏览器访问失败: {e}")
            return None

    def _run_search(self, query: str) -> Optional[str]:
        """通过 agent-browser 执行 Google 搜索"""
        search_url = f"https://www.google.com/search?q={query}"
        return self._run_browser(search_url)

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        safe_key = re.sub(r'[^\w]', '_', key)[:80]
        return self.cache_dir / f"{safe_key}.json"

    def _load_cache(self, key: str, max_age_hours: int = 24) -> Optional[List[Dict]]:
        """加载缓存，超过 max_age_hours 小时则失效"""
        cache_path = self._get_cache_path(key)
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text(encoding='utf-8'))
            cached_time = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
            age_hours = (datetime.now() - cached_time).total_seconds() / 3600
            if age_hours > max_age_hours:
                return None
            return data.get("resources", [])
        except Exception:
            return None

    def _save_cache(self, key: str, resources: List[Dict]) -> None:
        """保存到缓存"""
        cache_path = self._get_cache_path(key)
        data = {
            "cached_at": datetime.now().isoformat(),
            "key": key,
            "resources": resources
        }
        cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def search_resources(self,
                        domain: str,
                        topic: str,
                        max_results: int = 5,
                        language: str = "zh") -> List[Dict[str, Any]]:
        """
        搜索某个主题的最新在线学习资源

        返回格式：
        [
            {
                "title": "资源标题",
                "url": "资源链接",
                "type": "article/tutorial/video/paper",
                "description": "简短描述",
                "source": "来源"
            }
        ]
        """
        cache_key = f"{domain}_{topic}_{language}"
        cached = self._load_cache(cache_key, max_age_hours=12)
        if cached:
            return cached[:max_results]

        # 构造搜索查询
        queries = self._build_search_queries(domain, topic, language)
        all_resources = []

        for query in queries:
            content = self._run_search(query)
            if content:
                extracted = self._parse_search_results(content, domain)
                all_resources.extend(extracted)

        # 去重（按URL）
        seen_urls = set()
        unique_resources = []
        for r in all_resources:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_resources.append(r)

        resources = unique_resources[:max_results]
        if resources:
            self._save_cache(cache_key, resources)

        return resources

    def _build_search_queries(self, domain: str, topic: str, language: str) -> List[str]:
        """构建多个搜索查询"""
        queries = []
        if language == "zh":
            queries.append(f"{domain} {topic} 教程 学习")
            queries.append(f"{domain} {topic} 入门指南 2024 2025")
            queries.append(f"{topic} best tutorial guide")
        else:
            queries.append(f"{domain} {topic} tutorial guide")
            queries.append(f"{domain} {topic} best practices 2024 2025")
            queries.append(f"{topic} beginner advanced guide")
        return queries

    def _parse_search_results(self, content: str, domain: str) -> List[Dict[str, Any]]:
        """
        解析搜索结果页面，提取资源链接

        从 agent-browser 返回的 accessibility tree 中提取搜索结果
        """
        resources = []
        lines = content.split('\n')

        for line in lines:
            # 尝试从快照中提取链接信息
            url_match = re.search(r'https?://[^\s\]\)"\']+', line)
            if not url_match:
                continue

            url = url_match.group(0)
            # 过滤掉不相关的URL
            skip_domains = ['google.com', 'gstatic.com', 'googleapis.com',
                           'accounts.google', 'support.google']
            if any(skip in url for skip in skip_domains):
                continue

            # 提取标题（链接前的文本）
            title = line[:url_match.start()].strip().strip('- []')
            if not title or len(title) < 5:
                title = "在线资源"

            # 判断资源类型
            resource_type = self._classify_resource(url, title)

            resources.append({
                "title": title[:100],
                "url": url,
                "type": resource_type,
                "description": "",
                "source": self._extract_source(url)
            })

        return resources

    def _classify_resource(self, url: str, title: str) -> str:
        """判断资源类型"""
        url_lower = url.lower()
        title_lower = title.lower()

        if any(x in url_lower for x in ['youtube.com', 'bilibili', 'vimeo']):
            return "video"
        if any(x in url_lower for x in ['arxiv.org', 'papers', 'research']):
            return "paper"
        if any(x in url_lower for x in ['github.com', 'gitlab']):
            return "code"
        if any(x in url_lower for x in ['docs', 'documentation', 'wiki']):
            return "documentation"
        if any(x in title_lower for x in ['教程', 'tutorial', 'guide', '入门']):
            return "tutorial"
        return "article"

    def _extract_source(self, url: str) -> str:
        """从URL提取来源名称"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            # 去掉 www.
            return re.sub(r'^www\.', '', domain)
        except Exception:
            return url

    def fetch_article_content(self, url: str) -> Optional[str]:
        """获取文章的正文内容"""
        content = self._run_browser(url)
        if not content:
            return None

        # 从 accessibility tree 提取文本内容
        # 去掉 ref 标记等，保留纯文本
        text_lines = []
        for line in content.split('\n'):
            # 跳过空的和纯标记行
            cleaned = re.sub(r'@\d+\s*', '', line).strip()
            if cleaned and len(cleaned) > 5:
                text_lines.append(cleaned)

        return '\n'.join(text_lines[:200])  # 限制长度

    def get_trending_topics(self, domain: str) -> List[Dict[str, Any]]:
        """获取某个领域的热门话题"""
        cache_key = f"{domain}_trending"
        cached = self._load_cache(cache_key, max_age_hours=48)
        if cached:
            return cached

        queries = [
            f"{domain} latest news trends 2025",
            f"{domain} 最新趋势 热门话题"
        ]

        all_topics = []
        for query in queries:
            content = self._run_search(query)
            if content:
                # 从搜索结果中提取话题
                topics = self._parse_search_results(content, domain)
                all_topics.extend(topics)

        # 去重
        seen = set()
        unique = []
        for t in all_topics:
            title = t.get("title", "")
            if title and title not in seen:
                seen.add(title)
                unique.append(t)

        result = unique[:10]
        if result:
            self._save_cache(cache_key, result)

        return result

    def enrich_topic_with_online_resources(self,
                                           domain: str,
                                           topic: Dict[str, Any]) -> Dict[str, Any]:
        """
        为学习话题补充在线资源

        在原有话题数据基础上，搜索并追加最新在线资源链接
        """
        topic_title = topic.get("title", "")
        key_concepts = topic.get("key_concepts", [])

        # 搜索话题相关资源
        main_resources = self.search_resources(domain, topic_title, max_results=3)

        # 搜索关键概念相关资源
        concept_resources = []
        for concept in key_concepts[:2]:
            cr = self.search_resources(domain, concept, max_results=2)
            concept_resources.extend(cr)

        # 合并去重
        all_urls = set()
        online_resources = []
        for r in main_resources + concept_resources:
            if r["url"] not in all_urls:
                all_urls.add(r["url"])
                online_resources.append(r)

        # 补充到话题数据
        enriched = dict(topic)
        existing_resources = enriched.get("resources", [])
        enriched["online_resources"] = online_resources[:5]
        enriched["all_resources"] = existing_resources + online_resources[:3]
        enriched["enriched_at"] = datetime.now().isoformat()

        return enriched
