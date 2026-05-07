# learning_coach 在线资源获取代码与逻辑说明

本文档基于当前机器上的实际代码整理，说明 personal-learning-coach 在“每日学习内容”中如何获取在线资源、涉及哪些代码文件、调用了什么工具，以及各段代码的职责。

本文档已整理为独立资料包，文中涉及的代码文件均已复制到同目录下的 `./code/` 文件夹中，文内路径统一改为相对路径，便于单独查看、打包或转发。

## 1. 相关文件

本次核实的核心文件有：

1. `./code/coach.py`
2. `./code/content_pusher.py`
3. `./code/online_resource.py`

这 3 个文件构成了当前在线资源增强的主路径：

- `coach.py`：学习主流程入口
- `content_pusher.py`：每日内容组装与资源附加
- `online_resource.py`：在线搜索、抓取、解析、缓存

---

## 2. 总体调用链

当前在线资源获取的实际调用链如下：

1. 用户请求“今日学习内容”
2. `LearningCoach.get_daily_content(domain)` 被调用
3. `ContentPusher.format_daily_content(...)` 负责组装每日内容
4. `ContentPusher` 调用 `OnlineResourceFetcher.search_resources(...)`
5. `OnlineResourceFetcher`：
   - 先查缓存
   - 构造搜索词
   - 通过 `agent-browser` 打开 Google 搜索结果页
   - 通过 `agent-browser snapshot` 获取页面快照
   - 从快照文本中解析 URL
   - 去重、分类、缓存
6. 将结果拼接到“🌐 最新在线资源”板块
7. 返回给学习教练主流程输出

简化图示：

`./code/coach.py -> ./code/content_pusher.py -> ./code/online_resource.py -> subprocess -> agent-browser`

---

## 3. 入口代码：coach.py

文件：`./code/coach.py`

关键代码片段：

```python
126|    def get_daily_content(self, domain: str) -> Dict[str, Any]:
127|        """获取今日学习内容"""
128|        plan = self.data_manager.load_plan(domain)
...
136|        # 检查是否已经完成所有内容
137|        next_topic = self.content_pusher.get_next_topic(domain, plan)
...
155|        # 格式化每日内容
156|        daily_content = self.content_pusher.format_daily_content(
157|            domain,
158|            next_topic,
159|            plan.get("learning_style", "theory_practice")
160|        )
...
162|        return {
163|            "success": True,
164|            "content": daily_content,
165|            "topic": next_topic,
166|            "domain": domain
167|        }
```

### 逻辑说明

这段代码说明：

- `get_daily_content()` 是“每日学习内容”的入口。
- 它先根据学习计划找出当前要学习的 topic。
- 然后调用 `self.content_pusher.format_daily_content(...)`。
- 在线资源不是在 `coach.py` 里直接抓的，而是在内容格式化阶段被补进去。

也就是说：
`coach.py` 负责“触发”，不负责“具体抓取”。

---

## 4. 内容拼接代码：content_pusher.py

文件：`./code/content_pusher.py`

### 4.1 初始化在线资源抓取器

```python
8|from online_resource import OnlineResourceFetcher
...
14|    def __init__(self, data_manager, enable_online_resources: bool = True):
15|        self.data_manager = data_manager
16|        self.enable_online_resources = enable_online_resources
17|        self.online_fetcher = OnlineResourceFetcher() if enable_online_resources else None
```

#### 逻辑说明

- `ContentPusher` 默认启用在线资源功能。
- 只要 `enable_online_resources=True`，就会创建 `OnlineResourceFetcher()`。
- 因此当前系统的默认行为是：生成每日学习内容时，尝试附加在线资源。

### 4.2 在每日内容中插入在线资源

关键代码片段：

```python
55|    def format_daily_content(self,
56|                            domain: str,
57|                            topic: Dict[str, Any],
58|                            learning_style: str) -> str:
59|        """格式化每日学习内容，含在线资源"""
...
64|        # 尝试获取在线资源
65|        online_section = ""
66|        if self.online_fetcher:
67|            try:
68|                online_resources = self.online_fetcher.search_resources(
69|                    domain, topic_data["title"], max_results=3
70|                )
71|                if online_resources:
72|                    online_section = "\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n🌐 最新在线资源：\n"
73|                    for r in online_resources:
74|                        type_emoji = {"video": "🎬", "paper": "📄", "tutorial": "📝",
75|                                     "code": "💻", "documentation": "📖"}.get(r["type"], "🔗")
76|                        online_section += f'{type_emoji} {r["title"]}\n   {r["url"]}\n'
77|            except Exception:
78|                pass  # 在线资源获取失败不影响主流程
...
120|        content += online_section
```

