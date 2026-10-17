import styles from './PlaceholderPage.module.css'

export default function WatchlistPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>自选管理</h1>
      <div className={styles.placeholder}>
        <div className={styles.placeholderIcon}>📋</div>
        <div className={styles.placeholderText}>功能开发中</div>
        <div className={styles.placeholderHint}>
          将支持创建自选组、添加和移除股票
        </div>
      </div>
    </div>
  )
}
