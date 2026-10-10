import styles from './PlaceholderPage.module.css'

export default function RiskPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>风险监控</h1>
      <div className={styles.placeholder}>
        <div className={styles.placeholderIcon}>📈</div>
        <div className={styles.placeholderText}>功能开发中</div>
        <div className={styles.placeholderHint}>
          将支持输入公告/财报内容，生成结构化风险摘要
        </div>
      </div>
    </div>
  )
}