#### 逻辑说明

这段代码体现了当前系统的几个关键点：

1. 每日内容格式化时才触发在线资源搜索。
2. 搜索参数是：
   - `domain`：学习领域，例如 `ai_agent`
   - `topic_data["title"]`：当前学习主题标题
   - `max_results=3`：默认最多取 3 条
3. 如果抓取成功，就会生成一个“🌐 最新在线资源”区块。
4. 如果抓取失败，会直接 `pass`，不会阻断主学习流程。

这说明当前实现采用的是“增强式设计”：
- 在线资源是附加值
- 抓取失败不影响每日学习内容主流程

---

## 5. 核心抓取与解析代码：online_resource.py

文件：`./code/online_resource.py`

这是整个在线资源机制的核心。

### 5.1 类定义与缓存目录

```python
13|class OnlineResourceFetcher:
14|    """在线资源获取器 - 使用 agent-browser 抓取最新学习资源"""
...
16|    def __init__(self, cache_dir: str = None):
17|        if cache_dir:
18|            self.cache_dir = Path(cache_dir)
19|        else:
20|            self.cache_dir = Path.home() / ".hermes" / "learning_coach" / "cache"
21|        self.cache_dir.mkdir(parents=True, exist_ok=True)
```

#### 逻辑说明

- `OnlineResourceFetcher` 是专门用于在线资源抓取的类。
- 默认缓存目录不是 satadisk，而是：
  `./code/cache`
- 初始化时会自动创建缓存目录。

这意味着：
当前资源搜索结果会落到本地缓存，避免重复抓取。

### 5.2 真正调用浏览器的代码

```python
23|    def _run_browser(self, url: str, action: str = "snapshot") -> Optional[str]:
24|        """使用 agent-browser 访问网页并获取内容"""
25|        try:
26|            result = subprocess.run(
27|                ["agent-browser", "navigate", url],
28|                capture_output=True, text=True, timeout=30
29|            )
30|            if result.returncode != 0:
31|                return None
32|            # 获取页面快照
33|            snap = subprocess.run(
34|                ["agent-browser", "snapshot"],
35|                capture_output=True, text=True, timeout=15
36|            )
37|            return snap.stdout if snap.returncode == 0 else None
38|        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
39|            print(f"浏览器访问失败: {e}")
40|            return None
```

#### 逻辑说明

这是当前实现里最关键的“外部工具调用点”。

实际调用了：

1. Python 标准库 `subprocess`
2. 外部 CLI 工具 `agent-browser`

实际命令流程是：

1. `agent-browser navigate <url>`
2. `agent-browser snapshot`

也就是说：
当前 personal-learning-coach 并没有直接调用 arXiv API、LangChain API、Chroma API 或 Pinecone API，而是通过浏览器自动化方式访问网页并抓取结果快照。

### 5.3 搜索入口：Google 搜索

```python
42|    def _run_search(self, query: str) -> Optional[str]:
43|        """通过 agent-browser 执行 Google 搜索"""
44|        search_url = f"https://www.google.com/search?q={query}"
45|        return self._run_browser(search_url)
```

#### 逻辑说明

这里可以明确看出：

- 当前实现的搜索入口是 Google 搜索 URL
- 不是结构化搜索 API
- 也不是站点定向抓取

因此，你之前列出的 MemGPT / Chroma / Pinecone 资源，在当前系统中属于“Google 搜索结果里可能被抓取出来的候选资源”。

### 5.4 缓存机制

