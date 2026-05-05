import { Bot, Brain, FileText, GraduationCap, Library, Network, Sparkles, GitCompare, GitBranch } from "lucide-react";
import { APP_VERSION } from "@/lib/app-version";

const features = [
  { icon: GraduationCap, title: "深度解题", desc: "面向数学/理科题的多步推理链路，支持图片题、规划、解答、复盘。" },
  { icon: Network, title: "知识图谱", desc: "把知识点、章节、阅读材料结构化，帮助学生看见知识之间的关系。" },
  { icon: Library, title: "课外书学习", desc: "可把课外书、阅读材料、讲义纳入学习资料，再用于总结、问答和图谱化。" },
  { icon: Bot, title: "辅导机器人", desc: "创建不同学科/人格的 TutorBot，用于指定场景的陪伴式学习。" },
  { icon: FileText, title: "共写与笔记", desc: "支持写作辅助、读书笔记、学习记录和内容整理。" },
  { icon: Brain, title: "记忆与个性化", desc: "围绕学习过程沉淀上下文，让后续辅导更贴近个人情况。" },
];

const comparison = [
  { area: "统一学习工作台", deeptutor: "Chat、Deep Solve、Quiz、Research、Math Animator、Visualize 共用同一线程。", intellitutor: "保留统一工作台，并按教师/学生真实使用重新整理入口与中文说明。", effect: "学生不用在多个工具之间跳来跳去；老师演示时路径更短。" },
  { area: "知识库 / RAG", deeptutor: "v1.3.0 新增版本化知识库索引、重建索引流程、原始文件预览、索引状态。", intellitutor: "继续沿用知识库底座，额外准备阅读材料和学科内容种子。", effect: "DeepTutor 偏通用资料管理；IntelliTutor 更偏课堂内容落地。" },
  { area: "知识图谱", deeptutor: "有基础知识图谱与学习节点能力。", intellitutor: "强化图谱交互：目录/节点定位、主题拆分、字体可读性、名著/数学独立图谱。", effect: "不再把《红楼梦》和高中数学混成一锅粥，学生能按主题看知识结构。" },
  { area: "课外书学习", deeptutor: "Book Engine 可把材料编译成 living book。", intellitutor: "面向《红楼梦》《骆驼祥子》等阅读教学，加入导读、人物关系、章节结构图谱。", effect: "更适合语文/阅读课直接使用，而不是只展示技术能力。" },
  { area: "数学动画", deeptutor: "Math Animator 支持生成数学动画/图片，但部署依赖要求高。", intellitutor: "线上修复 Manim/libffi 依赖，默认降级为 low-quality 静态分镜图。", effect: "从“十分钟没反应”变成优先快速返回可见图片；课堂上更稳。" },
  { area: "附件与预览", deeptutor: "v1.2.3-v1.2.5 强化 PDF/Office/图片/SVG/代码附件、预览和下载。", intellitutor: "计划评估合并上游附件增强，但不会无脑覆盖现有品牌、登录和图谱改造。", effect: "合并后能提升资料导入体验；评估后合并能避免把现有功能搞炸。" },
  { area: "用户系统", deeptutor: "默认更像本地/单人开源工具，没有完整生产用户管理。", intellitutor: "新增注册登录、邀请码、管理员后台、禁用/启用、重置密码、管理员切换。", effect: "可以小规模给学生/老师试用，不至于谁都能乱注册。" },
  { area: "TutorBot", deeptutor: "Personal TutorBots 是核心能力，近期也清理了 channel 依赖。", intellitutor: "保留 TutorBot，并修正创建失败提示、入口和部署环境体验。", effect: "可以继续做不同学科/不同人格的学习助手。" },
  { area: "Space / Notebook / Skills / Memory", deeptutor: "v1.3.0 增加 Space hub，整合 Notebooks、Question Bank、Skills、Memory。", intellitutor: "已具备笔记/记忆/技能相关入口，但上游 Space hub 需要专项评估再合并。", effect: "这是本次上游更新最值得评估的部分，可能显著改善信息组织。" },
  { area: "部署与版本识别", deeptutor: "提供开源启动、诊断、Windows 修复和版本发布。", intellitutor: "增加线上版本识别、生产域名、服务器依赖修复和管理员初始化。", effect: "Pigou 能判断线上到底是不是最新版本，排障成本更低。" },
];

