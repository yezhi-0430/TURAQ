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
- **查看工具调用**：展开消息查看详细的工具调用记录
      `
    },

    market: {
      title: '市场看板使用教程',
      content: `
## 市场看板功能说明

实时追踪 A 股市场动态，快速掌握市场全貌。

### 主要功能

**1. 指数行情**
- 上证指数、深证成指、创业板指实时走势
- 当日涨跌幅、成交量、成交额
- 历史数据对比

**2. 个股搜索**
- 快速搜索股票代码或名称
- 查看个股详情页
- K线图、分时图切换

**3. 市场概览**
- 涨跌家数统计
- 涨停、跌停数量
- 市场情绪指标

### 使用方法

**查看个股详情：**
1. 在搜索框输入股票代码（如 600519）或名称（如 贵州茅台）
2. 点击搜索结果
3. 查看详细行情、K线图、技术指标

**查看板块行情：**
1. 切换到"板块"标签
2. 查看各行业板块涨跌幅
3. 点击板块名称查看成分股

**添加自选股：**
1. 在个股详情页点击"加自选"
2. 选择分组（可选）
3. 在自选股页面快速查看

### 数据说明

- **更新频率**：实时行情延迟约15分钟
- **交易时间**：周一至周五 9:30-11:30, 13:00-15:00
- **数据来源**：东方财富、新浪财经
- **历史数据**：支持查看日K、周K、月K

### 技术指标

**常用指标：**
- MA（移动平均线）：5日、10日、20日、60日
- MACD（异同移动平均线）：判断趋势
- KDJ（随机指标）：判断超买超卖
- RSI（相对强弱指标）：衡量涨跌力度
- BOLL（布林线）：判断压力支撑

**成交量指标：**
- VOL（成交量）：反映市场活跃度
- OBV（能量潮）：资金流向
- 换手率：衡量流动性
      `
    },

    risk: {
      title: '风险看板使用教程',
      content: `
## 风险看板功能说明

智能监控自选股风险，基于财报、公告和行情数据进行综合分析。

### 主要功能

**1. 监控范围设置**
- 选择自选股分组进行监控
- 指定具体股票分析
- 包含/排除未关联资料的股票

**2. 自动风险分析**
- AI 自动分析财报数据
- 解读重要公告内容
- 结合行情走势判断风险

**3. 资料管理**
- 自动获取最新财报和公告
- 手动补充资料
- 查看资料覆盖状态

### 使用方法

**开始分析：**
1. 选择"自选范围"（如"核心持仓"分组）
2. 可选择"指定股票"缩小范围
3. 选择"行情区间"（30/90/180天）
4. 点击"分析当前范围"开始

**查看分析结果：**
- **财报原文**：提取的关键财务数据
- **行情观测**：价格走势、技术指标
- **模型推断**：AI 综合分析的风险评估

**搜索分析：**
1. 在搜索框输入股票名称或代码
2. 选中搜索结果
3. 自动开始单独分析

### 风险等级说明

- **高风险**：发现明显负面信号，需重点关注
- **中风险**：存在一定风险因素，建议谨慎
- **低风险**：暂无明显风险，保持观察
- **信息不足**：资料缺失，无法准确判断

### 分析维度

**财务风险：**
- 盈利能力下滑
- 现金流紧张
- 负债率过高
- 应收账款异常

**经营风险：**
- 主营业务萎缩
- 市场份额下降
- 行业竞争加剧
- 政策影响

**市场风险：**
- 股价大幅波动
- 成交量异常
- 技术指标恶化
- 资金流出

### 注意事项

- 每只股票独立分析，可随时停止
- 离开页面后未完成项会保留
- 分析结果仅供参考，不构成投资建议
- 建议定期更新资料，保持分析准确性
      `
    },

    paper: {
      title: '模拟交易使用教程',
      content: `
## 模拟交易功能说明

零成本练习交易策略，在真实市场环境中提升交易技能。

### 主要功能

**1. 虚拟账户**
- 初始资金：100,000 元人民币
- 使用实时市场价格
- 遵循真实交易规则

**2. 交易操作**
- 买入：市价单快速成交
- 卖出：T+1 交易规则
- 撤单：未成交订单可撤销

**3. 资产管理**
- 实时查看持仓盈亏
- 历史交易记录
- 资金使用率分析

### 使用方法

**买入股票：**
1. 搜索股票代码或名称
2. 点击"买入"按钮
3. 输入买入数量（100股起，必须是100的整数倍）
4. 确认价格和金额
5. 点击"确认买入"

**卖出股票：**
1. 在"我的持仓"中找到要卖出的股票
2. 点击"卖出"按钮
3. 输入卖出数量（不超过可卖数量）
4. 确认价格和金额
5. 点击"确认卖出"

**查看账户：**
- **总资产**：现金 + 持仓市值
- **可用资金**：可用于买入的现金
- **持仓市值**：所有持仓的当前市值
- **盈亏**：总资产 - 初始资金

