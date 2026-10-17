import styles from './PlaceholderPage.module.css'

export default function SettingsPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>系统设置</h1>
      <div className={styles.placeholder}>
        <div className={styles.placeholderIcon}>⚙️</div>
        <div className={styles.placeholderText}>功能开发中</div>
        <div className={styles.placeholderHint}>
          将支持 API Key 配置、行情源选择等设置
        </div>
      </div>
    </div>
  )
}
