import { ref, watch } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'palmprint-theme'

function readInitial(): Theme {
  // index.html 里挂载前的内联脚本已根据 localStorage 切好 .dark 类（无记录时默认
  // 亮色）；这里镜像该结果，使 Vue 状态从首帧起就同步。
  if (typeof document !== 'undefined' && document.documentElement.classList.contains('dark')) {
    return 'dark'
  }
  return 'light'
}

// 模块级单例：App.vue（驱动 Naive UI 主题）与 ThemeToggle.vue 共享同一份状态，
// 否则各自的 theme ref 互不相通，点按钮时 Naive UI 主题不会跟着切。
const theme = ref<Theme>(readInitial())

function apply(t: Theme) {
  const cls = document.documentElement.classList
  if (t === 'dark') cls.add('dark')
  else cls.remove('dark')
}

let started = false
function ensureStarted() {
  if (started) return
  started = true
  apply(theme.value)
  watch(theme, (t) => {
    apply(t)
    try {
      localStorage.setItem(STORAGE_KEY, t)
    } catch {
      /* 隐私模式等 */
    }
  })
}

export function useTheme() {
  ensureStarted()

  function toggle(event?: MouseEvent) {
    const next: Theme = theme.value === 'dark' ? 'light' : 'dark'

    const supportsVT = typeof (document as any).startViewTransition === 'function'
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!supportsVT || reduced) {
      theme.value = next
      return
    }

    // 揭开动画的圆心 = 点击位置；缺省回退到视口中心。
    const x = event?.clientX ?? window.innerWidth / 2
    const y = event?.clientY ?? window.innerHeight / 2
    // 离圆心最远的角 = 覆盖整个视口所需的半径。
    const maxR = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y),
    )

    const root = document.documentElement
    root.style.setProperty('--theme-x', `${x}px`)
    root.style.setProperty('--theme-y', `${y}px`)
    root.style.setProperty('--theme-r', `${maxR}px`)

    // 截图期间挂起元素级 CSS 过渡，否则 body { transition: background-color }
    // 会让"新"快照显示半渐变的颜色，圆形揭开就看不出来了。
    const transition = (document as any).startViewTransition(() => {
      root.classList.add('vt-instant')
      theme.value = next
      apply(next)
    })
    transition.finished.finally(() => {
      root.classList.remove('vt-instant')
    })
  }

  return { theme, toggle }
}
