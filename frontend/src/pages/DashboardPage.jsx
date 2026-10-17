import styles from './PlaceholderPage.module.css'

export default function DashboardPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>行情驾驶舱</h1>
      <div className={styles.placeholder}>
        <div className={styles.placeholderIcon}>📊</div>
        <div className={styles.placeholderText}>功能开发中</div>
        <div className={styles.placeholderHint}>
          将展示市场概览、自选股实时价格和最近风险线索
        </div>
      </div>
    </div>
  )
}