const upstreamLogs = [
  { version: "v1.3.0", date: "2026.4.27", text: "版本化知识库索引、重建索引流程、Knowledge 管理工作区重做、原始文件预览、索引版本状态、embedding 维度自动发现、SiliconFlow/Aliyun/OpenAI SDK adapters、reasoning-stream 和视觉附件鲁棒性、Space hub、TutorBot/channel 依赖清理、Matrix extra、Windows 启动/调试修复。" },
  { version: "v1.2.5", date: "2026.4.25", text: "持久化聊天附件、右侧文件预览抽屉、代码附件覆盖扩展、附件感知 Deep Solve/Question/Research/Visualize、TutorBot 保存到 Notebook、Markdown 导出、Setup Tour 诊断、滚动/上传选择器修复。" },
  { version: "v1.2.4", date: "2026.4.25", text: "文本/代码/SVG 聊天附件、一键 Setup Tour、uv pip 和 Windows npm 修复、Markdown 聊天导出、紧凑 Knowledge Base UI、主题/popover polish、release/version hardening。" },
  { version: "v1.2.3", date: "2026.4.24", text: "PDF/DOCX/XLSX/PPTX 附件、reasoning thinking-block 展示、embedding send_dimensions 三态开关、LLM provider core refactor、Soul 模板编辑器、Co-Writer 保存到 Notebook、知识库拖拽上传与删除韧性。" },
  { version: "v1.2.2", date: "2026.4.22", text: "用户自定义 Skills、聊天输入性能重构、response_format 自动 fallback、LAN 远程访问修复、sidebar version badge、Deep Solve 图片附件、TutorBot WebSocket auto-start、Book Library UI、visualization 全屏。" },
];

const intelliLogs = [
  { version: "IntelliTutor 2026.4.27", date: "2026.4.27", text: "上线管理员用户管理雏形：用户列表、禁用/启用、管理员切换、重置密码；管理员默认为 pigouwu。" },
  { version: "Math Animator 修复", date: "2026.4.27", text: "生产环境安装 Manim 依赖，修复 conda libffi 冲突；后端错误不再伪装成 completed 空回复；默认改为 image/low 静态分镜优先。" },
  { version: "知识图谱拆分", date: "2026.4.27", text: "把旧混合图谱拆成红楼梦阅读图谱、骆驼祥子阅读图谱、高中数学人教A版知识图谱，并修复 SVG 字体颜色和节点居中飞走问题。" },
  { version: "功能页升级", date: "2026.4.27", text: "新增 IntelliTutor vs DeepTutor 对比表，说明双方能力、我们的增强和实际效果；加入上游/本项目更新日志 tabs。" },
  { version: "Phase 0-3 能力增强", date: "2026.4.18-20", text: "完成内容分析、学习计划、苏格拉底对话、测评、闪卡、音频陪伴、内容管理、知识图谱入口等多项课堂化能力。" },
];