```python
47|    def _get_cache_path(self, key: str) -> Path:
48|        """获取缓存文件路径"""
49|        safe_key = re.sub(r'[^\w]', '_', key)[:80]
50|        return self.cache_dir / f"{safe_key}.json"
...
52|    def _load_cache(self, key: str, max_age_hours: int = 24) -> Optional[List[Dict]]:
...
59|            cached_time = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
60|            age_hours = (datetime.now() - cached_time).total_seconds() / 3600
61|            if age_hours > max_age_hours:
62|                return None
63|            return data.get("resources", [])
...
67|    def _save_cache(self, key: str, resources: List[Dict]) -> None:
68|        """保存到缓存"""
69|        cache_path = self._get_cache_path(key)
70|        data = {
71|            "cached_at": datetime.now().isoformat(),
72|            "key": key,
73|            "resources": resources
74|        }
75|        cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
```

#### 逻辑说明

缓存逻辑分为三步：

1. 根据 `domain + topic + language` 生成缓存 key
2. 先从 JSON 文件中读取缓存
3. 若缓存未过期则直接返回，否则重新抓取

在 `search_resources()` 中，实际使用：

```python
96|        cache_key = f"{domain}_{topic}_{language}"
97|        cached = self._load_cache(cache_key, max_age_hours=12)
98|        if cached:
99|            return cached[:max_results]
```

所以当前搜索缓存有效期是：12 小时。

### 5.5 搜索主流程

```python
77|    def search_resources(self,
78|                        domain: str,
79|                        topic: str,
80|                        max_results: int = 5,
81|                        language: str = "zh") -> List[Dict[str, Any]]:
...
96|        cache_key = f"{domain}_{topic}_{language}"
97|        cached = self._load_cache(cache_key, max_age_hours=12)
98|        if cached:
99|            return cached[:max_results]
...
101|        # 构造搜索查询
102|        queries = self._build_search_queries(domain, topic, language)
103|        all_resources = []
...
105|        for query in queries:
106|            content = self._run_search(query)
107|            if content:
108|                extracted = self._parse_search_results(content, domain)
109|                all_resources.extend(extracted)
...
111|        # 去重（按URL）
112|        seen_urls = set()
113|        unique_resources = []
114|        for r in all_resources:
115|            url = r.get("url", "")
116|            if url and url not in seen_urls:
117|                seen_urls.add(url)
118|                unique_resources.append(r)
...
120|        resources = unique_resources[:max_results]
121|        if resources:
122|            self._save_cache(cache_key, resources)
123|
124|        return resources
```

#### 逻辑说明

`search_resources()` 是当前获取在线资源的主入口。它的完整流程是：

1. 查缓存
2. 如果没缓存，则构造多组搜索词
3. 对每个搜索词都执行一次 Google 搜索
4. 从每次搜索返回的快照文本里解析资源
5. 按 URL 去重
6. 截断到 `max_results`
7. 保存缓存
8. 返回结果

这说明当前实现是“多 query 聚合搜索”，不是只搜一次。

### 5.6 搜索词构造

```python
126|    def _build_search_queries(self, domain: str, topic: str, language: str) -> List[str]:
127|        """构建多个搜索查询"""
128|        queries = []
129|        if language == "zh":
130|            queries.append(f"{domain} {topic} 教程 学习")
131|            queries.append(f"{domain} {topic} 入门指南 2024 2025")
132|            queries.append(f"{topic} best tutorial guide")
133|        else:
134|            queries.append(f"{domain} {topic} tutorial guide")
135|            queries.append(f"{domain} {topic} best practices 2024 2025")
136|            queries.append(f"{topic} beginner advanced guide")
137|        return queries
```

#### 逻辑说明

搜索词不是固定写死某个链接，而是按 topic 动态生成。

例如如果 topic 是“记忆系统”，当前可能生成类似查询：

- `ai_agent 记忆系统 教程 学习`
- `ai_agent 记忆系统 入门指南 2024 2025`
- `记忆系统 best tutorial guide`

因此 MemGPT、Chroma、Pinecone 这类资源，很可能是通过这些 query 被搜索结果覆盖到。

### 5.7 搜索结果解析