### 交易规则

**T+1 制度：**
- 当天买入的股票，次日才能卖出
- 卖出后资金立即可用
- 周末和节假日不可交易

**涨跌停限制：**
- 普通股票：±10%
- ST、*ST股票：±5%
- 达到涨跌停时无法成交

**交易时间：**
- 集合竞价：9:15-9:25（模拟交易不支持）
- 连续竞价：9:30-11:30, 13:00-15:00
- 盘后时间：无法下单

**交易单位：**
- 最小单位：100股（1手）
- 买入必须是100的整数倍
- 卖出可以不足100股（处理零股）

### 费用说明

**模拟交易免手续费：**
- 实际交易需要支付佣金（约万分之三）
- 实际交易卖出需缴纳印花税（千分之一）
- 模拟交易为了简化，暂不收取费用

### 策略建议

**风险控制：**
- 单只股票持仓不超过20%
- 设置止损点（如-8%自动卖出）
- 避免追涨杀跌

**仓位管理：**
- 不要满仓操作，保留一定现金
- 分批建仓，降低成本
- 根据市场情况调整仓位

**交易纪律：**
- 每次交易前制定计划
- 记录交易理由和结果
- 定期复盘总结经验
- 控制交易频率，避免过度交易

### 数据统计

- **胜率**：盈利交易次数 / 总交易次数
- **盈亏比**：平均盈利 / 平均亏损
- **最大回撤**：从最高点到最低点的跌幅
- **年化收益**：按时间折算的年度收益率
      `
    },

    watchlist: {
      title: '自选股使用教程',
      content: `
## 自选股功能说明

收藏关注的股票，快速追踪重点标的，提高研究效率。

### 主要功能

**1. 股票收藏**
- 添加自选股到收藏夹
- 按分组管理股票
- 快速查看重点股票

**2. 分组管理**
- 创建多个自选分组
- 自定义分组名称
- 将股票归类到不同分组

**3. 实时监控**
- 实时价格更新
- 涨跌幅排序
- 一键查看行情

### 使用方法

**添加自选股：**
1. 在市场看板搜索股票
2. 点击股票详情页的"加自选"按钮
3. 选择要添加到的分组
4. 添加成功后显示在自选股列表

**创建分组：**
1. 进入自选股页面
2. 点击"新建分组"
3. 输入分组名称（如"核心持仓"、"观察股"、"成长股"）
4. 确认创建

**移动股票：**
1. 在自选股列表中找到要移动的股票
2. 右键点击或长按（移动端）
3. 选择"移动到"
4. 选择目标分组

**删除自选股：**
1. 找到要删除的股票
2. 点击"删除"或右滑删除
3. 确认删除

### 分组建议

**按投资目的分组：**
- **核心持仓**：当前重点持有的股票
- **观察股**：准备买入的候选股票
- **长期关注**：长线价值投资标的
- **短线机会**：短期交易机会

**按行业分组：**
- **科技板块**：半导体、软件、互联网
- **消费板块**：白酒、食品、零售
- **金融板块**：银行、保险、证券
- **新能源**：光伏、锂电、新能源汽车

**按风格分组：**
- **蓝筹股**：大盘稳定股
- **成长股**：高成长潜力
- **周期股**：周期性行业
- **题材股**：热点概念股

### 使用技巧

**高效监控：**
- 每天开盘查看自选股涨跌情况
- 关注异动股票（涨跌幅超过5%）
- 定期清理不再关注的股票

**配合其他功能：**
- 在风险看板中监控自选股风险
- 在模拟交易中练习自选股操作
- 用AI研究助手分析自选股

**数据同步：**
- 自选股数据自动保存
- 刷新页面后数据仍在
- 建议定期导出备份

### 快捷操作

- **快速搜索**：使用搜索框快速定位股票
- **批量操作**：选中多只股票批量移动或删除
- **排序**：按涨跌幅、价格、名称排序
- **筛选**：按分组、行业、涨跌筛选

### 注意事项

- 自选股数量建议控制在50只以内
- 定期清理不再关注的股票
- 合理分组便于管理
- 自选股仅用于关注，不代表推荐买入
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
    const pageHeadings = document.querySelectorAll('.page-heading');

    pageHeadings.forEach((heading) => {
      // 避免重复添加
      if (heading.querySelector('.announcement-btn')) return;

      const btn = document.createElement('button');
      btn.className = 'btn announcement-btn';
      btn.type = 'button';
      btn.setAttribute('aria-label', '查看使用教程');
      btn.innerHTML = `
        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 16v-4M12 8h.01"/>
        </svg>
        使用教程
      `;

      // 根据页面确定教程类型
      const pageTitle = heading.querySelector('h1')?.textContent || '';
      let tutorialType = 'research';

      if (pageTitle.includes('市场')) {
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

      // 插入到 page-heading 的末尾（和其他按钮并列）
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
