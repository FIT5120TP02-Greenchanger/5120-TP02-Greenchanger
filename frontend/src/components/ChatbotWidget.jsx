import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import styles from './ChatbotWidget.module.css'

const STORAGE_KEY = 'greenshift_chat_messages'
const BOT_NAME = 'GreenBot'

function loadStoredMessages() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY)
        return raw ? JSON.parse(raw) : []
    } catch {
        return []
    }
}

function persistMessages(messages) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
    } catch {
        // localStorage full/unavailable — chat still works for this session, just won't persist
    }
}

// True when there's something worth telling the bot about — keeps this generic
// rather than assuming the exact shape of propertyStats/canopyStats.
function hasUsableContext(context) {
    if (!context) return false
    return Object.values(context).some(value => value !== null && value !== undefined)
}

export default function ChatbotWidget({ context }) {
    const [isOpen, setIsOpen] = useState(false)
    const [hasUnread, setHasUnread] = useState(false)
    const [messages, setMessages] = useState(() => loadStoredMessages())
    const [inputText, setInputText] = useState('')
    const [isSending, setIsSending] = useState(false)
    const scrollRef = useRef(null)

    const contextAvailable = hasUsableContext(context)

    // persist on every change, and keep the view scrolled to the latest message
    useEffect(() => {
        persistMessages(messages)
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [messages])

    function toggleOpen() {
        setIsOpen(prev => !prev)
        setHasUnread(false)
    }

    async function handleSend() {
        const textToSend = inputText.trim()
        if (!textToSend || isSending) return

        const userMsg = { role: 'user', content: textToSend, ts: Date.now() }
        const thinkingMsg = { role: 'assistant', content: 'Thinking...', ts: Date.now() + 1, pending: true }

        setMessages(prev => [...prev, userMsg, thinkingMsg])
        setInputText('')
        setIsSending(true)

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: textToSend, history: messages, context: context || null })
            })
            const data = await response.json()

            setMessages(prev =>
                prev.map(msg =>
                    msg.pending ? { role: 'assistant', content: data.response, ts: Date.now() } : msg
                )
            )

            if (!isOpen) setHasUnread(true)
        } catch (err) {
            setMessages(prev =>
                prev.map(msg =>
                    msg.pending
                        ? { role: 'assistant', content: "Sorry, I couldn't reach the server. Try again in a moment." }
                        : msg
                )
            )
        } finally {
            setIsSending(false)
        }
    }

    function handleInputChange(e) {
        setInputText(e.target.value)
    }

    function handleKeyDown(e) {
        if (e.key === 'Enter') handleSend()
    }

    function handleClearChat() {
        setMessages([])
        localStorage.removeItem(STORAGE_KEY)
    }

    return (
        <div className={styles.widget}>
            {isOpen && (
                <div className={styles.panel} role="dialog" aria-label={`${BOT_NAME} chat`}>
                    <div className={styles.header}>
                        <div className={styles.headerTitle}>
                            <span className={styles.leaf}>🌿</span>
                            <span>{BOT_NAME}</span>
                            {contextAvailable && (
                                <span
                                    className={styles.contextDot}
                                    title="GreenBot can see the current map data"
                                    aria-label="Live map data connected"
                                />
                            )}
                        </div>
                        <div className={styles.headerActions}>
                            <button
                                className={styles.iconButton}
                                onClick={handleClearChat}
                                aria-label="Clear conversation"
                                title="Clear conversation"
                                type="button"
                            >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                    <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                            </button>
                            <button
                                className={styles.iconButton}
                                onClick={toggleOpen}
                                aria-label="Collapse chat"
                                title="Collapse"
                                type="button"
                            >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                    <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                            </button>
                        </div>
                    </div>

                    <div className={styles.history} ref={scrollRef}>
                        {messages.length === 0 && (
                            <p className={styles.intro}>
                                Hi, I'm {BOT_NAME}.{' '}
                                {contextAvailable
                                    ? "I can see the property and canopy data for what you're viewing — ask me anything about it."
                                    : 'Ask me about greening your street — trees, green walls, pots, or how a change might cool things down.'}
                            </p>
                        )}
                        {messages.map((msg, i) => (
                            <div key={i} className={msg.role === 'user' ? styles.userMsg : styles.botMsg}>
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                            </div>
                        ))}
                    </div>

                    <div className={styles.controls}>
                        <input
                            className={styles.input}
                            type="text"
                            placeholder={`Ask ${BOT_NAME}...`}
                            aria-label="Message"
                            value={inputText}
                            onChange={handleInputChange}
                            onKeyDown={handleKeyDown}
                            disabled={isSending}
                        />
                        <button
                            className={styles.sendButton}
                            onClick={handleSend}
                            disabled={isSending || !inputText.trim()}
                            aria-label="Send message"
                            type="button"
                        >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <path d="M4 12L20 4l-7 16-2-7-7-1z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                            </svg>
                        </button>
                    </div>
                </div>
            )}

            <button
                className={styles.bubble}
                onClick={toggleOpen}
                aria-label={isOpen ? `Close ${BOT_NAME}` : `Open ${BOT_NAME}`}
                aria-expanded={isOpen}
                type="button"
            >
                {isOpen ? (
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                        <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                ) : (
                    <span className={styles.bubbleLeaf}>🌿</span>
                )}
                {hasUnread && !isOpen && <span className={styles.badge} />}
            </button>
        </div>
    )
}