```python
139|    def _parse_search_results(self, content: str, domain: str) -> List[Dict[str, Any]]:
140|        """
141|        解析搜索结果页面，提取资源链接
142|
143|        从 agent-browser 返回的 accessibility tree 中提取搜索结果
144|        """
145|        resources = []
146|        lines = content.split('\n')
147|
148|        for line in lines:
149|            # 尝试从快照中提取链接信息
150|            url_match = re.search(r'https?://[^\s\]\)"\']+', line)
151|            if not url_match:
152|                continue
153|
154|            url = url_match.group(0)
155|            # 过滤掉不相关的URL
156|            skip_domains = ['google.com', 'gstatic.com', 'googleapis.com',
157|                           'accounts.google', 'support.google']
158|            if any(skip in url for skip in skip_domains):
159|                continue
160|
161|            # 提取标题（链接前的文本）
162|            title = line[:url_match.start()].strip().strip('- []')
163|            if not title or len(title) < 5:
164|                title = "在线资源"
...
169|            resources.append({
170|                "title": title[:100],
171|                "url": url,
172|                "type": resource_type,
173|                "description": "",
174|                "source": self._extract_source(url)
175|            })
```

#### 逻辑说明

这里的解析逻辑并不是严格的 DOM 结构提取，而是：

1. 把 snapshot 文本按行拆分
2. 用正则匹配每行里的 URL
3. 过滤 Google 自身域名
4. 从 URL 前面的文本猜测标题
5. 打包成资源对象

所以当前解析方式比较轻量，但也相对脆弱。

### 5.8 资源分类

```python
179|    def _classify_resource(self, url: str, title: str) -> str:
180|        """判断资源类型"""
181|        url_lower = url.lower()
182|        title_lower = title.lower()
183|
184|        if any(x in url_lower for x in ['youtube.com', 'bilibili', 'vimeo']):
185|            return "video"
186|        if any(x in url_lower for x in ['arxiv.org', 'papers', 'research']):
187|            return "paper"
188|        if any(x in url_lower for x in ['github.com', 'gitlab']):
189|            return "code"
190|        if any(x in url_lower for x in ['docs', 'documentation', 'wiki']):
191|            return "documentation"
192|        if any(x in title_lower for x in ['教程', 'tutorial', 'guide', '入门']):
193|            return "tutorial"
194|        return "article"
```

#### 逻辑说明

当前系统会基于 URL 和标题，把资源分成：

- `video`
- `paper`
- `code`
- `documentation`
- `tutorial`
- `article`

因此你给出的示例资源大致会被识别为：

- MemGPT arXiv 论文 -> `paper`
- LangChain + Chroma 文档 -> `documentation` 或 `tutorial`
- Chroma 官方文档 -> `documentation`
- Pinecone 入门文章 -> `article` 或 `tutorial`

### 5.9 文章来源正文抓取

```python
207|    def fetch_article_content(self, url: str) -> Optional[str]:
208|        """获取文章的正文内容"""
209|        content = self._run_browser(url)
210|        if not content:
211|            return None
...
215|        text_lines = []
216|        for line in content.split('\n'):
217|            cleaned = re.sub(r'@\d+\s*', '', line).strip()
218|            if cleaned and len(cleaned) > 5:
219|                text_lines.append(cleaned)
220|
221|        return '\n'.join(text_lines[:200])  # 限制长度
```

#### 逻辑说明

除了“搜索资源列表”，当前模块还支持：

- 直接打开指定 URL
- 获取该页面快照
- 简单清洗文本
- 返回正文片段

这更适合在后续增强中做：
- 资源摘要
- 文章精读
- 自动摘录

### 5.10 热门话题获取

```python
224|    def get_trending_topics(self, domain: str) -> List[Dict[str, Any]]:
225|        """获取某个领域的热门话题"""
...
231|        queries = [
232|            f"{domain} latest news trends 2025",
233|            f"{domain} 最新趋势 热门话题"
234|        ]
```

#### 逻辑说明

这个函数说明 `OnlineResourceFetcher` 不只可以抓“学习资源”，还可以抓“热门趋势话题”。

虽然当前每日学习主流程主要用的是 `search_resources()`，但类本身已经预留了话题发现能力。

### 5.11 话题增强接口

```python
259|    def enrich_topic_with_online_resources(self,
260|                                           domain: str,
261|                                           topic: Dict[str, Any]) -> Dict[str, Any]:
...
270|        # 搜索话题相关资源
271|        main_resources = self.search_resources(domain, topic_title, max_results=3)
...
273|        # 搜索关键概念相关资源
274|        concept_resources = []
275|        for concept in key_concepts[:2]:
276|            cr = self.search_resources(domain, concept, max_results=2)
277|            concept_resources.extend(cr)
...
287|        # 补充到话题数据
288|        enriched = dict(topic)
289|        existing_resources = enriched.get("resources", [])
290|        enriched["online_resources"] = online_resources[:5]
291|        enriched["all_resources"] = existing_resources + online_resources[:3]
292|        enriched["enriched_at"] = datetime.now().isoformat()
```

