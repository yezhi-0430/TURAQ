import { useState } from 'react'
import styles from './Layout.module.css'

export default function Layout({ children, currentPage, onNavigate }) {
  return (
    <div className={styles.layout}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.logo}>A股风险监控</div>
          <div className={styles.marketTickers}>
            <div className={styles.ticker}>
              <span className={styles.tickerName}>上证指数</span>
              <span className={styles.tickerValue}>3563.12</span>
              <span className={`${styles.tickerChange} ${styles.up}`}>+1.18%</span>
            </div>
            <div className={styles.ticker}>
              <span className={styles.tickerName}>深证成指</span>
              <span className={styles.tickerValue}>4694.44</span>
              <span className={`${styles.tickerChange} ${styles.up}`}>+0.93%</span>
            </div>
            <div className={styles.ticker}>
              <span className={styles.tickerName}>创业板指</span>
              <span className={styles.tickerValue}>1744.02</span>
              <span className={`${styles.tickerChange} ${styles.down}`}>-2.51%</span>
            </div>
          </div>
        </div>
        <div className={styles.headerRight}>
          <div className={styles.searchBox}>
            <span>🔍</span>
            <input type="text" placeholder="搜索股票代码或名称" />
          </div>
          <div className={styles.accountInfo}>
            模拟账户
            <span className={styles.accountBalance}>¥500,000</span>
          </div>
        </div>
      </header>

      <aside className={styles.sidebar}>
        <nav>
          <ul className={styles.navList}>
            <li className={styles.navItem}>
              <a
                href="#"
                className={`${styles.navLink} ${currentPage === 'dashboard' ? styles.active : ''}`}
                onClick={(e) => { e.preventDefault(); onNavigate('dashboard'); }}
              >
                <span className={styles.navIcon}>📊</span>
                行情驾驶舱
              </a>
            </li>
            <li className={styles.navItem}>
              <a
                href="#"
                className={`${styles.navLink} ${currentPage === 'watchlist' ? styles.active : ''}`}
                onClick={(e) => { e.preventDefault(); onNavigate('watchlist'); }}
              >
                <span className={styles.navIcon}>📋</span>
                自选管理
              </a>
            </li>
            <li className={styles.navItem}>
              <a
                href="#"
                className={`${styles.navLink} ${currentPage === 'agent' ? styles.active : ''}`}
                onClick={(e) => { e.preventDefault(); onNavigate('agent'); }}
              >
                <span className={styles.navIcon}>💬</span>
                AI 研究助手
              </a>
            </li>
            <li className={styles.navItem}>
              <a
                href="#"
                className={`${styles.navLink} ${currentPage === 'risk' ? styles.active : ''}`}
                onClick={(e) => { e.preventDefault(); onNavigate('risk'); }}
              >
                <span className={styles.navIcon}>📈</span>
                风险监控
              </a>
            </li>
            <li className={styles.navItem}>
              <a
                href="#"
                className={`${styles.navLink} ${currentPage === 'trading' ? styles.active : ''}`}
                onClick={(e) => { e.preventDefault(); onNavigate('trading'); }}
              >
                <span className={styles.navIcon}>📊</span>
                模拟交易
              </a>
            </li>
            <li className={styles.navItem}>
              <a
                href="#"
                className={`${styles.navLink} ${currentPage === 'settings' ? styles.active : ''}`}
                onClick={(e) => { e.preventDefault(); onNavigate('settings'); }}
              >
                <span className={styles.navIcon}>⚙️</span>
                系统设置
              </a>
            </li>
          </ul>
        </nav>
      </aside>

      <main className={styles.mainContent}>
        {children}
      </main>
    </div>
  )
}