export default function FeaturesPage() {
  return (
    <main className="h-full overflow-y-auto [scrollbar-gutter:stable]">
      <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-7">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--border)] px-3 py-1 text-xs text-[var(--muted-foreground)]">
          <Sparkles className="h-3.5 w-3.5" /> 当前版本 {APP_VERSION}
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-[var(--foreground)]">IntelliTutor 功能说明</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">
          IntelliTutor 基于 DeepTutor 做了产品化改造：从“开源学习助手框架”变成面向学生、老师和家庭试用的学习工作台。
        </p>
      </div>

      <section className="mb-6 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)]">
        <div className="border-b border-[var(--border)] p-6">
          <div className="mb-2 flex items-center gap-2">
            <GitCompare className="h-5 w-5 text-[var(--foreground)]" />
            <h2 className="text-lg font-medium text-[var(--foreground)]">DeepTutor 做了什么 / 我们做了什么 / 效果怎样</h2>
          </div>
          <p className="text-sm leading-6 text-[var(--muted-foreground)]">
            不只打勾。下面按能力维度说明：原版上游提供了什么、IntelliTutor 在真实课堂/学生试用里补了什么、最后用户能感受到什么差异。
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead className="bg-[var(--muted)]/50 text-xs uppercase tracking-wide text-[var(--muted-foreground)]">
              <tr>
                <th className="w-40 px-5 py-3 text-left font-medium">能力维度</th>
                <th className="px-5 py-3 text-left font-medium">DeepTutor 做了什么</th>
                <th className="px-5 py-3 text-left font-medium">我们做了什么</th>
                <th className="px-5 py-3 text-left font-medium">实际效果</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {comparison.map((row) => (
                <tr key={row.area} className="hover:bg-[var(--muted)]/30">
                  <td className="px-5 py-4 align-top font-medium text-[var(--foreground)]">{row.area}</td>
                  <td className="px-5 py-4 align-top text-xs leading-5 text-[var(--muted-foreground)]">{row.deeptutor}</td>
                  <td className="px-5 py-4 align-top text-xs leading-5 text-[var(--muted-foreground)]">{row.intellitutor}</td>
                  <td className="px-5 py-4 align-top text-xs leading-5 text-[var(--foreground)]">{row.effect}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
        <div className="mb-4 flex items-center gap-2">
          <GitBranch className="h-5 w-5 text-[var(--foreground)]" />
          <h2 className="text-lg font-medium text-[var(--foreground)]">项目更新日志</h2>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--muted)]/20 p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--foreground)]">DeepTutor 上游更新</h3>
            <div className="space-y-3">
              {upstreamLogs.map((log) => (
                <article key={log.version} className="rounded-lg bg-[var(--card)] p-3">
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-[var(--foreground)]">{log.version}</span>
                    <span className="text-xs text-[var(--muted-foreground)]">{log.date}</span>
                  </div>
                  <p className="text-xs leading-5 text-[var(--muted-foreground)]">{log.text}</p>
                </article>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--muted)]/20 p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--foreground)]">IntelliTutor 本项目更新</h3>
            <div className="space-y-3">
              {intelliLogs.map((log) => (
                <article key={log.version} className="rounded-lg bg-[var(--card)] p-3">
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-[var(--foreground)]">{log.version}</span>
                    <span className="text-xs text-[var(--muted-foreground)]">{log.date}</span>
                  </div>
                  <p className="text-xs leading-5 text-[var(--muted-foreground)]">{log.text}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
        <p className="mt-4 rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-xs leading-5 text-amber-700 dark:text-amber-300">
          同步策略：DeepTutor 今天的 v1.3.0 值得合并评估，尤其是版本化知识库索引和 Space hub；但设置页“一键同步”目前风险偏高，不能直接点了就合并生产代码。正确做法是先 dry-run / diff / build / smoke test，再决定合并哪些文件。
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <section key={feature.title} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--muted)] text-[var(--foreground)]">
                <Icon className="h-5 w-5" />
              </div>
              <h2 className="text-base font-medium text-[var(--foreground)]">{feature.title}</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">{feature.desc}</p>
            </section>
          );
        })}
      </div>

      <section className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
        <h2 className="text-lg font-medium text-[var(--foreground)]">课外书如何进入知识图谱？</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-[var(--muted-foreground)]">
          <li>进入 Book 或 Knowledge 页面，上传/整理课外书材料。</li>
          <li>确认材料已进入知识库后，打开 Knowledge Graph。</li>
          <li>输入“为这本书生成知识图谱/人物关系/章节结构”，即可生成图谱化视图。</li>
        </ol>
      </section>
    </div>
  </main>
  );
}