#### 逻辑说明

这段代码展示了一个更完整的增强思路：

1. 先按话题标题搜资源
2. 再按关键概念搜资源
3. 合并去重
4. 回填到 topic 对象里

这比 `ContentPusher.format_daily_content()` 里当前直接按标题搜 3 条资源更完整。

说明：
- 当前代码库里已经有“深一点的增强接口”
- 但每日主流程现在主要还是简单调用 `search_resources(domain, title, max_results=3)`

---

## 6. 当前实际调用了什么工具

从代码实现看，当前在线资源获取链路实际使用到的工具/机制如下：

### 6.1 Python 标准库

- `subprocess`：启动外部命令
- `json`：缓存序列化
- `re`：正则匹配 URL
- `datetime`：缓存过期判断
- `pathlib.Path`：缓存目录与文件路径处理

### 6.2 外部命令行工具

- `agent-browser`

当前代码调用方式：

```bash
agent-browser navigate <url>
agent-browser snapshot
```

### 6.3 搜索源

- Google 搜索 URL

格式：

```text
https://www.google.com/search?q=<query>
```

### 6.4 本地缓存

- JSON 文件缓存
- 默认目录：`./code/cache`
- 资源搜索默认缓存有效期：12 小时
- 热门趋势默认缓存有效期：48 小时

---

## 7. 结合你给出的资源，当前系统会如何处理

如果当前学习主题与“记忆系统 / 向量数据库 / RAG / 长期记忆召回”有关，那么系统大概率会通过搜索词，抓到类似下面这类资源：

1. MemGPT 论文
   - `https://arxiv.org/abs/2310.08560`
   - 大概率分类为 `paper`

2. LangChain + Chroma 文档
   - `https://python.langchain.com/docs/integrations/vectorstores/chroma/`
   - 大概率分类为 `documentation` 或 `tutorial`

3. Chroma 官方文档
   - `https://docs.trychroma.com/docs/overview/introduction`
   - 大概率分类为 `documentation`

4. Pinecone 向量数据库文章
   - `https://www.pinecone.io/learn/vector-database/`
   - 大概率分类为 `article` 或 `tutorial`

但需要注意：
当前系统并不是把这 4 条资源写死在代码里，而是通过“主题搜索 -> 解析结果 -> 动态返回”的方式发现它们。

---

## 8. 当前实现的特点与局限

### 优点

1. 不依赖专门 API，接入快
2. 能按主题动态找资源
3. 有缓存，减少重复请求
4. 资源抓取失败不会影响学习主流程

### 局限

1. 目前通过 Google 搜索页面抓取，不够稳定
2. 解析方式依赖 snapshot 文本和正则，较脆弱
3. 没有对官方文档/论文源做强优先级排序
4. 默认缓存路径仍在 `./code/cache`
5. 当前每日主流程只取 3 条资源，较保守
6. 当前主流程主要按 topic title 搜索，还没有充分利用关键概念增强

---

## 9. 一句话总结

当前 personal-learning-coach 的在线资源获取逻辑是：

在生成每日学习内容时，由 `ContentPusher` 调用 `OnlineResourceFetcher`，后者通过 Python `subprocess` 启动 `agent-browser`，访问 Google 搜索页并抓取页面快照，再从快照文本中解析、分类和缓存资源链接，最后把这些资源追加到当天学习内容的“最新在线资源”板块中。

---

## 10. 后续可优化方向

如果要把这块做得更稳，建议后续可以考虑：

1. 为重要主题增加“精选资源白名单”
   - 如 MemGPT、Chroma、Pinecone 这类高价值链接
2. 搜索与精选混合
   - 自动搜索保证新鲜度
   - 精选资源保证质量底线
3. 优先官方文档/论文站点
   - arxiv / 官方 docs / 官方 blog / GitHub
4. 把缓存目录统一迁移到 `/home/crabin/satadisk/hermes_save`
5. 在每日主流程里使用 `enrich_topic_with_online_resources()` 做更完整增强
