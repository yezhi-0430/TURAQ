/* 公告按钮和使用教程 */
(function() {
  'use strict';

  // 使用教程内容
  const tutorials = {
    research: {
      title: 'AI 研究助手使用教程',
      content: `
## 快速开始

AI 研究助手是您的智能研究伙伴，能够帮您快速分析股票、理解市场动态。

### 主要功能

**1. 智能对话**
- 输入问题，AI 自动调用工具查询数据
- 支持多轮对话，上下文连贯
- 每次对话最多 15 次工具调用

**2. 股票查询**
- 查询实时行情：\`查询 600519 的最新行情\`
- 分析技术指标：\`分析 600519 的 MACD 和 KDJ\`
- 对比多只股票：\`对比 600519 和 000858 的表现\`

**3. 市场分析**
- 板块分析：\`今日涨停板块有哪些？\`
- 资金流向：\`北向资金今日净流入情况\`
- 技术形态：\`找出突破 60 日均线的股票\`

### 使用技巧

**提问示例：**
- ✅ "贵州茅台最近的走势如何？"
- ✅ "帮我分析宁德时代的技术指标"
- ✅ "新能源板块今天表现怎么样？"

**注意事项：**
- 单次对话工具调用次数有限，复杂问题可分多次对话
- AI 分析仅供参考，不构成投资建议
- 数据更新可能存在延迟

### 快捷操作

- **新建对话**：点击右上角"新建对话"按钮
- **清除历史**：刷新页面重新开始
- **查看工具调用**：展开"工具记录"查看详细数据
      `
    },

    market: {
      title: '市场行情使用教程',
      content: `
## 市场行情

实时追踪 A 股市场动态，掌握最新行情数据。

### 主要功能

**1. 实时行情**
- 主要指数走势（上证、深证、创业板）
- 个股实时价格和涨跌幅
- 成交量和成交额统计

**2. 涨跌排行**
- 涨幅榜：当日涨幅最大的股票
- 跌幅榜：当日跌幅最大的股票
- 换手率排行：活跃度最高的股票

**3. 板块行情**
- 行业板块涨跌幅
- 概念板块热度排名
- 板块资金流向

### 使用方法

**查看个股：**
1. 在搜索框输入股票代码或名称
2. 点击搜索结果进入详情页
3. 查看 K 线图、技术指标、财务数据

**监控板块：**
1. 切换到"板块"标签
2. 查看各板块涨跌幅排名
3. 点击板块查看成分股

**设置提醒：**
- 设置价格提醒（即将上线）
- 设置涨跌幅提醒（即将上线）

### 数据说明

- **更新频率**：实时数据延迟 15 分钟
- **交易时间**：周一至周五 9:30-15:00
- **数据来源**：东方财富、新浪财经
      `
    },

    risk: {
      title: '风险看板使用教程',
      content: `
## 风险看板

智能监控市场风险，及时预警潜在问题。

### 主要功能

**1. 风险指标**
- 市场情绪指数（恐慌/贪婪）
- 波动率指标（VIX 类似）
- 资金流向监控

**2. 异常检测**
- 大单异动：单笔成交额超阈值
- 急涨急跌：短时间内波动过大
- 换手率异常：成交活跃度突变

**3. 风险预警**
- 个股风险评级（高/中/低）
- 持仓风险分析
- 止损建议

### 使用方法

**查看风险：**
1. 进入"风险看板"页面
2. 查看整体市场风险评分
3. 查看个股风险列表

**设置监控：**
1. 添加自选股到监控列表
2. 设置风险阈值
3. 开启消息通知

**理解指标：**
- **风险评分**：0-100，数值越高风险越大
- **波动率**：历史波动的标准差
- **资金流向**：净流入为正，净流出为负

### 注意事项

- 风险指标仅供参考，不构成投资建议
- 风险评估基于历史数据，不代表未来
- 建议结合基本面分析综合判断
      `
    },

    paper: {
      title: '模拟交易使用教程',
      content: `
## 模拟交易

零风险练习交易策略，提升实战技巧。

### 主要功能

**1. 虚拟账户**
- 初始资金：100,000 元
- 实时市场价格
- 真实交易规则

**2. 交易操作**
- 买入股票：市价单/限价单
- 卖出股票：T+1 交易规则
- 持仓管理：查看盈亏

**3. 交易记录**
- 历史成交记录
- 盈亏统计
- 策略回测

### 使用方法

**开始交易：**
1. 进入"模拟交易"页面
2. 搜索股票代码
3. 输入买入数量（100 股起）
4. 确认下单

**查看持仓：**
1. 查看当前持仓列表
2. 实时盈亏计算
3. 持仓占比分析

**卖出股票：**
1. 在持仓列表点击"卖出"
2. 输入卖出数量
3. 确认卖出（需满足 T+1 规则）

### 交易规则

- **T+1 制度**：今天买的股票明天才能卖
- **涨跌停限制**：ST 股票 ±5%，其他 ±10%
- **最小单位**：100 股（1 手）
- **手续费**：模拟交易免手续费

### 策略建议

- 设置止损点，控制风险
- 分散投资，不要重仓单只股票
- 记录每次交易的理由和结果
- 定期复盘，总结经验
      `
    },

    watchlist: {
      title: '自选股使用教程',
      content: `
## 自选股

收藏关注的股票，快速追踪重点标的。

### 主要功能

**1. 股票收藏**
- 添加自选股
- 分组管理
- 批量操作

**2. 实时监控**
- 价格变动提醒
- 涨跌幅排序
- 盈亏统计

**3. 数据分析**
- 技术指标概览
- 资金流向
- 关联新闻

### 使用方法

**添加自选：**
1. 搜索股票
2. 点击"加自选"按钮
3. 选择分组（可选）

**管理自选：**
1. 进入"自选股"页面
2. 查看所有自选股列表
3. 长按拖动调整顺序
4. 右滑删除

**分组管理：**
1. 创建分组（如"核心持仓"、"观察股"）
2. 拖动股票到不同分组
3. 快速切换分组查看

### 使用技巧

**高效监控：**
- 按涨跌幅排序，快速发现异动
- 设置自定义列，显示关心的指标
- 开启价格提醒，不错过机会

**分组建议：**
- 持仓股：当前持有的股票
- 观察股：准备买入的股票
- 长期关注：长线价值股

### 数据同步

- 自选股数据保存在云端
- 多设备自动同步
- 定期备份，防止丢失
      `
    }
  };

  // 简单的 Markdown 转 HTML
  function markdownToHtml(md) {
    let html = md.trim();

    // 转换标题
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');

    // 转换粗体标题
    html = html.replace(/^\*\*(.+?)\*\*$/gm, '<h4>$1</h4>');

    // 转换行内代码
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // 转换列表项
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');

    // 转换粗体
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // 转换段落
    html = html.split('\n\n').map(para => {
      if (para.startsWith('<h3>') || para.startsWith('<h4>') || para.startsWith('<li>')) {
        return para;
      }
      if (para.includes('<li>')) {
        return '<ul>' + para + '</ul>';
      }
      return '<p>' + para.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');

    return html;
  }

  // 显示公告
  function showAnnouncement(type) {
    const tutorial = tutorials[type];
    if (!tutorial) return;

    const dialog = document.getElementById('announcement-dialog');
    if (!dialog) return;

    document.getElementById('announcement-title').textContent = tutorial.title;
    document.getElementById('announcement-body').innerHTML = markdownToHtml(tutorial.content);

    dialog.showModal();
  }

  // 在每个页面标题旁添加公告按钮
  function addAnnouncementButtons() {
    const pageHeadings = document.querySelectorAll('.page-heading > div');

    pageHeadings.forEach((heading) => {
      // 避免重复添加
      if (heading.querySelector('.announcement-btn')) return;

      const btn = document.createElement('button');
      btn.className = 'announcement-btn';
      btn.type = 'button';
      btn.setAttribute('aria-label', '查看使用教程');
      btn.innerHTML = `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 16v-4M12 8h.01"/>
        </svg>
      `;

      // 根据页面确定教程类型
      const pageTitle = heading.querySelector('h1')?.textContent || '';
      let tutorialType = 'research';

      if (pageTitle.includes('市场') || pageTitle.includes('行情')) {
        tutorialType = 'market';
      } else if (pageTitle.includes('风险')) {
        tutorialType = 'risk';
      } else if (pageTitle.includes('模拟') || pageTitle.includes('交易')) {
        tutorialType = 'paper';
      } else if (pageTitle.includes('自选')) {
        tutorialType = 'watchlist';
      }

      btn.addEventListener('click', () => {
        showAnnouncement(tutorialType);
      });

      heading.appendChild(btn);
    });
  }

  // 初始化
  function init() {
    // 创建公告对话框
    const announcementDialog = document.createElement('dialog');
    announcementDialog.id = 'announcement-dialog';
    announcementDialog.className = 'announcement-dialog';
    announcementDialog.innerHTML = `
      <div class="announcement-content">
        <div class="announcement-header">
          <h2 id="announcement-title">使用教程</h2>
          <button class="announcement-close" type="button" aria-label="关闭">
            <svg class="icon"><use href="#i-x"/></svg>
          </button>
        </div>
        <div class="announcement-body" id="announcement-body">
          <!-- 教程内容将在这里显示 -->
        </div>
      </div>
    `;
    document.body.appendChild(announcementDialog);

    // 关闭对话框
    announcementDialog.querySelector('.announcement-close').addEventListener('click', () => {
      announcementDialog.close();
    });

    // 点击背景关闭
    announcementDialog.addEventListener('click', (e) => {
      if (e.target === announcementDialog) {
        announcementDialog.close();
      }
    });

    // 添加按钮
    addAnnouncementButtons();

    // 监听页面变化
    const observer = new MutationObserver(() => {
      addAnnouncementButtons();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  // 页面加载完成后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // 暴露到全局（供外部调用）
  window.showAnnouncement = showAnnouncement;
})();
