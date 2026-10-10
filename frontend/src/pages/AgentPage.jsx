import { useState, useRef, useEffect } from 'react'
import styles from './AgentPage.module.css'

export default function AgentPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim() || isThinking) return

    const userMessage = {
      role: 'user',
      content: input.trim()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsThinking(true)

    try {
      // 调用后端 Agent API（目前使用模拟数据）
      const response = await simulateAgentCall(userMessage.content)

      setMessages(prev => [...prev, response])
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'agent',
        content: '抱歉，处理请求时出错了。',
        error: true
      }])
    } finally {
      setIsThinking(false)
    }
  }

  const handleExampleClick = (question) => {
    setInput(question)
  }

  return (
    <div className={styles.agentPage}>
      <h1 className={styles.pageTitle}>AI 研究助手</h1>

      <div className={styles.chatContainer}>
        <div className={styles.messagesArea}>
          {messages.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyStateIcon}>💬</div>
              <div className={styles.emptyStateText}>
                问我关于股票价格、涨跌幅的问题，我会使用工具来计算
              </div>
              <div className={styles.exampleQuestions}>
                <button
                  className={styles.exampleQuestion}
                  onClick={() => handleExampleClick('平安银行从 10 元跌到 9 元，跌幅是多少？')}
                >
                  平安银行从 10 元跌到 9 元，跌幅是多少？
                </button>
                <button
                  className={styles.exampleQuestion}
                  onClick={() => handleExampleClick('股价从 50 涨到 55，涨幅是多少？')}
                >
                  股价从 50 涨到 55，涨幅是多少？
                </button>
                <button
                  className={styles.exampleQuestion}
                  onClick={() => handleExampleClick('计算 100 到 120 的变化率')}
                >
                  计算 100 到 120 的变化率
                </button>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, idx) => (
                <Message key={idx} message={msg} />
              ))}
              {isThinking && <ThinkingIndicator />}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className={styles.inputArea}>
          <form className={styles.inputForm} onSubmit={handleSubmit}>
            <textarea
              className={styles.inputBox}
              placeholder="请输入问题..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSubmit(e)
                }
              }}
            />
            <button
              type="submit"
              className={styles.sendButton}
              disabled={!input.trim() || isThinking}
            >
              发送
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

function Message({ message }) {
  return (
    <div className={styles.message}>
      <div className={styles.messageHeader}>
        <span className={`${styles.messageRole} ${styles[message.role]}`}>
          {message.role === 'user' ? '👤 用户' : '🤖 Agent'}
        </span>
      </div>
      <div className={styles.messageContent}>
        {message.content}
      </div>
      {message.toolExecutions && message.toolExecutions.map((tool, idx) => (
        <ToolExecution key={idx} tool={tool} />
      ))}
    </div>
  )
}

function ToolExecution({ tool }) {
  return (
    <div className={styles.toolExecution}>
      <div className={styles.toolHeader}>
        <div className={styles.toolName}>
          🔧 调用工具：{tool.name}
        </div>
        <span className={`${styles.toolStatus} ${styles[tool.status]}`}>
          {tool.status === 'success' ? '✓ 成功' : '✗ 失败'}
        </span>
      </div>
      <div className={styles.toolDetails}>
        <div className={styles.toolDetail}>
          <span className={styles.toolDetailLabel}>参数：</span>
          <span className={styles.toolDetailValue}>
            {JSON.stringify(tool.arguments)}
          </span>
        </div>
        <div className={styles.toolDetail}>
          <span className={styles.toolDetailLabel}>结果：</span>
          <span className={styles.toolDetailValue}>
            {tool.result !== undefined ? tool.result : tool.error}
          </span>
        </div>
        <div className={styles.toolDuration}>
          耗时：{tool.duration_ms.toFixed(2)}ms
        </div>
      </div>
    </div>
  )
}

function ThinkingIndicator() {
  return (
    <div className={styles.message}>
      <div className={styles.messageHeader}>
        <span className={`${styles.messageRole} ${styles.agent}`}>
          🤖 Agent
        </span>
      </div>
      <div className={styles.thinkingIndicator}>
        正在思考
        <div className={styles.thinkingDots}>
          <span className={styles.thinkingDot}></span>
          <span className={styles.thinkingDot}></span>
          <span className={styles.thinkingDot}></span>
        </div>
      </div>
    </div>
  )
}

// 模拟 Agent 调用（后续替换为真实 API）
async function simulateAgentCall(userInput) {
  // 模拟延迟
  await new Promise(resolve => setTimeout(resolve, 1500))

  // 检测是否包含计算意图
  const match = userInput.match(/从?\s*(\d+\.?\d*)\s*[到涨跌]\s*(\d+\.?\d*)/)

  if (match) {
    const oldValue = parseFloat(match[1])
    const newValue = parseFloat(match[2])
    const change = ((newValue - oldValue) / oldValue * 100).toFixed(4)

    return {
      role: 'agent',
      content: `根据计算，从 ${oldValue} 到 ${newValue}，变化率为 ${change}%。`,
      toolExecutions: [
        {
          name: 'calculate_change',
          arguments: { old_value: oldValue, new_value: newValue },
          result: `${change}%`,
          status: 'success',
          duration_ms: Math.random() * 50 + 10
        }
      ]
    }
  }

  return {
    role: 'agent',
    content: '我理解了您的问题，但目前只支持价格变化率计算。请尝试类似"从 10 到 9 的变化率"这样的问题。'
  }
}
