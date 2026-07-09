# HTML 生成模板

## 触发条件

用户说"输出为 HTML"、"生成信息图表"、"整理成好看页面"等关键词时执行。

## 工作流程

1. 理解用户问题 → 转化为搜索关键词
2. 语义搜索查找相关文档
3. 读取文档内容（优先读分类目录下的加工版，信息不足时读源文件）
4. 按下方 HTML 模板生成页面

## HTML 输出格式

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>主题 — LLM Wiki</title>
  <style>
    /* 干净简洁的风格 — 可根据需要修改 */
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 900px; margin: 0 auto; padding: 20px; line-height: 1.8;
           color: #333; background: #fafafa; }
    h1 { border-bottom: 2px solid #2563eb; padding-bottom: 8px; }
    h2 { color: #2563eb; margin-top: 28px; }
    pre { background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px;
          overflow-x: auto; }
    code { background: #e2e8f0; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }
    .info-box { background: #dbeafe; border-left: 4px solid #2563eb; padding: 12px;
                margin: 16px 0; border-radius: 4px; }
    .warn-box { background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px;
                margin: 16px 0; border-radius: 4px; }
    table { border-collapse: collapse; width: 100%; margin: 16px 0; }
    th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
    th { background: #2563eb; color: white; }
    .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #ddd;
              font-size: 0.85em; color: #666; }
  </style>
</head>
<body>
  <h1>标题</h1>
  <p class="info-box">摘要：一句话概括本文内容</p>

  <h2>一、XXXX</h2>
  <p>正文内容...</p>

  <h2>二、XXXX</h2>
  <p>正文内容...</p>

  <h2>参考资料</h2>
  <ul>
    <li>《源文档标题》— LLM Wiki</li>
    <li>《关联文档标题》— LLM Wiki</li>
  </ul>

  <div class="footer">
    由 AI Agent 基于 LLM Wiki 知识库生成 · 生成时间：YYYY-MM-DD
  </div>
</body>
</html>
```

## 输出规则

- 生成后保存到 `Wiki/📤输出/` 目录，文件名按 `YYYY-MM-DD_主题.html` 格式
- 引用来源必须写清楚来自哪篇文档
