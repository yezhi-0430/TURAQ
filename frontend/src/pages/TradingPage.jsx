import styles from './PlaceholderPage.module.css'

export default function TradingPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>模拟交易</h1>
      <div className={styles.placeholder}>
        <div className={styles.placeholderIcon}>💰</div>
        <div className={styles.placeholderText}>功能开发中</div>
        <div className={styles.placeholderHint}>
          将展示账户信息、持仓列表和成交记录
        </div>
      </div>
    </div>
  )
}
