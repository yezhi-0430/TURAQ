/**
 * 财报分析模块
 */

import { apiRequest } from './api.js';

// 上传并分析财报
export async function uploadFinancialReport(file, companyName) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('company_name', companyName);

    const response = await fetch('/api/analysis/upload?company_name=' + encodeURIComponent(companyName), {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '上传失败');
    }

    return await response.json();
}

// 测试分析（使用模拟数据）
export async function testAnalysis() {
    return await apiRequest('/api/analysis/test');
}

// 渲染分析结果
export function renderAnalysisResult(result, container) {
    const { company_name, indicators, ratios, risks, report } = result;

    // 清空容器
    container.innerHTML = '';

    // 创建结果容器
    const resultDiv = document.createElement('div');
    resultDiv.className = 'analysis-result';

    // 1. 公司概览
    const overviewSection = createSection('公司概览', `
        <div class="overview-grid">
            <div class="metric-card">
                <div class="metric-label">营业收入</div>
                <div class="metric-value">${formatMoney(indicators.revenue)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">净利润</div>
                <div class="metric-value">${formatMoney(indicators.net_profit)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">总资产</div>
                <div class="metric-value">${formatMoney(indicators.total_assets)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">总负债</div>
                <div class="metric-value">${formatMoney(indicators.total_liabilities)}</div>
            </div>
        </div>
    `);

    // 2. 财务比率
    const ratiosSection = createSection('财务比率', `
        <div class="ratios-grid">
            <div class="ratio-item">
                <span class="ratio-label">资产负债率</span>
                <span class="ratio-value ${ratios.debt_ratio > 0.7 ? 'danger' : 'normal'}">${(ratios.debt_ratio * 100).toFixed(2)}%</span>
            </div>
            <div class="ratio-item">
                <span class="ratio-label">流动比率</span>
                <span class="ratio-value ${ratios.current_ratio < 1 ? 'danger' : 'normal'}">${ratios.current_ratio.toFixed(2)}</span>
            </div>
            <div class="ratio-item">
                <span class="ratio-label">应收账款/营收</span>
                <span class="ratio-value ${ratios.receivable_ratio > 0.4 ? 'danger' : 'normal'}">${(ratios.receivable_ratio * 100).toFixed(2)}%</span>
            </div>
            <div class="ratio-item">
                <span class="ratio-label">现金流含金量</span>
                <span class="ratio-value ${ratios.cash_quality < 0.8 ? 'danger' : 'normal'}">${ratios.cash_quality.toFixed(2)}</span>
            </div>
        </div>
    `);

    // 3. 综合评分
    const scoreSection = createSection('综合评分', `
        <div class="score-container">
            <div class="score-circle ${getScoreClass(report.score)}">
                <div class="score-value">${report.score}</div>
                <div class="score-label">分</div>
            </div>
            <div class="score-details">
                <div class="recommendation">${report.recommendation}</div>
                <div class="action">${report.action}</div>
            </div>
        </div>
    `);

    // 4. 风险识别
    let risksHTML = '';
    if (risks.length === 0) {
        risksHTML = '<div class="no-risks">✓ 未检测到风险点</div>';
    } else {
        risksHTML = '<div class="risks-list">';
        risks.forEach((risk, index) => {
            risksHTML += `
                <div class="risk-item ${risk.level}">
                    <div class="risk-header">
                        <span class="risk-badge">${risk.level.toUpperCase()}</span>
                        <span class="risk-name">${risk.name}</span>
                    </div>
                    <div class="risk-details">
                        <div class="risk-value">
                            实际值: ${risk.value.toFixed(2)} | 阈值: ${risk.threshold.toFixed(2)}
                        </div>
                        ${risk.cases && risk.cases.length > 0 ? `
                            <div class="risk-cases">
                                历史案例: ${risk.cases.join('、')}
                            </div>
                        ` : ''}
                        ${risk.suggestions && risk.suggestions.length > 0 ? `
                            <div class="risk-suggestions">
                                <strong>建议:</strong>
                                <ul>
                                    ${risk.suggestions.map(s => `<li>${s}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        });
        risksHTML += '</div>';
    }

    const risksSection = createSection(`风险识别 (${risks.length}个)`, risksHTML);

    // 5. 风险统计
    const statsSection = createSection('风险统计', `
        <div class="risk-stats">
            <div class="stat-item high">
                <div class="stat-value">${report.risk_summary.high}</div>
                <div class="stat-label">高风险</div>
            </div>
            <div class="stat-item medium">
                <div class="stat-value">${report.risk_summary.medium}</div>
                <div class="stat-label">中风险</div>
            </div>
            <div class="stat-item low">
                <div class="stat-value">${report.risk_summary.low}</div>
                <div class="stat-label">低风险</div>
            </div>
        </div>
    `);

    // 组装所有部分
    resultDiv.appendChild(overviewSection);
    resultDiv.appendChild(ratiosSection);
    resultDiv.appendChild(scoreSection);
    resultDiv.appendChild(risksSection);
    resultDiv.appendChild(statsSection);

    container.appendChild(resultDiv);
}

// 辅助函数
function createSection(title, content) {
    const section = document.createElement('div');
    section.className = 'analysis-section';
    section.innerHTML = `
        <h3 class="section-title">${title}</h3>
        <div class="section-content">${content}</div>
    `;
    return section;
}

function formatMoney(value) {
    if (!value) return '-';
    const yi = value / 100000000;
    return yi.toFixed(2) + ' 亿元';
}

function getScoreClass(score) {
    if (score >= 80) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 40) return 'warning';
    return 'danger';
}
