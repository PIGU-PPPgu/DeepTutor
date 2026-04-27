import { Bot, Brain, FileText, GraduationCap, Library, Network, Sparkles } from "lucide-react";
import { APP_VERSION } from "@/lib/app-version";

const features = [
  { icon: GraduationCap, title: "深度解题", desc: "支持题目文本/图片输入，按计划、推理、解答、复盘拆解复杂题。" },
  { icon: Network, title: "知识图谱", desc: "把知识点关系可视化，适合复习薄弱点和串联章节结构。" },
  { icon: Library, title: "课外书学习", desc: "支持把课外阅读材料纳入知识库，再用于问答、总结和图谱化学习。" },
  { icon: Bot, title: "辅导机器人", desc: "可创建不同人格/用途的 TutorBot，用于特定学科或学习场景。" },
  { icon: FileText, title: "共写与笔记", desc: "支持写作辅助、读书笔记、学习记录和内容整理。" },
  { icon: Brain, title: "记忆与个性化", desc: "围绕学习过程沉淀上下文，让后续辅导更贴近个人情况。" },
];

export default function FeaturesPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="mb-8 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-7">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--border)] px-3 py-1 text-xs text-[var(--muted-foreground)]">
          <Sparkles className="h-3.5 w-3.5" /> 当前版本 {APP_VERSION}
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-[var(--foreground)]">功能说明</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">
          这里说明当前版本多了什么、分别怎么用。建议先从“上传资料 → 生成知识图谱 → 深度解题/问答”这条学习链路开始。
        </p>
      </div>

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
  );
}
